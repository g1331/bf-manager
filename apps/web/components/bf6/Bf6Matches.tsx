"use client";

/**
 * 对局估算：后台定时重读生涯，两次之间的变化记成一条。只打了一局时能对上地图、模式和胜负；
 * 间隔里打了几局就合并成「N 场」，只列各模式的场次。按天分组，最新的在上。
 */
import { useQuery } from "@tanstack/react-query";
import type { Bf6MatchEstimate } from "@/lib/api/bf6";
import { kitInfo, mapInfo, modeInfo, vehicleInfo, weaponInfo } from "@/lib/bf6/catalog";
import { fmtFixed, fmtInt } from "@/lib/bf6/format";
import { bf6Queries } from "@/lib/queries/bf6";
import { cn } from "@/lib/utils";
import { Empty } from "./Bf6Maps";
import { MaskIcon } from "./primitives";

export function MatchesTab({ nucleusId }: { nucleusId: number }) {
  const q = useQuery(bf6Queries.matches(nucleusId));
  if (q.isLoading) {
    return (
      <div className="grid gap-2.5">
        {[0, 1, 2].map((i) => (
          <div key={i} className="border-bf6-line bg-bf6-panel h-[92px] animate-pulse border" />
        ))}
      </div>
    );
  }
  if (!q.data) return <Empty text="对局加载失败，请稍后重试" />;

  const { matches, tracking, tracked_since } = q.data;
  if (matches.length === 0) {
    return (
      <Empty
        text={
          tracking && tracked_since
            ? `从 ${fmtDateTime(tracked_since)} 开始记录，之后打完的对局会显示在这里`
            : "还没有开始记录这名玩家，稍后再打开这一页"
        }
      />
    );
  }
  return (
    <div>
      <div className="grid gap-6">
        {groupByDay(matches).map((g) => (
          <section key={g.key}>
            <h3 className="text-bf6-fg mb-2.5 flex items-baseline justify-between gap-3 text-[13px] font-bold tracking-[0.06em]">
              {g.label}
              <span className="text-bf6-mute text-xs font-normal tracking-normal tabular-nums">
                {sum(g.items, "matches")} 场 · {sum(g.items, "wins")} 胜
              </span>
            </h3>
            <ol className="grid gap-2.5">
              {g.items.map((m) => (
                <li key={m.id}>
                  <MatchCard match={m} />
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
      <p className="text-bf6-mute mt-4 text-xs">
        按两次读取之间的生涯变化估算，间隔内打的几局会合并成一条；时间是读到变化的时刻。保留 90 天。
      </p>
    </div>
  );
}

type Outcome = "win" | "loss" | "merged" | "partial";

function outcomeOf(m: Bf6MatchEstimate): Outcome {
  if (m.matches === 0) return "partial";
  if (m.matches > 1) return "merged";
  return m.wins > 0 ? "win" : m.losses > 0 ? "loss" : "merged";
}

const OUTCOME: Record<Outcome, { label: (m: Bf6MatchEstimate) => string; className: string }> = {
  win: { label: () => "胜利", className: "border-bf6-win text-bf6-win" },
  loss: { label: () => "失败", className: "border-bf6-loss text-bf6-loss" },
  merged: {
    label: (m) => (m.wins || m.losses ? `${m.wins} 胜 ${m.losses} 负` : `${m.matches} 场`),
    className: "border-bf6-line-strong text-bf6-fg2",
  },
  partial: { label: () => "未计场次", className: "border-bf6-line-strong text-bf6-mute" },
};

function MatchCard({ match: m }: { match: Bf6MatchEstimate }) {
  const outcome = outcomeOf(m);
  const single = m.matches === 1;
  const map = single && m.maps[0] ? mapInfo(m.maps[0].id) : null;
  const mode = m.modes[0] ? modeInfo(m.modes[0].id) : null;
  const backdrop = map?.img ?? mode?.art ?? null;
  const kit = m.kit ? kitInfo(m.kit) : null;
  const weapon = m.weapons[0];
  const vehicle = m.vehicles.find((v) => v.kills > 0);

  const title = single
    ? (map?.zh ?? mode?.name ?? "1 场")
    : m.matches > 1
      ? `${m.matches} 场`
      : "未完成的对局";
  const subtitle = single
    ? mode?.name
    : m.modes
        .map((s) => (s.matches > 1 ? `${modeInfo(s.id).name} ×${s.matches}` : modeInfo(s.id).name))
        .join("、");

  return (
    <div
      className={cn(
        "border-bf6-line bg-bf6-panel relative grid grid-cols-1 overflow-hidden border sm:grid-cols-[minmax(0,1fr)_auto]",
        outcome === "win" && "border-l-bf6-win border-l-2",
        outcome === "loss" && "border-l-bf6-loss border-l-2",
      )}
    >
      {backdrop ? (
        <div
          aria-hidden
          className="absolute inset-y-0 left-0 w-[70%] bg-cover bg-center opacity-35 sm:w-[46%]"
          style={{ backgroundImage: `url(${backdrop})` }}
        >
          <div className="from-bf6-panel/0 to-bf6-panel absolute inset-0 bg-gradient-to-r from-10%" />
        </div>
      ) : null}

      <div className="relative flex min-w-0 items-center gap-3 px-4 pt-3 sm:py-3">
        {kit?.icon ? <MaskIcon src={kit.icon} className="text-bf6-fg2 size-7 shrink-0" /> : null}
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <b className="text-bf6-fg truncate text-base font-extrabold tracking-[0.04em]">
              {title}
            </b>
            <span
              className={cn(
                "shrink-0 border px-1.5 py-px text-[11px] leading-4 tracking-[0.08em]",
                OUTCOME[outcome].className,
              )}
            >
              {OUTCOME[outcome].label(m)}
            </span>
          </div>
          <div className="text-bf6-mute mt-0.5 truncate text-xs">
            {[subtitle, timeRange(m)].filter(Boolean).join(" · ")}
          </div>
          {weapon || vehicle ? (
            <div className="text-bf6-fg2 mt-1.5 truncate text-xs">
              {weapon ? (
                <span>
                  {weaponInfo(weapon.id).name}
                  {weapon.kills ? ` ${weapon.kills} 杀` : ""}
                </span>
              ) : null}
              {weapon && vehicle ? <span className="text-bf6-mute"> · </span> : null}
              {vehicle ? (
                <span>
                  {vehicleInfo(vehicle.id).name} {vehicle.kills} 杀
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <dl className="relative grid grid-cols-5 gap-x-3 px-4 pt-2.5 pb-3 sm:flex sm:items-center sm:gap-x-6 sm:py-3">
        <Cell label="击杀" value={fmtInt(m.human_kills)} />
        <Cell label="死亡" value={fmtInt(m.deaths)} />
        <Cell label="K/D" value={m.kd == null ? "—" : fmtFixed(m.kd)} accent />
        <Cell label="得分" value={fmtInt(m.score)} />
        <Cell label="时长" value={fmtMinutes(m.time_seconds)} />
      </dl>
    </div>
  );
}

function Cell({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="min-w-0 sm:w-14 sm:text-right">
      <dt className="text-bf6-mute text-[11px]">{label}</dt>
      <dd
        className={cn(
          "font-display truncate text-[17px] font-medium tabular-nums",
          accent ? "text-bf6" : "text-bf6-fg",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function sum(items: Bf6MatchEstimate[], key: "matches" | "wins"): number {
  return items.reduce((n, m) => n + m[key], 0);
}

function fmtMinutes(seconds: number): string {
  return seconds ? `${Math.max(1, Math.round(seconds / 60))}′` : "—";
}

function clock(d: Date): string {
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 ${clock(d)}`;
}

/** 对局结束在两次读取之间：同一天写 14:05–14:15，跨天只写读到的时刻 */
function timeRange(m: Bf6MatchEstimate): string {
  const from = new Date(m.started_after);
  const to = new Date(m.observed_at);
  return from.toDateString() === to.toDateString()
    ? `${clock(from)}–${clock(to)}`
    : `${fmtDateTime(m.started_after)} 后 · ${clock(to)} 读到`;
}

type DayGroup = { key: string; label: string; items: Bf6MatchEstimate[] };

/** 列表已按读到的时间从新到旧排好，相邻同一天的并成一组（按浏览器本地时区） */
function groupByDay(items: Bf6MatchEstimate[]): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const it of items) {
    const d = new Date(it.observed_at);
    const key = d.toDateString();
    const last = groups.at(-1);
    if (last?.key === key) last.items.push(it);
    else groups.push({ key, label: dayLabel(d), items: [it] });
  }
  return groups;
}

function dayLabel(d: Date): string {
  const now = new Date();
  const startOfDay = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((startOfDay(now) - startOfDay(d)) / 86_400_000);
  const date = `${d.getMonth() + 1} 月 ${d.getDate()} 日`;
  if (days === 0) return `今天 · ${date}`;
  if (days === 1) return `昨天 · ${date}`;
  return date;
}
