/**
 * 作战档案首屏：主玩兵种的官方立绘铺在右侧，左侧是名字、K/D 和六项核心数据。
 */
import type { Bf6PlayerStats } from "@/lib/api/bf6";
import { kitInfo, modeInfo } from "@/lib/bf6/catalog";
import { fmtFixed, fmtHours, fmtInt, fmtPct } from "@/lib/bf6/format";
import { platformLabel } from "@/lib/bf6/player-link";
import { MaskIcon } from "./primitives";

export function Bf6Hero({
  name,
  avatarUrl,
  platform,
  stats,
}: {
  name: string;
  avatarUrl: string | null;
  platform: string | null;
  stats: Bf6PlayerStats;
}) {
  const c = stats.career;
  const kit = c.best_class ? kitInfo(c.best_class) : null;
  const topMode = stats.modes[0] ? modeInfo(stats.modes[0].id) : null;
  const platformName = platformLabel(platform);
  const xp = c.xp == null ? "—" : c.xp >= 1e6 ? `${(c.xp / 1e6).toFixed(2)}M` : fmtInt(c.xp);

  const cells = [
    { label: "KPM", value: fmtFixed(c.kpm), note: "每分钟真人击杀" },
    { label: "SPM", value: c.spm == null ? "—" : Math.round(c.spm).toString(), note: "每分钟得分" },
    {
      label: "胜率",
      value: fmtPct(c.win_rate),
      note: `${fmtInt(c.wins)} 胜 ${fmtInt(c.losses)} 负`,
    },
    { label: "场次", value: fmtInt(c.matches), note: "全部模式" },
    { label: "战斗时长", value: fmtHours(c.time_seconds), note: "小时" },
    { label: "经验", value: xp, note: "XP 总计" },
  ];

  return (
    <section className="border-bf6-line relative overflow-hidden border-b">
      {kit?.wide ? (
        <div
          className="absolute inset-0 [mask-image:linear-gradient(#000_40%,transparent_85%)] bg-cover [background-position:60%_20%] opacity-55 lg:left-[30%] lg:[mask-image:linear-gradient(90deg,transparent_0%,#000_38%),linear-gradient(#000_70%,transparent)] lg:[mask-composite:intersect] lg:opacity-90"
          style={{ backgroundImage: `url(${kit.wide})` }}
        />
      ) : null}
      <div className="absolute inset-0 bg-[linear-gradient(0deg,var(--color-bf6-bg)_8%,rgba(10,11,12,0.55)_55%,rgba(10,11,12,0.35)_100%)] lg:bg-[linear-gradient(90deg,var(--color-bf6-bg)_0%,rgba(10,11,12,0.92)_34%,rgba(10,11,12,0.25)_62%,rgba(10,11,12,0.1)_100%),linear-gradient(0deg,var(--color-bf6-bg)_0%,transparent_35%)]" />
      {kit ? (
        <div
          aria-hidden
          className="font-display pointer-events-none absolute -top-7 -right-1.5 hidden text-[220px] leading-none font-bold tracking-[-0.02em] text-transparent uppercase select-none [-webkit-text-stroke:1px_rgba(255,255,255,0.09)] xl:block"
        >
          {kit.en}
        </div>
      ) : null}

      <div className="relative px-1 pt-6 pb-6 sm:pt-10 sm:pb-9">
        <div className="text-bf6 flex items-center gap-3.5 font-mono text-[11px] tracking-[0.22em] uppercase">
          <span className="tracking-[-2px]">▶▶▶▶</span>作战档案 // Service Record
        </div>

        <div className="mt-4 flex items-center gap-4 sm:gap-5">
          <div className="relative size-16 shrink-0 sm:size-[92px]">
            {avatarUrl ? (
              <img
                src={avatarUrl}
                alt=""
                className="size-full object-cover [clip-path:polygon(0_0,calc(100%-16px)_0,100%_16px,100%_100%,0_100%)]"
              />
            ) : (
              <div className="font-display bg-bf6-panel text-bf6-fg2 grid size-full place-items-center text-3xl font-bold [clip-path:polygon(0_0,calc(100%-16px)_0,100%_16px,100%_100%,0_100%)]">
                {name.slice(0, 1).toUpperCase()}
              </div>
            )}
            <span className="border-bf6 absolute -bottom-1.5 -left-1.5 size-[22px] border-b-2 border-l-2" />
          </div>
          <div className="min-w-0">
            <h1 className="font-display text-bf6-fg truncate text-[34px] leading-none font-semibold tracking-[0.01em] sm:text-[58px]">
              {name}
            </h1>
            <div className="mt-3 flex flex-wrap gap-2">
              {platformName ? <Chip>{platformName}</Chip> : null}
              {kit ? (
                <Chip>
                  主玩 <b className="text-bf6-fg font-semibold">{kit.zh}</b>
                </Chip>
              ) : null}
              {topMode ? (
                <Chip>
                  最常玩 <b className="text-bf6-fg font-semibold">{topMode.name}</b>
                </Chip>
              ) : null}
              <Chip accent>生涯数据 · {fmtHours(c.time_seconds)} 小时</Chip>
            </div>
          </div>
        </div>

        <div className="mt-6 grid gap-5 sm:mt-9 lg:grid-cols-[auto_1fr] lg:items-end lg:gap-12">
          <div>
            <div className="text-bf6-mute font-mono text-[11px] tracking-[0.25em]">K / D</div>
            <div className="font-display text-bf6 mt-1.5 text-[92px] leading-[0.86] font-bold tabular-nums [text-shadow:0_0_40px_rgba(255,90,31,0.28)] sm:text-[128px]">
              {fmtFixed(c.kd)}
            </div>
            <div className="text-bf6-mute mt-2.5 text-xs">
              真人击杀 <b className="text-bf6-fg2 font-medium">{fmtInt(c.human_kills)}</b> / 死亡{" "}
              <b className="text-bf6-fg2 font-medium">{fmtInt(c.deaths)}</b>
            </div>
          </div>
          <div className="border-bf6-line-strong grid max-w-[760px] grid-cols-3 border-t sm:grid-cols-6">
            {cells.map((cell) => (
              <div key={cell.label} className="pt-3 pr-2.5 sm:pt-3.5 sm:pr-4">
                <span className="text-bf6-mute block text-xs">{cell.label}</span>
                <b className="font-display text-bf6-fg mt-1 block text-[26px] leading-tight font-medium tabular-nums sm:text-[32px]">
                  {cell.value}
                </b>
                <em className="text-bf6-mute mt-0.5 block truncate text-[11px] not-italic">
                  {cell.note}
                </em>
              </div>
            ))}
          </div>
        </div>
      </div>

      {kit?.icon ? (
        <div className="absolute top-9 right-6 hidden text-right xl:block">
          <small className="text-bf6-fg2 font-mono text-[10px] tracking-[0.3em]">主玩兵种</small>
          <div className="font-display text-bf6-fg flex items-center justify-end gap-2.5 text-3xl font-semibold">
            <MaskIcon src={kit.icon} className="size-[26px]" />
            {kit.zh}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function Chip({ children, accent }: { children: React.ReactNode; accent?: boolean }) {
  return (
    <span
      className={
        accent
          ? "border-bf6/50 bg-bf6-panel/70 text-bf6-soft inline-flex items-center gap-1.5 border px-2.5 py-1 text-xs"
          : "border-bf6-line-strong bg-bf6-panel/70 text-bf6-fg2 inline-flex items-center gap-1.5 border px-2.5 py-1 text-xs"
      }
    >
      {children}
    </span>
  );
}
