/**
 * EA 邮箱密码 + 2FA 登录任务的 API 客户端。
 *
 * 后端有两套对称端点：
 *   user  -> /me/ea-bindings/login-tasks/*
 *   admin -> /ea-accounts/login-tasks/*
 *
 * 用 ``actor`` 参数区分前缀；类型完全一致。
 */
import { api } from "@/lib/api-client";

export type EALoginTaskActor = "user" | "admin";

export type EALoginTaskStatus =
  | "pending"
  | "awaiting_2fa_method"
  | "awaiting_2fa_code"
  | "finalizing"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface EALoginTaskResult {
  persona_id: number;
  display_name: string | null;
  avatar_url: string | null;
  binding_id: number | null;
  account_id: number | null;
}

export interface EALoginTaskResponse {
  task_id: string;
  status: EALoginTaskStatus;
  version: number;
  available_methods: string[];
  selected_method: string | null;
  masked_destination: string | null;
  error_code: string | null;
  error_message: string | null;
  result: EALoginTaskResult | null;
  created_at: string;
  updated_at: string;
}

export interface EALoginTaskCreateRequest {
  email: string;
  password: string;
}

const TERMINAL_STATUSES: ReadonlySet<EALoginTaskStatus> = new Set([
  "succeeded",
  "failed",
  "cancelled",
]);

export function isTerminalStatus(status: EALoginTaskStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

function basePath(actor: EALoginTaskActor): string {
  return actor === "user" ? "/me/ea-bindings/login-tasks" : "/ea-accounts/login-tasks";
}

export const eaLoginTasksApi = {
  create: (actor: EALoginTaskActor, payload: EALoginTaskCreateRequest) =>
    api.post<EALoginTaskResponse>(basePath(actor), payload),

  /**
   * 状态查询。提供 ``sinceVersion`` 时启用长轮询：服务端 hold 住直到 ``current >
   * sinceVersion`` 或到达 ``ea_login_long_poll_seconds``，到点返回当前快照由客户端
   * 自行续轮询。不提供时立即返回当前状态。
   *
   * 可选 ``signal`` 传入 ``AbortController.signal``：组件卸载或自定义超时触发时
   * abort 进行中的 fetch，避免连接堆积。
   */
  get: (
    actor: EALoginTaskActor,
    taskId: string,
    sinceVersion?: number,
    options?: { signal?: AbortSignal },
  ) => {
    const qs = sinceVersion !== undefined ? `?since_version=${sinceVersion}` : "";
    return api.get<EALoginTaskResponse>(`${basePath(actor)}/${taskId}${qs}`, options);
  },

  submitMethod: (actor: EALoginTaskActor, taskId: string, method: string) =>
    api.post<EALoginTaskResponse>(`${basePath(actor)}/${taskId}/2fa-method`, { method }),

  submitCode: (actor: EALoginTaskActor, taskId: string, code: string) =>
    api.post<EALoginTaskResponse>(`${basePath(actor)}/${taskId}/2fa-code`, { code }),

  cancel: (actor: EALoginTaskActor, taskId: string) =>
    api.post<EALoginTaskResponse>(`${basePath(actor)}/${taskId}/cancel`),
};
