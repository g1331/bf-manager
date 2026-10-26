"use client";

/**
 * BF1 战队详情：基本信息、成员正在玩的服务器、按职位分组的全部成员。
 * 数据直接来自 EA（后端缓存 3 分钟），成员最多 100 人，一次取全。
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ShieldCheck, Users } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { PlayerAvatar } from "@/components/common/PlayerAvatar";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ApiException } from "@/lib/api-client";
import { bf1Api, type PlatoonDetail, type PlatoonMember, type PlatoonRole } from "@/lib/api/bf1";

const ROLE_LABEL: Record<PlatoonRole, string> = {
  general: "将军",
  colonel: "上校",
  lieutenant: "中尉",
  private: "列兵",
};

export default function PlatoonDetailPage() {
  const { game, guid } = useParams<{ game: string; guid: string }>();
  const detail = useQuery({
    queryKey: ["bf1-platoon", guid],
    queryFn: () => bf1Api.getPlatoonDetail(guid),
    staleTime: 60_000,
    retry: (count, err) => !(err instanceof ApiException && err.status === 404) && count < 2,
  });

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 text-white sm:px-6 sm:py-10">
      <Link
        href={`/${game}/platoons`}
        className="inline-flex items-center gap-1.5 text-sm text-white/55 transition-colors hover:text-white"
      >
        <ArrowLeft className="size-4" />
        战队搜索
      </Link>

      {detail.isLoading ? (
        <div className="space-y-6">
          <div className="h-40 animate-pulse bg-white/[0.06]" />
          <div className="h-64 animate-pulse bg-white/[0.06]" />
        </div>
      ) : !detail.data ? (
        <div className="border border-white/10 bg-black/40 px-4 py-10 text-center text-sm text-white/55">
          {detail.error instanceof ApiException && detail.error.status === 404
            ? "没有找到这个战队"
            : "战队加载失败，请稍后重试"}
        </div>
      ) : (
        <PlatoonView game={game} platoon={detail.data} />
      )}
    </main>
  );
}

function PlatoonView({ game, platoon }: { game: string; platoon: PlatoonDetail }) {
  // EA 成员列表的 avatar 基本为空，与服务器成员名单共用批量头像接口补上（战队最多 100 人）
  const ids = platoon.members.map((m) => m.persona_id);
  const avatars = useQuery({
    queryKey: ["bf1-avatars", ids],
    queryFn: () => bf1Api.getAvatars(ids),
    enabled: ids.length > 0,
    staleTime: 60 * 60_000,
  });
  const groups = (["general", "colonel", "lieutenant", "private"] as const)
    .map((role) => ({
      label: ROLE_LABEL[role],
      members: platoon.members.filter((m) => m.role === role),
    }))
    .concat({ label: "其他", members: platoon.members.filter((m) => m.role == null) })
    .filter((g) => g.members.length > 0);
  const join = platoon.free_join ? "自由加入" : platoon.can_apply ? "可申请加入" : "仅限邀请";

  return (
    <>
      <Bf1Panel
        variant="transparent"
        cut={24}
        corners={["topLeft", "bottomRight"]}
        className="bg-black/55 p-6 backdrop-blur-sm sm:p-8"
      >
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
          {platoon.emblem_url ? (
            // EA 徽章域不在 next/image remotePatterns 内，用原生 img
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={platoon.emblem_url}
              alt={platoon.name ?? "战队徽章"}
              className="size-28 shrink-0 object-contain"
            />
          ) : (
            <ShieldCheck className="size-28 shrink-0 p-6 text-white/20" />
          )}
          <div className="min-w-0">
            <h1 className="font-display flex flex-wrap items-baseline gap-x-3 text-3xl font-bold tracking-wide break-all sm:text-4xl">
              {platoon.tag ? <span className="text-white/45">[{platoon.tag}]</span> : null}
              <span>{platoon.name}</span>
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-white/55">
              <span className="flex items-center gap-1.5 tabular-nums">
                <Users className="size-3.5" />
                {platoon.size ?? platoon.members.length} 人
              </span>
              <span>{join}</span>
              {platoon.created_at ? (
                <span className="tabular-nums">
                  创建于 {new Date(platoon.created_at * 1000).toLocaleDateString("zh-CN")}
                </span>
              ) : null}
              {platoon.verified ? <span className="text-amber-300/90">已认证</span> : null}
            </div>
            {platoon.description ? (
              <p className="mt-3 max-w-3xl text-sm leading-relaxed whitespace-pre-line text-white/70">
                {platoon.description}
              </p>
            ) : null}
          </div>
        </div>
      </Bf1Panel>

      {platoon.servers.length > 0 ? (
        <section>
          <SectionHeading>正在游玩</SectionHeading>
          <ul className="grid gap-3 md:grid-cols-2">
            {platoon.servers.map(({ server, members }) => (
              <li key={server.game_id}>
                <Bf1Panel
                  variant="transparent"
                  cut={14}
                  corners={["bottomRight"]}
                  className="h-full border-l-2 border-emerald-400/60 bg-black/45 px-4 py-3.5 backdrop-blur-sm"
                >
                  <Link
                    href={`/${game}/server/${server.game_id}`}
                    className="block truncate font-semibold text-white hover:text-amber-300"
                  >
                    {server.name}
                  </Link>
                  <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-white/50 tabular-nums">
                    <span>{server.map_display_name ?? server.map_name}</span>
                    {server.mode_display_name ? <span>{server.mode_display_name}</span> : null}
                    <span>
                      {server.player_count}/{server.max_player_count}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {members.map((m) => (
                      <Link
                        key={m.persona_id}
                        href={`/${game}/player/${m.persona_id}`}
                        className="border border-white/15 px-1.5 text-xs leading-5 text-white/75 hover:border-white/40 hover:text-white"
                      >
                        {m.name}
                      </Link>
                    ))}
                  </div>
                </Bf1Panel>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="space-y-5">
        {groups.map((g) => (
          <div key={g.label}>
            <div className="mb-2 flex items-baseline gap-2">
              <SectionHeading className="mb-0">{g.label}</SectionHeading>
              <span className="text-xs text-white/40 tabular-nums">{g.members.length}</span>
            </div>
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {g.members.map((m) => (
                <MemberCard
                  key={m.persona_id}
                  game={game}
                  member={m}
                  avatarUrl={m.avatar_url || avatars.data?.[m.persona_id] || null}
                />
              ))}
            </ul>
          </div>
        ))}
        {groups.length === 0 ? <p className="text-sm text-white/45">成员列表暂时取不到</p> : null}
      </section>
    </>
  );
}

function MemberCard({
  game,
  member,
  avatarUrl,
}: {
  game: string;
  member: PlatoonMember;
  avatarUrl: string | null;
}) {
  return (
    <li>
      <Link
        href={`/${game}/player/${member.persona_id}`}
        className="flex items-center gap-3 border border-white/10 bg-black/40 px-3 py-2 transition-colors hover:border-white/30 hover:bg-white/[0.06]"
      >
        <PlayerAvatar avatarUrl={avatarUrl} displayName={member.name} size="sm" />
        <span className="truncate text-sm text-white">{member.name}</span>
      </Link>
    </li>
  );
}
