/**
 * 后端 API 客户端
 * - 浏览器端：所有请求走 /api/v1/*，由 Next.js rewrites 代理到后端
 * - 服务端：直连 BACKEND_API_URL
 */

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  /** 后端为每个请求生成的编号，用户反馈问题时据此在日志里定位 */
  request_id?: string;
}

export class ApiException extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: Record<string, unknown>;
  readonly requestId?: string;

  constructor(status: number, error: ApiError) {
    super(error.message);
    this.name = "ApiException";
    this.code = error.code;
    this.status = status;
    this.details = error.details;
    this.requestId = error.request_id;
  }
}

const isServer = typeof window === "undefined";

function getBaseUrl(): string {
  if (isServer) {
    return process.env.BACKEND_API_URL ?? "http://localhost:8000";
  }
  return "";
}

interface FetchOptions extends RequestInit {
  /** 是否携带 session cookie（默认 true） */
  withCredentials?: boolean;
  /** 超时毫秒数，默认 DEFAULT_TIMEOUT_MS；传 null 不设超时（长轮询等自带超时的调用） */
  timeoutMs?: number | null;
}

/** Blaze 重连后首个请求要 4–7 秒，带全队战绩的服务器名单更慢，30 秒留足余量 */
const DEFAULT_TIMEOUT_MS = 30_000;

/** 合并调用方的取消信号与超时信号；老浏览器缺少 AbortSignal.any / timeout 时退化为只用其中一个 */
function withTimeout(
  signal: AbortSignal | null | undefined,
  timeoutMs: number | null,
): { signal: AbortSignal | undefined; timeout: AbortSignal | undefined } {
  const timeout =
    timeoutMs && typeof AbortSignal.timeout === "function"
      ? AbortSignal.timeout(timeoutMs)
      : undefined;
  if (!signal) return { signal: timeout, timeout };
  if (!timeout || typeof AbortSignal.any !== "function") return { signal, timeout: undefined };
  return { signal: AbortSignal.any([signal, timeout]), timeout };
}

/**
 * 把失败响应解析为统一 ApiError。除后端统一的 `{error:{...}}` 外，还兜底两类
 * 真实出现过的形态：
 * - FastAPI 默认的 `{detail: [...]}`（422 参数校验）或 `{detail: "..."}`，没有 error 包装；
 * - 非 JSON 响应（CDN / 反代错误页，如 Cloudflare 替换源站 502/504 的 HTML 页）。
 * message 最终兜底为「请求失败（HTTP xxx）」——不能用 res.statusText，HTTP/2 下它恒为
 * 空串，曾导致报错 toast 整条空白。
 */
async function parseApiError(res: Response): Promise<ApiError> {
  let code = `HTTP_${res.status}`;
  let message = "";
  let details: Record<string, unknown> | undefined;
  let requestId: string | undefined;
  try {
    const payload = (await res.json()) as { error?: Partial<ApiError>; detail?: unknown };
    if (payload.error) {
      code = payload.error.code ?? code;
      message = payload.error.message ?? "";
      details = payload.error.details;
      requestId = payload.error.request_id;
    } else if (typeof payload.detail === "string") {
      message = payload.detail;
    } else if (Array.isArray(payload.detail) && payload.detail.length > 0) {
      // Pydantic 校验错误：取第一条的字段路径 + 原因
      const first = payload.detail[0] as { loc?: unknown[]; msg?: string };
      const loc = Array.isArray(first.loc)
        ? first.loc.filter((part) => part !== "body").join(".")
        : "";
      message = `参数校验失败${loc ? `（${loc}）` : ""}${first.msg ? `：${first.msg}` : ""}`;
      code = "VALIDATION_ERROR";
    }
  } catch {
    // 非 JSON 响应，走下方兜底文案
  }
  if (!message) message = `请求失败（HTTP ${res.status}）`;
  // 服务端内部错误附上编号，用户截图或反馈时带上即可定位；4xx 是预期内的结果，不打扰
  if (res.status >= 500 && res.status !== 503 && requestId) {
    message = `${message}（错误编号 ${requestId}）`;
  }
  return { code, message, details, request_id: requestId };
}

async function fetchApi<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { withCredentials = true, timeoutMs = DEFAULT_TIMEOUT_MS, ...init } = options;

  const url = `${getBaseUrl()}/api/v1${path.startsWith("/") ? path : `/${path}`}`;
  const { signal, timeout } = withTimeout(init.signal, timeoutMs);

  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      signal,
      credentials: withCredentials ? "include" : "omit",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...init.headers,
      },
    });
  } catch (err) {
    // 调用方主动取消（组件卸载等）原样抛出，交给调用方按取消处理
    if (init.signal?.aborted) throw err;
    if (timeout?.aborted) {
      throw new ApiException(0, {
        code: "TIMEOUT",
        message: "请求超时，EA 或本站响应太慢，请稍后重试",
      });
    }
    throw new ApiException(0, {
      code: "NETWORK_ERROR",
      message: "网络连接失败，请检查网络后重试",
    });
  }

  if (!res.ok) {
    throw new ApiException(res.status, await parseApiError(res));
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;

  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, options?: FetchOptions) =>
    fetchApi<T>(path, { ...options, method: "GET" }),

  post: <T>(path: string, body?: unknown, options?: FetchOptions) =>
    fetchApi<T>(path, {
      ...options,
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),

  put: <T>(path: string, body?: unknown, options?: FetchOptions) =>
    fetchApi<T>(path, {
      ...options,
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown, options?: FetchOptions) =>
    fetchApi<T>(path, {
      ...options,
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string, options?: FetchOptions) =>
    fetchApi<T>(path, { ...options, method: "DELETE" }),
};

export type ApiErrorKind = "not_found" | "busy" | "timeout" | "network" | "server";

export interface ApiErrorView {
  kind: ApiErrorKind;
  /** 面向用户的说明；not_found 由页面给出更贴切的文案 */
  message: string;
  /** 本站内部错误的编号，用于反馈 */
  requestId?: string;
  /** 是否值得给「重试」按钮 */
  retryable: boolean;
}

/** 把查询错误归成几类，页面据此决定文案、要不要重试按钮、要不要附反馈入口 */
export function describeApiError(error: unknown): ApiErrorView {
  if (!(error instanceof ApiException)) {
    return { kind: "server", message: "加载失败，请稍后重试", retryable: true };
  }
  if (error.status === 404) {
    return { kind: "not_found", message: error.message, retryable: false };
  }
  if (error.status === 429 || error.code === "EA_BUSY") {
    return { kind: "busy", message: error.message, retryable: true };
  }
  if (error.code === "TIMEOUT") return { kind: "timeout", message: error.message, retryable: true };
  if (error.code === "NETWORK_ERROR") {
    return { kind: "network", message: error.message, retryable: true };
  }
  return {
    kind: "server",
    message: error.message,
    requestId: error.status >= 500 && error.status !== 503 ? error.requestId : undefined,
    retryable: true,
  };
}
