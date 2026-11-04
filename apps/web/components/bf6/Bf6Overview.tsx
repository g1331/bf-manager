/**
 * 概览分区：生涯之最 → 战斗表现 / 团队贡献 → 王牌装备 → 兵种 → 武器偏好 → 常玩地图 → 禁区冲突。
 */
import type { Bf6PlayerStats } from "@/lib/api/bf6";
import {
  WEAPON_CATEGORIES,
  kitInfo,
  statIcon,
  vehicleInfo,
  weaponInfo,
  type WeaponCategory,
} from "@/lib/bf6/catalog";
import {
  fmtCompact,
  fmtFixed,
  fmtHours,
  fmtInt,
  fmtKm,
  fmtPct,
  perHour,
  share,
} from "@/lib/bf6/format";
import { cn } from "@/lib/utils";
import { MapCard, RedsecPanel, nonRedsecMaps } from "./Bf6Maps";
import { MaskIcon, Panel, PanelTitle, SectionTitle, Stat } from "./primitives";

export type Bf6Tab = "overview" | "weapons" | "vehicles" | "gadgets" | "maps" | "modes";

export function Bf6Overview({
  stats,
  onShowTab,
}: {
  stats: Bf6PlayerStats;
  onShowTab: (tab: Bf6Tab) => void;
}) {
  const maps = nonRedsecMaps(stats.maps);
  let index = 0;
  const next = () => String(++index).padStart(2, "0");

  return (
    <div>
      <SectionTitle index={next()} title="生涯之最" en="Career Bests" />
      <CareerBests stats={stats} />

      <SectionTitle index={next()} title="战斗表现" en="Combat" />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
        <CombatPanel stats={stats} />
        <TeamPanel stats={stats} />
      </div>

      {stats.weapons[0] || stats.vehicles[0] ? (
        <>
          <SectionTitle index={next()} title="王牌装备" en="Signature" />
          <AceLoadout stats={stats} />
        </>
      ) : null}

      {stats.kits.length > 0 ? (
        <>
          <SectionTitle index={next()} title="兵种" en="Classes" aside="按战斗时长排序" />
          <ClassCards stats={stats} />
        </>
      ) : null}

      {stats.weapon_categories.length > 0 ? (
        <>
          <SectionTitle index={next()} title="武器偏好" en="Weapon Mix" aside="按大类击杀" />
          <WeaponMix stats={stats} />
        </>
      ) : null}

      {maps.length > 0 ? (
        <>
          <SectionTitle
            index={next()}
            title="常玩地图"
            en="Maps"
            aside={
              <button
                type="button"
                onClick={() => onShowTab("maps")}
                className="text-bf6-fg2 hover:text-bf6-soft text-[13px] transition-colors"
              >
                全部 {stats.maps.length} 张 →
              </button>
            }
          />
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr_1fr]">
            {maps.slice(0, 5).map((m, i) => (
              <MapCard key={m.id} map={m} rank={i + 1} featured={i === 0} />
            ))}
          </div>
        </>
      ) : null}

      {stats.redsec ? (
        <>
          <SectionTitle index={next()} title="禁区冲突" en="REDSEC" />
          <RedsecPanel redsec={stats.redsec} />
        </>
      ) : null}
    </div>
  );
}

/* ------------------------------ 生涯之最 ------------------------------ */

function CareerBests({ stats }: { stats: Bf6PlayerStats }) {
  const b = stats.bests;
  const records = [
    { icon: "Kills", label: "单局最多击杀", value: b.round_kills },
    { icon: "Score", label: "单局最高得分", value: b.round_score },
    { icon: "KD", label: "一条命最多击杀", value: b.life_kills },
    { icon: "Recon-Sniper", label: "最远击杀", value: b.longest_kill_m, unit: "m" },
    { icon: "Headshots", label: "单局最多爆头", value: b.round_headshots },
    { icon: "Assault-Objective", label: "单局最多守点", value: b.round_defends },
  ];
  return (
    <div className="bf6-cut relative overflow-hidden bg-[repeating-linear-gradient(0deg,rgba(0,0,0,0.025)_0_2px,transparent_2px_5px),linear-gradient(100deg,#e4e5e6_0%,#cfd2d4_100%)] text-[#111214]">
      {/* 每格画左、上分隔线，整体左移上移 1px，最外圈的线被裁掉 */}
      <div className="-mt-px -ml-px grid w-[calc(100%+1px)] grid-cols-2 sm:grid-cols-3 xl:grid-cols-6">
        {records.map((r) => (
          <div
            key={r.label}
            className="border-t border-l border-black/12 px-3.5 pt-4 pb-5 sm:px-5 sm:pt-5.5 sm:pb-6.5"
          >
            <MaskIcon src={statIcon(r.icon)} className="text-bf6 size-[30px]" />
            <span className="mt-2.5 block text-xs font-semibold tracking-[0.06em] text-[#3d4144]">
              {r.label}
            </span>
            <b className="font-display mt-0.5 block text-[32px] leading-[1.05] font-bold tabular-nums sm:text-[40px]">
              {fmtInt(r.value)}
              {r.unit && r.value != null ? (
                <small className="ml-0.5 text-lg font-medium">{r.unit}</small>
              ) : null}
            </b>
          </div>
        ))}
      </div>
      <span className="absolute right-3.5 bottom-2 hidden font-mono text-[9px] tracking-[0.2em] text-black/35 sm:block">
        + BEST // _CAREER
      </span>
    </div>
  );
}

