/**
 * 鉴权 / 会话相关工具
 */
import { api, ApiException } from "./api-client";

export interface SessionUser {
  id: number;
  persona_id: number;
  display_name: string | null;
  avatar_url: string | null;
  role: "user" | "admin";
}

export interface SessionResponse {
  user: SessionUser | null;
}

export interface LoginRequest {
  remid: string;
  // sid 留空时 EA 会在登录响应里自动签发新 sid，因此设为可选
  sid?: string;
}

export interface LoginResponse {
  user: SessionUser;
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

export async function logout(): Promise<void> {
  await api.post("/auth/logout");
}
