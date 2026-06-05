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

// 长轮询失败自愈策略：最多重试 N 次，指数退避加 ±20% jitter；只对瞬时错误重试。
// 4xx 确定性错误立即报错；POST 提交类（submitMethod / submitCode）永远不重试，避免重复
// 提交验证码触发 EA 风控。POST 仍然走业务侧错误处理，不在此处理。
const MAX_RETRY_ATTEMPTS = 5;
const BASE_DELAY_MS = 500;
const MAX_DELAY_MS = 8000;
// 服务端长轮询窗口为 ea_login_long_poll_seconds=25 秒，前端 fetch 超时设大一点的
// 35 秒上限，给 TLS / 反代层一点余量。超时由 AbortController 触发，进入 retry 流程。
const FETCH_TIMEOUT_MS = 35000;
const RETRY_TOAST_ID = "ea-login-retry";

function computeRetryDelay(attempt: number): number {
  const base = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
  const jitter = base * 0.2 * (Math.random() * 2 - 1);
  return Math.max(0, base + jitter);
}

function isRetryable(err: unknown): boolean {
  if (err instanceof ApiException) {
    const s = err.status;
    // 401（未登录）/ 403（权限）/ 404（任务不存在或非本人）/ 410（已清理）属于确定性失败
    if (s === 401 || s === 403 || s === 404 || s === 410) return false;
    // 5xx 与 429 视为瞬时故障，可退避重试
    if (s >= 500 || s === 429) return true;
    // 其余 4xx（如 422 / 400）属于请求侧错误，不重试
    return false;
  }
  // fetch 抛 TypeError / AbortError / 网络层错误：均视为瞬时，可重试
  return true;
}

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
  // onSucceeded 是父组件 props 函数引用，父组件 rerender 会换引用。把它放进 ref
  // 可避免它进 useEffect 依赖数组、避免反复 cancel / restart polling loop。
  const onSucceededRef = useRef(onSucceeded);
  onSucceededRef.current = onSucceeded;

  const loginForm = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const codeForm = useForm<CodeValues>({
    resolver: zodResolver(codeSchema),
    defaultValues: { code: "" },
  });

  // 关闭时重置整个流程，避免下次打开仍显示上次的成功页。
  // loginForm / codeForm 只作为方法调用对象，依赖语义为空，从 deps 中剔除以
  // 避免父组件 rerender 反复触发本 effect。
  useEffect(() => {
    if (!open) {
      setTask(null);
      setSubmitting(false);
      loginForm.reset({ email: "", password: "" });
      codeForm.reset({ code: "" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // 长轮询：任务未终态时持续 long-poll；瞬时错误退避重试，确定性错误立即报错。
  // 设计要点（与 PR 评审记录一致）：
  // - 每次 GET 配独立 AbortController + FETCH_TIMEOUT_MS 超时，避免连接堆积
  // - 退避用 abortable sleep，visibilitychange 与 cleanup 都能立即唤醒
  // - retryAttempt 在每次成功响应后清零，连续失败才计入预算
  // - 预算耗尽时 fire-and-forget cancel 后端任务，释放内存里的明文凭据
  // - 仅对 GET status 重试；submitMethod / submitCode / cancel 这类 POST 永不重试
  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    let inflightController: AbortController | null = null;
    let sleepController = new AbortController();

    const onVisibilityChange = () => {
      if (!document.hidden) {
        // 标签页回到前台：让正在退避的 sleep 立即结束，loop 进入下一次 GET。
        // 不直接发额外 GET，避免与正在进行的请求并发拉同一份状态。
        sleepController.abort();
        sleepController = new AbortController();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    const abortableSleep = (ms: number, signal: AbortSignal) =>
      new Promise<void>((resolve) => {
        if (signal.aborted) return resolve();
        const t = setTimeout(() => {
          signal.removeEventListener("abort", onAbort);
          resolve();
        }, ms);
        const onAbort = () => {
          clearTimeout(t);
          resolve();
        };
        signal.addEventListener("abort", onAbort, { once: true });
      });

    const loop = async () => {
      let retryAttempt = 0;
      while (!cancelled) {
        const current = taskRef.current;
        if (!current || isTerminalStatus(current.status)) break;

        inflightController = new AbortController();
        const fetchTimer = setTimeout(() => inflightController?.abort(), FETCH_TIMEOUT_MS);
        let next: EALoginTaskResponse;
        try {
          next = await eaLoginTasksApi.get(actor, current.task_id, current.version, {
            signal: inflightController.signal,
          });
        } catch (err) {
          clearTimeout(fetchTimer);
          if (cancelled) break;
          if (!isRetryable(err)) {
            // 4xx 等确定性错误：立刻报错并终止轮询
            toast.error(describeError(err, "轮询任务状态失败"));
            break;
          }
          if (retryAttempt >= MAX_RETRY_ATTEMPTS) {
            // 退避预算耗尽：报错 + fire-and-forget cancel，让后端立刻释放敏感数据
            toast.error(describeError(err, "轮询任务状态失败"), { id: RETRY_TOAST_ID });
            const tid = taskRef.current?.task_id;
            if (tid) {
              eaLoginTasksApi.cancel(actor, tid).catch(() => {});
            }
            break;
          }

          // 退避重试：交互态用中性 toast 不打扰用户，其它状态用错误样式 toast
          const interactive =
            current.status === "awaiting_2fa_method" || current.status === "awaiting_2fa_code";
          const attemptText = `连接中断，重试中… (${retryAttempt + 1}/${MAX_RETRY_ATTEMPTS})`;
          if (interactive) {
            toast(attemptText, { id: RETRY_TOAST_ID, duration: 3000 });
          } else {
            toast.error(attemptText, { id: RETRY_TOAST_ID, duration: 3000 });
          }

          const delay = computeRetryDelay(retryAttempt);
          retryAttempt += 1;
          await abortableSleep(delay, sleepController.signal);
          continue;
        }
        clearTimeout(fetchTimer);
        if (cancelled) break;

        // 成功响应：重置退避预算，dismiss 中间出现过的 retry toast。
        if (retryAttempt > 0) {
          toast.dismiss(RETRY_TOAST_ID);
        }
        retryAttempt = 0;

        setTask(next);
        if (next.status === "succeeded") {
          onSucceededRef.current?.(next);
          toast.success("EA 登录成功");
        }
        if (next.status === "failed") {
          toast.error(next.error_message ?? "登录失败");
        }
      }
    };

    loop();

    return () => {
      cancelled = true;
      sleepController.abort();
      inflightController?.abort();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      toast.dismiss(RETRY_TOAST_ID);
    };
  }, [open, actor, task?.task_id]);

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
    case "SECOND_EMAIL":
      return "备用邮箱";
    case "APP":
      return "EA App";
    case "SMS":
      return "短信";
    case "BACKUP_CODE":
      return "备用验证码";
    case "TRUSTED_DEVICE":
      return "受信任设备";
    default:
      return method ?? "";
  }
}
