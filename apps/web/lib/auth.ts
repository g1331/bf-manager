/**
 * 鉴权 / 会话相关工具
 */
import { api, ApiException } from "./api-client";

export interface SessionBinding {
  id: number;
  persona_id: number;
  display_name: string | null;
  avatar_url: string | null;
  is_primary: boolean;
  is_frozen: boolean;
}

/**
 * - legacy：remid 登录时代建的旧账号，还没设置登录邮箱
 * - pending_binding：邮箱注册了但还没绑 EA，除绑定页外的功能都用不了
 */
export type AccountStatus = "legacy" | "pending_binding" | "active";

export interface SessionUser {
  id: number;
  username: string;
  role: "user" | "admin";
  email: string | null;
  status: AccountStatus;
  is_frozen: boolean;
  last_login_at: string | null;
  primary_binding: SessionBinding | null;
}

export interface SessionResponse {
  user: SessionUser | null;
}

export interface CookieBindRequest {
  remid: string;
  // sid 留空时 EA 会在登录响应里自动签发新 sid，因此设为可选
  sid?: string;
}

export interface CookieBindResponse {
  // true：这个 EA 号原来挂在旧账号上，已认领过去，需要用同样的邮箱密码重新登录
  claimed: boolean;
  persona_id: number;
  display_name: string | null;
}

export interface EmailLoginRequest {
  email: string;
  password: string;
}

/** open 开放注册 / invite 邀请注册 / closed 暂停注册（旧账号认领照常） */
export type RegistrationMode = "open" | "invite" | "closed";

export interface AuthConfig {
  registration_mode: RegistrationMode;
  invite_required: boolean;
  // 为 null 表示没启用人机验证
  turnstile_site_key: string | null;
}

export type RegisterMode = "ea" | "plain";

export interface RegisterRequest {
  email: string;
  mode: RegisterMode;
  invite_code?: string;
  /** 从群邀请链接过来注册：不用邀请码，验证后自动进群 */
  group_invite_token?: string;
}

export interface AcceptedResponse {
  message: string;
}

export type VerificationKind = "register" | "claim" | "reset" | "set_email";

export interface VerificationInfo {
  kind: VerificationKind;
  email: string;
  persona_name: string | null;
  mode: RegisterMode | null;
}

export type InviteStatus = "unused" | "used" | "expired" | "revoked";

export interface InviteCodeItem {
  id: number;
  code: string;
  status: InviteStatus;
  expires_at: string;
  used_at: string | null;
  created_at: string;
  /** 群邀请链接注册时记下的名额占用，不是能发给别人的码 */
  via_group_link: boolean;
}

export interface InviteCodeList {
  items: InviteCodeItem[];
  // 管理员不限，为 null
  quota_left: number | null;
  invite_required: boolean;
}

export interface LocalLoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  user: SessionUser;
}

export interface BindingListItem {
  id: number;
  persona_id: number;
  display_name: string | null;
  avatar_url: string | null;
  is_primary: boolean;
  is_frozen: boolean;
  last_verified_at: string | null;
}

export interface BindingListResponse {
  items: BindingListItem[];
}

export async function getSession(): Promise<SessionUser | null> {
  try {
    const res = await api.get<SessionResponse>("/auth/session");
    return res.user;
  } catch (err) {
    if (err instanceof ApiException && err.status === 401) return null;
    throw err;
  }
}

/** 带人机验证 token 的请求头；没启用 Turnstile 时 token 为 null，不带头 */
function captchaHeaders(token: string | null): HeadersInit | undefined {
  return token ? { "X-Turnstile-Token": token } : undefined;
}

export async function getAuthConfig(): Promise<AuthConfig> {
  return api.get<AuthConfig>("/auth/config");
}

export async function emailLogin(payload: EmailLoginRequest): Promise<SessionUser> {
  const res = await api.post<LoginResponse>("/auth/email-login", payload);
  return res.user;
}

export async function register(
  payload: RegisterRequest,
  captcha: string | null,
): Promise<AcceptedResponse> {
  return api.post<AcceptedResponse>("/auth/register", payload, {
    headers: captchaHeaders(captcha),
  });
}

export async function requestPasswordReset(
  email: string,
  captcha: string | null,
): Promise<AcceptedResponse> {
  return api.post<AcceptedResponse>(
    "/auth/password-reset",
    { email },
    { headers: captchaHeaders(captcha) },
  );
}

export async function lookupVerification(token: string): Promise<VerificationInfo> {
  return api.post<VerificationInfo>("/auth/verifications/lookup", { token });
}

export async function confirmVerification(token: string, password: string): Promise<SessionUser> {
  const res = await api.post<LoginResponse>("/auth/verifications/confirm", { token, password });
  return res.user;
}

export async function bindWithCookie(payload: CookieBindRequest): Promise<CookieBindResponse> {
  return api.post<CookieBindResponse>("/me/ea-bindings/cookie", payload);
}

/** 申请注销：账号立即冻结并退出登录，冷静期后删除 */
export async function requestAccountDeletion(
  password: string,
  confirm: string,
): Promise<{ delete_at: string }> {
  return api.post<{ delete_at: string }>("/me/delete-account", { password, confirm });
}

/** 冷静期内撤销注销并登录 */
export async function cancelAccountDeletion(payload: EmailLoginRequest): Promise<SessionUser> {
  const res = await api.post<LoginResponse>("/auth/cancel-deletion", payload);
  return res.user;
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await api.post("/me/password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

export async function requestSetEmail(
  email: string,
  captcha: string | null,
): Promise<AcceptedResponse> {
  return api.post<AcceptedResponse>("/me/email", { email }, { headers: captchaHeaders(captcha) });
}

export async function logoutAll(): Promise<void> {
  await api.post("/auth/logout-all");
}

export async function listInviteCodes(): Promise<InviteCodeList> {
  return api.get<InviteCodeList>("/me/invite-codes");
}

export async function createInviteCode(): Promise<InviteCodeList> {
  return api.post<InviteCodeList>("/me/invite-codes");
}

export async function revokeInviteCode(id: number): Promise<InviteCodeList> {
  return api.post<InviteCodeList>(`/me/invite-codes/${id}/revoke`);
}

export async function localLogin(payload: LocalLoginRequest): Promise<SessionUser> {
  const res = await api.post<LoginResponse>("/auth/local-login", payload);
  return res.user;
}

export async function logout(): Promise<void> {
  await api.post("/auth/logout");
}

export async function listMyBindings(): Promise<BindingListItem[]> {
  const res = await api.get<BindingListResponse>("/me/ea-bindings");
  return res.items;
}

export async function unbindEa(bindingId: number): Promise<void> {
  await api.post(`/me/ea-bindings/${bindingId}/unbind`);
}

/** 登录后去哪：还没绑 EA 的先去绑定页，其余回到原来要去的页面 */
export function landingPath(user: SessionUser, next: string): string {
  return user.status === "pending_binding" ? "/bind" : next;
}
