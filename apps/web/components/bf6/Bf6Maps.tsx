/**
 * 地图与模式：地图卡用官方地图大图，禁区冲突单独一块大逃杀面板，模式按官方分组列出。
 */
import type { Bf6MapStats, Bf6ModeStats, Bf6PlayerStats, Bf6RedsecStats } from "@/lib/api/bf6";
import { BF6_ASSETS, MODE_GROUPS, mapInfo, modeInfo } from "@/lib/bf6/catalog";
import { fmtHours, fmtInt, fmtPct } from "@/lib/bf6/format";
import { cn } from "@/lib/utils";
import { MaskIcon, Panel, PanelTitle, Ring, SectionTitle, Stat, WinLossBar } from "./primitives";

export function nonRedsecMaps(maps: Bf6MapStats[]): Bf6MapStats[] {
  return maps.filter((m) => !mapInfo(m.id).redsec);
}

/* ------------------------------ 地图 ------------------------------ */

export function MapCard({
  map,
  rank,
  featured = false,
}: {
  map: Bf6MapStats;
  rank: number;
  featured?: boolean;
}) {
  const info = mapInfo(map.id);
  return (
    <div
      className={cn(
        "group border-bf6-line relative aspect-[16/9.4] overflow-hidden border bg-[#111]",
        featured && "lg:row-span-2 lg:aspect-auto",
      )}
    >
      {info.img ? (
        <img
          src={info.img}
          alt=""
          loading="lazy"
          className="absolute inset-0 size-full object-cover transition-transform duration-700 group-hover:scale-[1.04]"
        />
      ) : null}
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(10,11,12,0)_20%,rgba(10,11,12,0.55)_55%,rgba(10,11,12,0.96)_100%)]" />
      <span className="font-display border-bf6 bg-bf6-bg/70 text-bf6-fg absolute top-3 left-3.5 border-l-2 px-2 py-0.5 text-xs tracking-[0.2em]">
        #{String(rank).padStart(2, "0")}
      </span>
      <div className="absolute inset-x-4.5 bottom-3.5 [text-shadow:0_1px_8px_rgba(0,0,0,0.7)]">
        <div className="font-display text-bf6-fg2 text-[11px] tracking-[0.28em] uppercase">
          {info.en}
        </div>
        <div
          className={cn(
            "text-bf6-fg mt-0.5 font-extrabold tracking-[0.04em]",
            featured ? "text-2xl lg:text-[34px]" : "text-2xl",
          )}
        >
          {info.zh}
        </div>
        <div className="text-bf6-fg2 mt-2 flex items-end justify-between gap-2 text-xs">
          <span className="truncate">
            {fmtInt(map.matches)} 场 · {fmtInt(map.wins ?? 0)} 胜 {fmtInt(map.losses ?? 0)} 负 ·{" "}
            {fmtHours(map.time_seconds)} 小时
          </span>
          <span className="font-display text-bf6-fg shrink-0 text-[30px] leading-none font-semibold tabular-nums">
            {map.win_rate == null ? "—" : Math.round(map.win_rate * 100)}
            <small className="text-sm">%</small>
          </span>
        </div>
        <WinLossBar wins={map.wins} losses={map.losses} className="mt-2" />
      </div>
    </div>
  );
}

export function MapsTab({ stats }: { stats: Bf6PlayerStats }) {
  const maps = nonRedsecMaps(stats.maps);
  return (
    <div>
      {maps.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {maps.map((m, i) => (
            <MapCard key={m.id} map={m} rank={i + 1} />
          ))}
        </div>
      ) : (
        <Empty text="还没有多人地图的记录" />
      )}
      {stats.redsec ? (
        <>
          <SectionTitle index="RS" title="禁区冲突" en="REDSEC" />
          <RedsecPanel redsec={stats.redsec} />
        </>
      ) : null}
    </div>
  );
}

/* ------------------------------ 禁区冲突 ------------------------------ */

export function RedsecPanel({ redsec }: { redsec: Bf6RedsecStats }) {
  const map = mapInfo("ftpgranite");
  const podium = [
    { label: "吃鸡", value: redsec.wins ?? 0 },
    { label: "前三", value: redsec.top3 },
    { label: "前十", value: redsec.top10 },
  ];
  return (
    <Panel
      ticks={false}
      className="grid overflow-hidden lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]"
    >
      <div
        className="relative min-h-[200px] bg-cover bg-center lg:min-h-[300px]"
        style={{ backgroundImage: `url(${BF6_ASSETS.redsecArt})` }}
      >
        <div className="absolute inset-0 bg-[linear-gradient(180deg,transparent_40%,var(--color-bf6-panel)_100%)] lg:bg-[linear-gradient(90deg,transparent_40%,var(--color-bf6-panel)_100%)]" />
        <img
          src={BF6_ASSETS.redsecLogo}
          alt="REDSEC"
          className="absolute top-5 left-5.5 h-[34px]"
        />
        <div className="text-bf6-fg absolute bottom-4.5 left-5.5 text-[28px] font-extrabold">
          <small className="font-display text-bf6-fg2 block text-[11px] font-normal tracking-[0.3em] uppercase">
            {map.en}
          </small>
          {map.zh}
        </div>
      </div>
      <div className="px-4 py-5 sm:px-6 sm:py-5.5">
        <PanelTitle note={`${fmtInt(redsec.matches)} 场 · ${fmtHours(redsec.time_seconds)} 小时`}>
          大逃杀
        </PanelTitle>
        <div className="mt-4 grid grid-cols-3 gap-2.5">
          {podium.map((p, i) => (
            <div
              key={p.label}
              className={cn(
                "border px-3 py-3 text-center",
                i === 0 ? "border-bf6 bg-bf6/14" : "border-bf6-line-strong",
              )}
            >
              <span className="text-bf6-mute block text-[11px]">{p.label}</span>
              <b className="font-display text-bf6-fg block text-[30px] font-semibold tabular-nums">
                {fmtInt(p.value)}
              </b>
            </div>
          ))}
        </div>
        <div className="border-bf6-line mt-5.5 grid grid-cols-3 gap-x-4 gap-y-4.5 border-t pt-5">
          <Stat label="吃鸡率" value={fmtPct(redsec.win_rate)} />
          <Stat label="击杀" value={fmtInt(redsec.kills)} />
          <Stat label="最长连胜" value={fmtInt(redsec.longest_win_streak)} />
          <Stat label="单局团灭小队" value={fmtInt(redsec.round_squad_wipes)} />
          <Stat label="情报拾取" value={fmtInt(redsec.intel_pickups)} />
          <Stat label="单局开箱" value={fmtInt(redsec.round_chests)} />
        </div>
      </div>
    </Panel>
  );
}

