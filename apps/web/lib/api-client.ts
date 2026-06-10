/**
 * 后端 API 客户端
 * - 浏览器端：所有请求走 /api/v1/*，由 Next.js rewrites 代理到后端
 * - 服务端：直连 BACKEND_API_URL
 */

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export class ApiException extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: Record<string, unknown>;

  constructor(status: number, error: ApiError) {
    super(error.message);
    this.name = "ApiException";
    this.code = error.code;
    this.status = status;
    this.details = error.details;
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
  try {
    const payload = (await res.json()) as { error?: Partial<ApiError>; detail?: unknown };
    if (payload.error) {
      code = payload.error.code ?? code;
      message = payload.error.message ?? "";
      details = payload.error.details;
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
  return { code, message, details };
}

async function fetchApi<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { withCredentials = true, ...init } = options;

  const url = `${getBaseUrl()}/api/v1${path.startsWith("/") ? path : `/${path}`}`;

  const res = await fetch(url, {
    ...init,
    credentials: withCredentials ? "include" : "omit",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...init.headers,
    },
  });

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
