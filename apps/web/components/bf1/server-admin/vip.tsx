"use client";

/**
 * 计时 VIP 的共用件：按托管视图判断一名玩家的 VIP 状态、时长文案、状态徽标与时长选择器。
 *
 * 平台只托管限时 VIP 和行动服的待生效队列；EA 名单里没有托管记录的 VIP 一律按永久处理。
 */

import { useState } from "react";
import { Input } from "@/components/ui/input";
import type { TimedVipItem, TimedVipView } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

export type VipStatus =
  | { kind: "none" }
  | { kind: "permanent" }
  | { kind: "timed"; item: TimedVipItem }
  | { kind: "pending"; item: TimedVipItem };

export function vipStatusOf(view: TimedVipView | undefined, personaId: number): VipStatus {
  if (!view) return { kind: "none" };
  const item = view.items.find((i) => i.persona_id === personaId);
  if (item) return item.status === "pending" ? { kind: "pending", item } : { kind: "timed", item };
  return view.vip_ids.includes(personaId) ? { kind: "permanent" } : { kind: "none" };
}

/** 永久 VIP（名单里没有托管记录的）和排队中的永久 VIP：设天数会改成限时，需要确认 */
export function isPermanentVip(status: VipStatus): boolean {
  return (
    status.kind === "permanent" ||
    (status.kind === "pending" && status.item.remaining_seconds === null)
  );
}

/** 秒数 → 「3 天 5 小时」「5 小时」「20 分钟」 */
export function formatSpan(seconds: number): string {
  const s = Math.max(seconds, 0);
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  if (days > 0) return hours ? `${days} 天 ${hours} 小时` : `${days} 天`;
  if (hours > 0) return `${hours} 小时`;
  return `${Math.max(Math.ceil(s / 60), 1)} 分钟`;
}

export function formatExpiry(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/**
 * 名单行上的状态徽标；永久 VIP 占名单大多数，不打标记。operation 决定已到期时提示
 * 「等立即生效」还是「自动下 V 失败」。
 */
export function VipBadge({ status, operation }: { status: VipStatus; operation: boolean }) {
  if (status.kind === "none" || status.kind === "permanent") return null;
  const { item } = status;
  if (status.kind === "pending") {
    const span =
      item.remaining_seconds === null ? "永久" : `剩 ${formatSpan(item.remaining_seconds)}`;
    return (
      <Badge className="border-sky-400/40 text-sky-200">
        待生效 · {span}
        {item.queue_position ? ` · 第 ${item.queue_position} 位` : ""}
      </Badge>
    );
  }
  if (item.expired) {
    return operation ? (
      <Badge className="border-rose-400/40 text-rose-200">已到期 · 等立即生效</Badge>
    ) : (
      <Badge className="border-rose-400/40 text-rose-200" title={item.last_error ?? undefined}>
        到期未移除
      </Badge>
    );
  }
  return (
    <Badge
      className="border-amber-400/40 text-amber-200"
      title={item.expires_at ? `${formatExpiry(item.expires_at)} 到期` : undefined}
    >
      剩 {formatSpan(item.remaining_seconds ?? 0)}
    </Badge>
  );
}

function Badge({
  className,
  title,
  children,
}: {
  className?: string;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      title={title}
      className={cn("max-w-full truncate border px-1.5 text-[10px] leading-4", className)}
    >
      {children}
    </span>
  );
}

const PRESETS: (number | null)[] = [null, 1, 3, 7, 30];
export const MAX_VIP_DAYS = 3650;

/** 自定义天数的合法性：整数、非 0、绝对值不超过上限；不允许负数时必须为正 */
export function isValidDays(days: number | null, allowNegative: boolean): boolean {
  if (days === null) return true;
  if (!Number.isInteger(days) || days === 0 || Math.abs(days) > MAX_VIP_DAYS) return false;
  return allowNegative || days > 0;
}

/**
 * 时长选择：永久 / 1 / 3 / 7 / 30 天 / 自定义。value 为 null 表示永久；
 * allowNegative 用于给已有期限的 VIP 改期（负数缩短）。
 */
export function VipDurationPicker({
  value,
  onChange,
  allowNegative = false,
  allowPermanent = true,
  label,
}: {
  value: number | null;
  onChange: (days: number | null) => void;
  allowNegative?: boolean;
  allowPermanent?: boolean;
  label: string;
}) {
  const presets = allowPermanent ? PRESETS : PRESETS.filter((p) => p !== null);
  const [custom, setCustom] = useState(() => !presets.includes(value));
  const [text, setText] = useState(() => (value === null ? "" : String(value)));

  const chip = (active: boolean) =>
    cn(
      "h-8 border px-3 text-sm transition-colors",
      // 确认框跟随主题（浅色），用主题色而不是详情页的暗色写死值
      active
        ? "border-primary bg-primary/10 text-primary font-medium"
        : "border-border text-foreground/75 hover:border-foreground/40",
    );

  return (
    <div className="space-y-2 py-2">
      <div className="text-sm font-medium">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {presets.map((p) => (
          <button
            key={String(p)}
            type="button"
            className={chip(!custom && value === p)}
            onClick={() => {
              setCustom(false);
              onChange(p);
            }}
          >
            {p === null ? "永久" : allowNegative ? `+${p} 天` : `${p} 天`}
          </button>
        ))}
        <button
          type="button"
          className={chip(custom)}
          onClick={() => {
            setCustom(true);
            const n = Number(text);
            onChange(text && Number.isFinite(n) ? n : NaN);
          }}
        >
          自定义
        </button>
      </div>
      {custom ? (
        <div className="flex items-center gap-2">
          <Input
            type="number"
            inputMode="numeric"
            value={text}
            autoFocus
            onChange={(e) => {
              setText(e.target.value);
              onChange(e.target.value === "" ? NaN : Number(e.target.value));
            }}
            placeholder={allowNegative ? "天数，负数为缩短" : "天数"}
            className="h-9 w-32"
          />
          <span className="text-muted-foreground text-sm">天</span>
          {!isValidDays(value, allowNegative) ? (
            <span className="text-destructive text-xs">
              {allowNegative ? "填非 0 整数" : "填正整数"}，最多 {MAX_VIP_DAYS} 天
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
