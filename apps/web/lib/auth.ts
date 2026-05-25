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

export interface SessionUser {
  id: number;
  username: string;
  role: "user" | "admin";
  is_frozen: boolean;
  last_login_at: string | null;
  primary_binding: SessionBinding | null;
}

export interface SessionResponse {
  user: SessionUser | null;
}

export interface LoginRequest {
  remid: string;
  // sid 留空时 EA 会在登录响应里自动签发新 sid，因此设为可选
  sid?: string;
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

export async function login(payload: LoginRequest): Promise<SessionUser> {
  const res = await api.post<LoginResponse>("/auth/login", payload);
  return res.user;
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