/* ------------------------------ 模式 ------------------------------ */

function ModeRow({ mode }: { mode: Bf6ModeStats }) {
  const info = modeInfo(mode.id);
  return (
    <Panel
      ticks={false}
      className="grid grid-cols-[92px_1fr_auto] items-center gap-3 py-2.5 pr-4 pl-2.5 sm:grid-cols-[132px_1fr_auto] sm:gap-4"
    >
      <div
        className={cn(
          "border-bf6-line relative grid h-[60px] place-items-center border bg-[#0d0f10] bg-cover bg-center sm:h-[76px]",
          !info.art &&
            !info.icon &&
            "bg-[repeating-linear-gradient(115deg,rgba(255,90,31,0.08)_0_10px,transparent_10px_22px)]",
        )}
        style={info.art ? { backgroundImage: `url(${info.art})` } : undefined}
      >
        {info.art ? (
          <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(10,11,12,0.1),rgba(10,11,12,0.55))]" />
        ) : null}
        {info.icon ? (
          <MaskIcon
            src={info.icon}
            className="text-bf6-fg relative size-[38px] drop-shadow-[0_2px_4px_rgba(0,0,0,0.6)]"
          />
        ) : !info.art ? (
          <span className="text-bf6-mute font-mono text-[10px] tracking-[0.2em]">MODE</span>
        ) : null}
      </div>
      <div className="min-w-0">
        <div className="text-bf6-fg truncate text-base font-extrabold tracking-[0.04em] sm:text-lg">
          {info.name}
        </div>
        <small className="font-display text-bf6-mute block truncate text-[10px] tracking-[0.25em] uppercase">
          {info.en}
        </small>
        <div className="text-bf6-mute mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
          <span>
            <b className="font-display text-bf6-fg mr-0.5 text-base font-medium tabular-nums">
              {fmtInt(mode.matches)}
            </b>
            场
          </span>
          <span>
            <b className="font-display text-bf6-fg mr-0.5 text-base font-medium tabular-nums">
              {fmtInt(mode.kills)}
            </b>
            击杀
          </span>
          <span>
            <b className="font-display text-bf6-fg mr-0.5 text-base font-medium tabular-nums">
              {fmtHours(mode.time_seconds)}
            </b>
            小时
          </span>
        </div>
      </div>
      <Ring ratio={mode.win_rate} />
    </Panel>
  );
}

export function ModesTab({ stats }: { stats: Bf6PlayerStats }) {
  const byId = new Map(stats.modes.map((m) => [m.id, m]));
  const used = new Set<string>();
  const groups: { key: string; zh: string; en: string; items: Bf6ModeStats[] }[] = MODE_GROUPS.map(
    (g) => {
      const items = g.ids.flatMap((id) => byId.get(id) ?? []);
      items.forEach((m) => used.add(m.id));
      return { key: g.key, zh: g.zh, en: g.en, items };
    },
  );
  groups.push({
    key: "other",
    zh: "活动与其他",
    en: "Events & More",
    items: stats.modes.filter((m) => !used.has(m.id)),
  });

  const shown = groups.filter((g) => g.items.length > 0);
  if (shown.length === 0) return <Empty text="还没有模式记录" />;
  return (
    <div className="grid gap-7">
      {shown.map((g) => (
        <div key={g.key}>
          <div className="mb-3 flex items-baseline gap-2.5">
            <b className="text-bf6-fg text-[15px] tracking-[0.06em]">{g.zh}</b>
            <span className="font-display text-bf6-mute text-[11px] tracking-[0.3em] uppercase">
              {g.en}
            </span>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {[...g.items]
              .sort((a, b) => (b.time_seconds ?? 0) - (a.time_seconds ?? 0))
              .map((m) => (
                <ModeRow key={m.id} mode={m} />
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return (
    <div className="border-bf6-line-strong text-bf6-mute border border-dashed px-4 py-10 text-center text-sm">
      {text}
    </div>
  );
}
