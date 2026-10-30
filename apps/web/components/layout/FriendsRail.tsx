"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { UsersRound, UserPlus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSession } from "@/hooks/useSession";
import { PlayerAvatar } from "@/components/common/PlayerAvatar";
import {
  groupsApi,
  type GroupPresence,
  type MemberServer,
  type PresenceMember,
  type PresenceSlot,
} from "@/lib/api/groups";

/**
 * 右侧好友 / 派对侧栏，默认收起：
 *   收起时只占一条窄边，顶部留一个图标入口，主内容尽量铺开；
 *   点击入口后面板从舞台右缘滑出，浮在主内容之上，不挤压布局。
 *   点面板外、按 Esc 或点关闭按钮都会收起。面板与内容之间不画竖线分隔——大厅本身没有这条线。
 *
 * 面板列出我所在各群的其他成员此刻在哪个服。数据来自全服快照的名单，每分钟一轮，
 * 所以只认得「在某个有人的服里」，离线和停在主菜单都算不在服内。
 */
export function FriendsRail() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLElement>(null);
  const session = useSession();
  const active = session.data?.status === "active";
  const presence = useQuery({
    queryKey: ["groups", "presence"],
    queryFn: groupsApi.presence,
    enabled: active,
    // 后端快照每分钟一轮，收起时也轮询，入口上的在服人数才跟得上
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  const playing = countPlaying(presence.data);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <aside ref={rootRef} className="sticky top-0 z-50 hidden h-screen w-14 shrink-0 lg:block">
      {/* 收起态：入口贴顶部 header 行、紧邻账户区，作为右上角社交入口 */}
      <div className="flex justify-center pt-6">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={cn(
            "relative flex size-9 items-center justify-center rounded-full transition-colors hover:text-white",
            open ? "text-white" : "text-white/55",
          )}
          aria-label={playing ? `好友与派对，${playing} 人在服` : "好友与派对"}
          aria-expanded={open}
          aria-controls="friends-panel"
          title="好友与派对"
        >
          <UsersRound className="size-5" />
          {playing ? (
            <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-emerald-500 px-1 text-[10px] leading-none font-semibold text-black tabular-nums">
              {playing}
            </span>
          ) : null}
        </button>
      </div>

      {/* 展开态：从舞台右缘滑出、浮在主内容之上；舞台 overflow-hidden 会裁掉收起时移出的部分 */}
      <div
        id="friends-panel"
        className={cn(
          "absolute inset-y-0 right-0 w-72 bg-black/80 backdrop-blur-md transition-[opacity,translate] duration-300",
          open ? "translate-x-0 opacity-100" : "pointer-events-none translate-x-full opacity-0",
        )}
        aria-hidden={!open}
        inert={!open}
      >
        <div className="flex h-full flex-col pt-6">
          <div className="flex h-9 items-center gap-2.5 px-5">
            <UsersRound className="size-5 text-white/70" />
            <span className="font-display text-sm font-semibold tracking-[0.18em] text-white/85 uppercase">
              好友与派对
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="-mr-2 ml-auto flex size-9 items-center justify-center rounded-full text-white/55 transition-colors hover:text-white"
              aria-label="收起好友与派对"
            >
              <X className="size-5" />
            </button>
          </div>

          <span className="mx-5 mt-4 h-px bg-white/10" aria-hidden />

          <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-6">
            {!session.data ? (
              <Hint>登录后可在此查看群成员在哪个服。</Hint>
            ) : !active ? (
              <Hint>绑定 EA 账号后可在此查看群成员在哪个服。</Hint>
            ) : presence.isPending ? (
              <PanelSkeleton />
            ) : presence.isError ? (
              <Hint>加载失败，稍后会自动重试。</Hint>
            ) : presence.data.groups.length === 0 ? (
              <Hint>
                加入或创建群组后，这里会显示群成员在哪个服。
                <Link
                  href="/me/groups"
                  onClick={() => setOpen(false)}
                  className="mt-3 block text-amber-400 hover:text-amber-300"
                >
                  去看看我的群组
                </Link>
              </Hint>
            ) : (
              <GroupList data={presence.data} onNavigate={() => setOpen(false)} />
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}

function countPlaying(data: GroupPresence | undefined): number {
  if (!data) return 0;
  // 同一个人可能同时在几个群里，按人去重
  const ids = new Set<number>();
  for (const g of data.groups) {
    for (const m of g.members) if (m.server) ids.add(m.user_id);
  }
  return ids.size;
}

function Hint({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-10 flex flex-col items-center gap-3 text-center">
      <UserPlus className="size-7 text-white/25" />
      <div className="text-sm leading-relaxed text-white/45">{children}</div>
    </div>
  );
}

function PanelSkeleton() {
  return (
    <div className="mt-5 space-y-4" aria-hidden>
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="size-9 animate-pulse rounded-full bg-white/10" />
          <div className="h-3 flex-1 animate-pulse rounded bg-white/10" />
        </div>
      ))}
    </div>
  );
}

