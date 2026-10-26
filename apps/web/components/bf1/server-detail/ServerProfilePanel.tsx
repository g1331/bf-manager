"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, ShieldCheck } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { PlayerAvatar } from "@/components/common/PlayerAvatar";
import { bf1Api, type ServerExtras } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

/** 服务器档案：服主、战队、租期与各类 ID */
export function ServerProfilePanel({
  extras,
  now,
  game,
}: {
  extras: ServerExtras;
  now: number;
  game: string;
}) {
  const { owner, platoon, lifecycle } = extras;
  const created = lifecycle.created_at ? Date.parse(lifecycle.created_at) / 1000 : null;
  const expires = lifecycle.expires_at ? Date.parse(lifecycle.expires_at) / 1000 : null;
  const leftDays = expires ? Math.ceil((expires - now) / 86400) : null;
  const leftShare =
    created && expires && expires > created
      ? Math.min(Math.max((expires - now) / (expires - created), 0), 1)
      : null;
  // RSP 返回的服主头像为空，与成员名单共用批量头像接口补上
  const ownerId = owner?.persona_id;
  const ownerAvatar = useQuery({
    queryKey: ["bf1-avatars", [ownerId]],
    queryFn: () => bf1Api.getAvatars([ownerId!]),
    enabled: !!ownerId && !owner?.avatar_url,
    staleTime: 60 * 60_000,
  });

  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="h-full bg-black/45 p-5 backdrop-blur-sm sm:p-6"
    >
      <SectionHeading>服务器档案</SectionHeading>

      {owner?.display_name ? (
        <Row label="服主">
          <PlayerAvatar
            avatarUrl={owner.avatar_url || (ownerId ? ownerAvatar.data?.[ownerId] : null) || null}
            displayName={owner.display_name}
            size="sm"
          />
          {ownerId ? (
            <Link
              href={`/${game}/player/${ownerId}`}
              className="truncate text-white hover:text-amber-300"
            >
              {owner.display_name}
            </Link>
          ) : (
            <span className="truncate text-white">{owner.display_name}</span>
          )}
          {owner.platform ? (
            <span className="shrink-0 border border-white/20 px-1 text-[10px] leading-4 text-white/60">
              {owner.platform.toUpperCase()}
            </span>
          ) : null}
        </Row>
      ) : null}
      {extras.bookmark_count != null ? (
        <Row label="收藏">
          <span className="text-white tabular-nums">{extras.bookmark_count.toLocaleString()}</span>
        </Row>
      ) : null}

      {expires ? (
        <div className="mt-4 border-t border-white/10 pt-4">
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-white/45">租期</span>
            <span
              className={cn(
                "font-display text-lg font-semibold tabular-nums",
                leftDays != null && leftDays <= 7 ? "text-rose-400" : "text-white",
              )}
            >
              {leftDays != null && leftDays > 0 ? `剩余 ${leftDays} 天` : "已到期"}
            </span>
          </div>
          {leftShare != null ? (
            <div className="mt-2 h-1 bg-white/10">
              <div
                className={cn("h-full", leftShare < 0.1 ? "bg-rose-400" : "bg-amber-400")}
                style={{ width: `${leftShare * 100}%` }}
              />
            </div>
          ) : null}
          <div className="mt-1.5 flex justify-between text-[11px] text-white/40 tabular-nums">
            <span>{created ? formatDate(created) : ""}</span>
            <span>到期 {formatDate(expires)}</span>
          </div>
        </div>
      ) : null}

      {platoon?.name ? (
        <div className="mt-4 flex items-start gap-3 border-t border-white/10 pt-4">
          {platoon.emblem_url ? (
            // EA 徽章域不在 next/image remotePatterns 内，用原生 img
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={platoon.emblem_url}
              alt={platoon.name ?? "战队徽章"}
              className="size-12 shrink-0 object-contain"
              loading="lazy"
            />
          ) : (
            <ShieldCheck className="mt-0.5 size-5 shrink-0 text-amber-300/80" />
          )}
          <div className="min-w-0 text-sm">
            <div className="flex flex-wrap items-baseline gap-x-2">
              {platoon.guid ? (
                <Link
                  href={`/${game}/platoon/${platoon.guid}`}
                  className="font-medium text-white hover:text-amber-300"
                >
                  [{platoon.tag ?? "—"}] {platoon.name}
                </Link>
              ) : (
                <span className="font-medium text-white">
                  [{platoon.tag ?? "—"}] {platoon.name}
                </span>
              )}
              {platoon.size != null ? (
                <span className="text-xs text-white/45">{platoon.size} 人</span>
              ) : null}
            </div>
            {platoon.description ? (
              <p className="mt-1 line-clamp-3 text-xs leading-relaxed whitespace-pre-line text-white/55">
                {platoon.description}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="mt-4 space-y-1.5 border-t border-white/10 pt-4">
        {extras.game_id ? <IdRow label="GameID" value={String(extras.game_id)} /> : null}
        {extras.server_id ? <IdRow label="ServerID" value={String(extras.server_id)} /> : null}
        {extras.persisted_game_id ? (
          <IdRow label="PersistID" value={extras.persisted_game_id} />
        ) : null}
      </div>
    </Bf1Panel>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 py-1 text-sm">
      <span className="w-10 shrink-0 text-xs text-white/45">{label}</span>
      <span className="flex min-w-0 items-center gap-2">{children}</span>
    </div>
  );
}

function IdRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        });
      }}
      className="group flex w-full items-center gap-3 text-left text-xs"
      title="点击复制"
    >
      <span className="w-16 shrink-0 text-white/40">{label}</span>
      <span className="min-w-0 flex-1 truncate font-mono text-white/70 group-hover:text-white">
        {value}
      </span>
      {copied ? (
        <Check className="size-3.5 shrink-0 text-emerald-400" />
      ) : (
        <Copy className="size-3.5 shrink-0 text-white/25 group-hover:text-white/60" />
      )}
    </button>
  );
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}
