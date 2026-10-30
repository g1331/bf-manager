import { z } from "zod";

// 与后端 account_service.validate_password 一致
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;

export const newPasswordFields = {
  password: z
    .string()
    .min(PASSWORD_MIN, `密码至少 ${PASSWORD_MIN} 位`)
    .max(PASSWORD_MAX, `密码最多 ${PASSWORD_MAX} 位`),
  confirm: z.string(),
};

export function confirmMatches(v: { password: string; confirm: string }) {
  return v.password === v.confirm;
}

export const confirmMismatch = { message: "两次输入的密码不一致", path: ["confirm"] };