function GroupList({ data, onNavigate }: { data: GroupPresence; onNavigate: () => void }) {
  // 快照不可用时谁在不在服都不知道，不能写成「不在服内」
  const unknown = data.updated_at === null;
  return (
    <>
      {unknown ? (
        <p className="mt-4 text-xs leading-relaxed text-amber-400/80">
          在服状态暂不可用，全服快照恢复后自动更新。
        </p>
      ) : null}
      {data.groups.map((g) => {
        const playing = g.members.filter((m) => m.server).length;
        return (
          <section key={g.id} className="mt-5">
            <div className="flex items-baseline justify-between gap-2">
              <Link
                href={`/me/groups/${g.id}`}
                onClick={onNavigate}
                className="compact-action truncate text-xs font-semibold tracking-wider text-white/60 hover:text-white"
              >
                {g.name}
              </Link>
              {unknown ? null : (
                <span className="shrink-0 text-[11px] text-white/35 tabular-nums">
                  {playing}/{g.members.length} 在服
                </span>
              )}
            </div>
            {g.members.length === 0 ? (
              <p className="mt-2 text-xs text-white/35">群里还没有其他成员。</p>
            ) : (
              <ul className="-mx-2 mt-1.5">
                {g.members.map((m) => (
                  <li key={m.user_id}>
                    <MemberRow member={m} unknown={unknown} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
      <p className="mt-6 text-[11px] leading-relaxed text-white/30">
        每分钟更新一次。离线或停在主菜单的成员都显示为不在服内。
      </p>
    </>
  );
}

const SLOT_LABEL: Partial<Record<PresenceSlot, string>> = {
  queue: "排队",
  spectator: "观战",
};

function MemberRow({
  member,
  unknown,
  onNavigate,
}: {
  member: PresenceMember;
  unknown: boolean;
  onNavigate: () => void;
}) {
  const name = member.display_name ?? member.username;
  const { server } = member;
  const href = server
    ? `/bf1/server/${server.game_id}`
    : member.persona_id
      ? `/bf1/player/${member.persona_id}`
      : null;

  const body = (
    <>
      <div className="relative">
        <PlayerAvatar avatarUrl={member.avatar_url} displayName={name} size="sm" />
        {server ? (
          <span className="absolute -right-0.5 -bottom-0.5 size-3 rounded-full border-2 border-black bg-emerald-500" />
        ) : null}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className={cn("truncate text-sm", server ? "text-white" : "text-white/55")}>
            {name}
          </span>
          {server && SLOT_LABEL[server.slot] ? (
            <span className="shrink-0 rounded-sm bg-white/10 px-1 text-[10px] text-white/60">
              {SLOT_LABEL[server.slot]}
            </span>
          ) : null}
        </div>
        {server ? (
          <ServerLine server={server} />
        ) : (
          <div className="text-xs text-white/30">{unknown ? "状态未知" : "不在服内"}</div>
        )}
      </div>
    </>
  );

  const rowClass = "flex items-center gap-3 rounded-md px-2 py-2";
  return href ? (
    <Link
      href={href}
      onClick={onNavigate}
      className={cn(rowClass, "transition-colors hover:bg-white/[0.06]")}
      title={server?.name ?? undefined}
    >
      {body}
    </Link>
  ) : (
    <div className={rowClass}>{body}</div>
  );
}

function ServerLine({ server }: { server: MemberServer }) {
  const detail = [
    server.map_display_name,
    server.mode_display_name,
    server.player_count != null && server.max_player_count
      ? `${server.player_count}/${server.max_player_count}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <>
      <div className="truncate text-xs text-emerald-400/90">{server.name ?? "在服中"}</div>
      {detail ? <div className="truncate text-[11px] text-white/40">{detail}</div> : null}
    </>
  );
}
