"use client";

/**
 * EA 邮箱密码 + 2FA 登录任务的统一 UI 组件。
 *
 * - User 端用 ``actor="user"``，登录成功写入 ``ea_bindings``。
 * - Admin 端用 ``actor="admin"``，登录成功写入 ``ea_accounts``。
 *
 * 内部状态机：
 *   idle      -> submitting -> awaiting_method / awaiting_code -> finalizing -> done
 *                          \-> failed / cancelled
 *
 * 长轮询通过 ``eaLoginTasksApi.get(actor, taskId, sinceVersion)`` 驱动，每次拿到
 * 新版本立即重渲染。组件卸载或用户关闭时调用 ``cancel`` 释放后端任务资源。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ApiException } from "@/lib/api-client";
import {
  eaLoginTasksApi,
  isTerminalStatus,
  type EALoginTaskActor,
  type EALoginTaskResponse,
} from "@/lib/api/ea-login-tasks";

const loginSchema = z.object({
  email: z.string().email("邮箱格式错误"),
  password: z.string().min(1, "密码必填"),
});
type LoginValues = z.infer<typeof loginSchema>;

const codeSchema = z.object({
  code: z.string().min(1, "验证码必填"),
});
type CodeValues = z.infer<typeof codeSchema>;

interface Props {
  actor: EALoginTaskActor;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 登录成功时回调，外层用来 invalidate 列表查询。 */
  onSucceeded?: (task: EALoginTaskResponse) => void;
}

function describeError(err: unknown, fallback: string): string {
  return err instanceof ApiException ? err.message : fallback;
}