/* ------------------------------ 战斗 / 团队 ------------------------------ */

function Split({
  left,
  right,
  winLoss,
}: {
  left: [string, number | null];
  right: [string, number | null];
  winLoss?: boolean;
}) {
  const l = left[1] ?? 0;
  const r = right[1] ?? 0;
  const total = l + r;
  if (!total) return null;
  return (
    <div className="mt-4.5">
      <div className="text-bf6-mute flex justify-between text-xs">
        <span>
          {left[0]}
          <b className="font-display text-bf6-fg mx-1 text-[15px] font-medium tabular-nums">
            {fmtInt(l)}
          </b>
          {fmtPct(l / total, 0)}
        </span>
        <span>
          {fmtPct(r / total, 0)}
          <b className="font-display text-bf6-fg mx-1 text-[15px] font-medium tabular-nums">
            {fmtInt(r)}
          </b>
          {right[0]}
        </span>
      </div>
      <div className="mt-1.5 flex h-1.5 gap-0.5">
        <i
          className={cn("block", winLoss ? "bg-bf6-win" : "bg-bf6")}
          style={{ width: `${(l / total) * 100}%` }}
        />
        <i
          className={cn("block", winLoss ? "bg-bf6-loss" : "bg-[#4a5157]")}
          style={{ width: `${(r / total) * 100}%` }}
        />
      </div>
    </div>
  );
}

function CombatPanel({ stats }: { stats: Bf6PlayerStats }) {
  const c = stats.career;
  const ai = c.kills != null && c.human_kills != null ? c.kills - c.human_kills : null;
  const damage = fmtCompact(c.damage);
  const cells = [
    { label: "击杀", value: fmtInt(c.kills), note: "含 AI" },
    { label: "死亡", value: fmtInt(c.deaths) },
    { label: "助攻", value: fmtInt(c.assists) },
    { label: "伤害", value: damage.value, unit: damage.unit },
    { label: "爆头击杀", value: fmtInt(c.headshots), note: fmtPct(c.headshot_rate) },
    { label: "命中率", value: fmtPct(c.accuracy) },
    { label: "多杀", value: fmtInt(c.multi_kills) },
    { label: "远距离击杀", value: fmtInt(c.long_distance_kills) },
    { label: "载具击杀", value: fmtInt(c.vehicle_kills) },
    { label: "摧毁载具", value: fmtInt(c.vehicles_destroyed) },
    { label: "处决", value: fmtInt(c.takedowns) },
    {
      label: "移动距离",
      value: fmtKm(c.distance_m),
      unit: c.distance_m != null ? "km" : undefined,
    },
  ];
  return (
    <Panel className="px-4 py-5 sm:px-6 sm:py-5.5">
      <PanelTitle note="击杀含 AI，K/D 与 KPM 只算真人">战斗</PanelTitle>
      <Split left={["真人", c.human_kills]} right={["AI", ai]} />
      <Split left={["开镜", c.ads_kills]} right={["腰射", c.hipfire_kills]} />
      <Split left={["胜", c.wins]} right={["负", c.losses]} winLoss />
      <div className="border-bf6-line mt-5.5 grid grid-cols-2 gap-x-4 gap-y-4.5 border-t pt-5 sm:grid-cols-4">
        {cells.map((cell) => (
          <Stat key={cell.label} {...cell} />
        ))}
      </div>
    </Panel>
  );
}

