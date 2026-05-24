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
    let payload: { error?: ApiError } = {};
    try {
      payload = (await res.json()) as { error?: ApiError };
    } catch {
      // 非 JSON 响应
    }
    const apiError: ApiError = payload.error ?? {
      code: `HTTP_${res.status}`,
      message: res.statusText,
    };
    throw new ApiException(res.status, apiError);
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