export function EaLoginFlow({ actor, open, onOpenChange, onSucceeded }: Props) {
  const [task, setTask] = useState<EALoginTaskResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // useRef 引用最新 task 供轮询循环读取，避免 useEffect 依赖 task 触发频繁重启
  const taskRef = useRef<EALoginTaskResponse | null>(null);
  taskRef.current = task;

  const loginForm = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const codeForm = useForm<CodeValues>({
    resolver: zodResolver(codeSchema),
    defaultValues: { code: "" },
  });

  // 关闭时重置整个流程，避免下次打开仍显示上次的成功页
  useEffect(() => {
    if (!open) {
      setTask(null);
      setSubmitting(false);
      loginForm.reset({ email: "", password: "" });
      codeForm.reset({ code: "" });
    }
  }, [open, loginForm, codeForm]);

  // 长轮询：当任务存在且未终态时，持续 long-poll
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const loop = async () => {
      while (!cancelled) {
        const current = taskRef.current;
        if (!current || isTerminalStatus(current.status)) break;
        try {
          const next = await eaLoginTasksApi.get(actor, current.task_id, current.version);
          if (cancelled) break;
          setTask(next);
          if (next.status === "succeeded") {
            onSucceeded?.(next);
            toast.success("EA 登录成功");
          }
          if (next.status === "failed") {
            toast.error(next.error_message ?? "登录失败");
          }
        } catch (err) {
          if (cancelled) break;
          toast.error(describeError(err, "轮询任务状态失败"));
          break;
        }
      }
    };
    loop();
    return () => {
      cancelled = true;
    };
  }, [open, actor, task?.task_id, onSucceeded]);

  // 用户主动关闭时尽量通知后端取消，节约 EA 风控配额
  const closeAndMaybeCancel = useCallback(
    async (nextOpen: boolean) => {
      if (!nextOpen && task && !isTerminalStatus(task.status)) {
        try {
          await eaLoginTasksApi.cancel(actor, task.task_id);
        } catch {
          // 后端 404 / 任务已终态都无所谓
        }
      }
      onOpenChange(nextOpen);
    },
    [task, actor, onOpenChange],
  );

  const onSubmitCredentials = loginForm.handleSubmit(async (values) => {
    setSubmitting(true);
    try {
      const created = await eaLoginTasksApi.create(actor, values);
      setTask(created);
    } catch (err) {
      toast.error(describeError(err, "创建登录任务失败"));
    } finally {
      setSubmitting(false);
    }
  });

  const onSelectMethod = async (method: string) => {
    if (!task) return;
    setSubmitting(true);
    try {
      const next = await eaLoginTasksApi.submitMethod(actor, task.task_id, method);
      setTask(next);
    } catch (err) {
      toast.error(describeError(err, "选择验证方式失败"));
    } finally {
      setSubmitting(false);
    }
  };

  const onSubmitCode = codeForm.handleSubmit(async (values) => {
    if (!task) return;
    setSubmitting(true);
    try {
      const next = await eaLoginTasksApi.submitCode(actor, task.task_id, values.code);
      setTask(next);
    } catch (err) {
      toast.error(describeError(err, "提交验证码失败"));
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <Sheet open={open} onOpenChange={(v) => void closeAndMaybeCancel(v)}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>
            {actor === "user" ? "邮箱密码绑定 EA 账号" : "邮箱密码新增 EA 账号"}
          </SheetTitle>
          <SheetDescription>
            登录链路完全在 bf-manager 内执行，明文邮箱、密码、验证码均不落盘；登录成功 后凭据以
            AES-256-GCM 加密后入库。
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-4 p-4">
          {task === null ? (
            <Form {...loginForm}>
              <form onSubmit={onSubmitCredentials} className="space-y-4">
                <FormField
                  control={loginForm.control}
                  name="email"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>EA 账号邮箱</FormLabel>
                      <FormControl>
                        <Input type="email" autoComplete="email" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={loginForm.control}
                  name="password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>EA 账号密码</FormLabel>
                      <FormControl>
                        <Input type="password" autoComplete="current-password" {...field} />
                      </FormControl>
                      <FormDescription>
                        密码仅用于完成本次 EA 登录链路，不会保存或上传任何明文。
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <SheetFooter>
                  <Button type="submit" disabled={submitting}>
                    {submitting ? "提交中…" : "开始登录"}
                  </Button>
                </SheetFooter>
              </form>
            </Form>
          ) : (
            <TaskProgress
              task={task}
              submitting={submitting}
              onSelectMethod={onSelectMethod}
              codeForm={codeForm}
              onSubmitCode={onSubmitCode}
            />
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function TaskProgress({
  task,
  submitting,
  onSelectMethod,
  codeForm,
  onSubmitCode,
}: {
  task: EALoginTaskResponse;
  submitting: boolean;
  onSelectMethod: (method: string) => void;
  codeForm: ReturnType<typeof useForm<CodeValues>>;
  onSubmitCode: () => void;
}) {
  switch (task.status) {
    case "pending":
    case "finalizing":
      return (
        <div className="text-muted-foreground space-y-2 text-sm">
          <p>
            正在与 EA 通信…（状态：<code>{task.status}</code>）
          </p>
          <p className="text-xs">如果长时间无反应，可关闭本面板再重试；后端任务将被自动取消。</p>
        </div>
      );
    case "awaiting_2fa_method":
      return (
        <div className="space-y-3">
          <p className="text-sm">EA 提供了多种二次验证方式，请选一种：</p>
          <div className="flex flex-wrap gap-2">
            {task.available_methods.map((m) => (
              <Button
                key={m}
                variant="outline"
                disabled={submitting}
                onClick={() => onSelectMethod(m)}
              >
                {labelOfMethod(m)}
              </Button>
            ))}
          </div>
        </div>
      );
    case "awaiting_2fa_code":
      return (
        <Form {...codeForm}>
          <form onSubmit={onSubmitCode} className="space-y-4">
            <div className="text-sm">
              <p>
                EA 已经发送验证码到{" "}
                <span className="font-medium">
                  {task.masked_destination || labelOfMethod(task.selected_method)}
                </span>
                ，请在 5 分钟内填写：
              </p>
            </div>
            <FormField
              control={codeForm.control}
              name="code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>验证码</FormLabel>
                  <FormControl>
                    <Input
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={12}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <SheetFooter>
              <Button type="submit" disabled={submitting}>
                {submitting ? "提交中…" : "提交验证码"}
              </Button>
            </SheetFooter>
          </form>
        </Form>
      );
    case "succeeded":
      return (
        <div className="space-y-2 text-sm">
          <p className="text-base font-medium text-green-600">EA 登录成功</p>
          {task.result ? (
            <p className="text-muted-foreground">
              persona_id {task.result.persona_id}
              {task.result.display_name ? ` · ${task.result.display_name}` : ""}
            </p>
          ) : null}
          <p className="text-muted-foreground text-xs">
            可关闭本面板。凭据已加密保存到对应账号体系。
          </p>
        </div>
      );
    case "failed":
      return (
        <div className="space-y-2 text-sm">
          <p className="text-base font-medium text-red-600">登录失败</p>
          <p className="text-muted-foreground">
            {task.error_message ?? task.error_code ?? "未知错误"}
          </p>
          <p className="text-muted-foreground text-xs">关闭面板后可重新发起。</p>
        </div>
      );
    case "cancelled":
      return (
        <div className="text-muted-foreground space-y-2 text-sm">
          <p>任务已取消。</p>
        </div>
      );
    default:
      return null;
  }
}

function labelOfMethod(method: string | null): string {
  switch (method) {
    case "EMAIL":
      return "邮箱";
    case "APP":
      return "EA App";
    case "SMS":
      return "短信";
    default:
      return method ?? "";
  }
}