function TeamPanel({ stats }: { stats: Bf6PlayerStats }) {
  const c = stats.career;
  const rows = [
    { icon: "Revives", label: "急救", value: c.revives },
    { icon: "Eng-Repair", label: "修理", value: c.repairs },
    { icon: "Damage", label: "治疗量", value: c.healing },
    { icon: "Support-EnemiesSuppressed", label: "补给队友", value: c.resupplies },
    { icon: "Assists", label: "索敌助攻", value: c.spot_assists },
    { icon: "Assault-Objective", label: "占领据点", value: c.captures },
  ];
  return (
    <Panel className="px-4 py-5 sm:px-6 sm:py-5.5">
      <PanelTitle>团队贡献</PanelTitle>
      <div className="mt-2">
        {rows.map((r) => (
          <div
            key={r.label}
            className="border-bf6-line grid grid-cols-[34px_1fr_auto] items-center gap-3 border-b py-3 last:border-b-0"
          >
            <div className="border-bf6-line-strong text-bf6-soft grid size-[34px] place-items-center border">
              <MaskIcon src={statIcon(r.icon)} className="size-[18px]" />
            </div>
            <div>
              <span className="text-bf6-mute block text-xs">{r.label}</span>
              <b className="font-display text-bf6-fg text-[22px] font-medium tabular-nums">
                {fmtInt(r.value)}
              </b>
            </div>
            <div className="text-bf6-mute text-right text-xs">
              <b className="font-display text-bf6-fg2 block text-[17px] font-medium tabular-nums">
                {perHour(r.value, c.time_seconds)}
              </b>
              每小时
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

/* ------------------------------ 王牌装备 ------------------------------ */

function AceCard({
  label,
  name,
  sub,
  img,
  cells,
}: {
  label: string;
  name: string;
  sub: string;
  img: string | null;
  cells: { label: string; value: string; unit?: string; accent?: boolean }[];
}) {
  return (
    <div className="bf6-cut border-bf6-line relative flex min-h-[284px] flex-col overflow-hidden border bg-[radial-gradient(420px_220px_at_72%_46%,rgba(255,90,31,0.22),transparent_70%),linear-gradient(135deg,#16191b_0%,#0f1112_100%)]">
      <div className="pointer-events-none absolute -top-5 -right-10 -bottom-5 w-[300px] bg-[linear-gradient(115deg,transparent_0_30%,var(--color-bf6)_30%_52%,transparent_52%_62%,var(--color-bf6)_62%_84%,transparent_84%)] opacity-[0.14]" />
      <div className="relative px-6 pt-5.5">
        <div className="text-bf6 font-mono text-[11px] tracking-[0.25em]">{label}</div>
        <h3 className="font-display text-bf6-fg mt-1.5 mb-0.5 text-[32px] leading-none font-semibold sm:text-[40px]">
          {name}
        </h3>
        <div className="text-bf6-fg2 text-[13px]">{sub}</div>
      </div>
      {img ? (
        <div className="relative mx-6 my-3 h-[120px] sm:absolute sm:top-5.5 sm:right-6 sm:m-0 sm:h-[156px] sm:w-[54%]">
          <img
            src={img}
            alt=""
            className="size-full object-contain drop-shadow-[0_18px_24px_rgba(0,0,0,0.6)] sm:object-right"
          />
        </div>
      ) : null}
      <div className="border-bf6-line-strong relative mx-6 mt-auto mb-5.5 grid grid-cols-4 gap-3 border-t pt-3.5">
        {cells.map((cell) => (
          <div key={cell.label} className="min-w-0">
            <span className="text-bf6-mute block text-[11px]">{cell.label}</span>
            <b
              className={cn(
                "font-display block truncate text-xl font-medium tabular-nums sm:text-2xl",
                cell.accent ? "text-bf6" : "text-bf6-fg",
              )}
            >
              {cell.value}
              {cell.unit ? <small className="ml-0.5 text-[13px]">{cell.unit}</small> : null}
            </b>
          </div>
        ))}
      </div>
    </div>
  );
}

function AceLoadout({ stats }: { stats: Bf6PlayerStats }) {
  const w = stats.weapons[0];
  const v = stats.vehicles[0];
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {w
        ? (() => {
            const info = weaponInfo(w.id);
            return (
              <AceCard
                label="// 王牌武器 · ACE WEAPON"
                name={info.name}
                sub={`${info.categoryZh} · 使用 ${fmtHours(w.time_seconds)} 小时`}
                img={info.img}
                cells={[
                  { label: "击杀", value: fmtInt(w.kills), accent: true },
                  { label: "KPM", value: fmtFixed(w.kpm) },
                  { label: "命中率", value: fmtPct(w.accuracy) },
                  { label: "爆头率", value: fmtPct(w.headshot_rate) },
                ]}
              />
            );
          })()
        : null}
      {v
        ? (() => {
            const info = vehicleInfo(v.id);
            const dmg = fmtCompact(v.damage);
            return (
              <AceCard
                label="// 王牌载具 · ACE VEHICLE"
                name={info.name}
                sub={`${info.typeZh ?? "载具"} · 驾驶 ${fmtHours(v.time_seconds)} 小时`}
                img={info.img}
                cells={[
                  { label: "击杀", value: fmtInt(v.kills), accent: true },
                  { label: "KPM", value: fmtFixed(v.kpm) },
                  { label: "伤害", value: dmg.value, unit: dmg.unit },
                  { label: "里程", value: fmtKm(v.distance_m), unit: "km" },
                ]}
              />
            );
          })()
        : null}
    </div>
  );
}

/* ------------------------------ 兵种 ------------------------------ */

function ClassCards({ stats }: { stats: Bf6PlayerStats }) {
  const total = stats.kits.reduce((sum, k) => sum + (k.time_seconds ?? 0), 0);
  const best = stats.career.best_class;
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:gap-4 lg:grid-cols-4">
      {stats.kits.map((k) => {
        const info = kitInfo(k.id);
        const part = share(k.time_seconds, total);
        const spm = k.score != null && k.time_seconds ? k.score / (k.time_seconds / 60) : null;
        const isBest = k.id === best;
        return (
          <div
            key={k.id}
            className={cn(
              "group bg-bf6-panel overflow-hidden border",
              isBest ? "border-bf6/60 shadow-[0_0_0_1px_rgba(255,90,31,0.25)]" : "border-bf6-line",
            )}
          >
            <div
              className="relative aspect-[3/3.4] bg-cover [background-position:center_18%] saturate-[0.92] transition-[filter] duration-300 group-hover:saturate-[1.08]"
              style={info.tall ? { backgroundImage: `url(${info.tall})` } : undefined}
            >
              <div className="absolute inset-0 bg-[linear-gradient(180deg,transparent_45%,rgba(15,17,18,0.96)_100%)]" />
              <div className="absolute inset-x-2.5 bottom-3.5 sm:inset-x-4">
                <div className="text-bf6-fg flex items-center gap-2 text-[17px] font-extrabold tracking-[0.06em] sm:text-[22px]">
                  {info.icon ? (
                    <MaskIcon src={info.icon} className="size-5 sm:size-[22px]" />
                  ) : null}
                  {info.zh}
                  {isBest ? (
                    <span className="bg-bf6 ml-auto hidden px-1.5 py-0.5 text-[11px] font-semibold tracking-[0.08em] text-black sm:inline">
                      主玩
                    </span>
                  ) : null}
                </div>
                <div className="text-bf6-fg2 mt-1.5 flex items-baseline gap-2 text-xs whitespace-nowrap">
                  <b className="font-display text-bf6-fg text-xl font-semibold tabular-nums sm:text-[26px]">
                    {Math.round(part * 100)}%
                  </b>
                  {fmtHours(k.time_seconds)} 小时
                </div>
                <div className="mt-2 h-[3px] bg-white/10">
                  <i className="bg-bf6 block h-full" style={{ width: `${part * 100}%` }} />
                </div>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 px-3 pt-2.5 pb-3 sm:px-4 sm:pt-3.5 sm:pb-4">
              <Stat label="击杀" value={fmtInt(k.kills)} size="sm" />
              <Stat label="K/D" value={fmtFixed(k.kd)} size="sm" />
              <Stat label="SPM" value={spm == null ? "—" : Math.round(spm).toString()} size="sm" />
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------ 武器偏好 ------------------------------ */

const MIX_COLORS = [
  "#ff5a1f",
  "#ff8a4c",
  "#f2b33d",
  "#d9dbdc",
  "#9aa3aa",
  "#6b7680",
  "#4a545c",
  "#353c42",
];

function WeaponMix({ stats }: { stats: Bf6PlayerStats }) {
  const cats = stats.weapon_categories.filter((w) => w.kills);
  const total = cats.reduce((sum, w) => sum + (w.kills ?? 0), 0);
  const label = (id: string) => WEAPON_CATEGORIES[id as WeaponCategory]?.zh ?? id;
  return (
    <Panel className="px-4 py-5 sm:px-6 sm:py-5.5">
      <div className="flex h-[34px] gap-0.5">
        {cats.map((w, i) => (
          <i
            key={w.id}
            title={label(w.id)}
            className="block h-full"
            style={{
              width: `${share(w.kills, total) * 100}%`,
              background: MIX_COLORS[i % MIX_COLORS.length],
            }}
          />
        ))}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-x-5 gap-y-3 lg:grid-cols-4">
        {cats.map((w, i) => (
          <div
            key={w.id}
            className="grid grid-cols-[10px_1fr_auto] items-center gap-x-2 text-[13px]"
          >
            <i className="size-2.5" style={{ background: MIX_COLORS[i % MIX_COLORS.length] }} />
            <span className="text-bf6-fg truncate">{label(w.id)}</span>
            <b className="font-display text-bf6-fg font-medium tabular-nums">{fmtInt(w.kills)}</b>
            <em className="text-bf6-mute col-start-2 col-end-4 text-[11px] not-italic">
              {fmtPct(share(w.kills, total), 0)}
              {w.accuracy != null ? ` · 命中 ${fmtPct(w.accuracy)}` : ""} ·{" "}
              {fmtHours(w.time_seconds)} h
            </em>
          </div>
        ))}
      </div>
    </Panel>
  );
}
