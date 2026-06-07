/**
 * 应用内两级导航的数据模型与匹配逻辑。
 *
 * 复刻经典战地（BF1/3/4）游戏大厅的导航结构：
 *   一级 = 左侧窄图标条（rail），负责「游戏 / 玩家信息 / 管理」模块切换；
 *   二级 = 顶部横向 tab，展示当前模块下的子页面。
 *
 * 与真实大厅一致：rail 顶部不是某个独立的「总览」入口，而是游戏列表本身——
 *   点击 BF1 进入的就是它的「概况」页（即原来的全服统计），同模块还包含
 *   服务器与战绩查询等子页。游戏组在 rail 中垂直居中。
 *
 * 本文件只承载纯数据与纯函数，便于服务端与客户端组件共用，UI 细节留给组件。
 */

import { CircleUser, Gauge, type LucideIcon } from "lucide-react";
import { GAMES, type GameMeta } from "./game-registry";

/** 顶部二级 tab。 */
export interface TopTab {
  label: string;
  /** 英文大写代号，呼应战地 UI 的大写标签语汇，作 tab 副标。 */
  code?: string;
  href: string;
  /** 精确匹配（用于本身是其它子路由前缀的入口，如运维概览 /admin）。 */
  exact?: boolean;
  /** 额外参与高亮的路由前缀（列表入口覆盖其单数详情页，如 /bf1/player）。 */
  match?: string[];
}

/** 一级模块在 rail 中的呈现形态：游戏用封面缩略图，其余用线性图标。 */
export type RailKind = "game" | "user" | "admin";

/** rail 三个分组：游戏组居中，玩家组紧随其后，系统组始终钉在底部。 */
export type RailSection = "games" | "player" | "system";

/** 一级模块（左侧 rail 的一项）。 */
export interface RailModule {
  key: string;
  /** rail 悬停提示与移动端列表用的完整名称。 */
  label: string;
  /** 点击落点（模块默认页）。禁用模块为 "#"。 */
  href: string;
  kind: RailKind;
  /** rail 视觉分组，决定竖向位置（居中 / 紧随 / 底部）。 */
  section: RailSection;
  /** 归属本模块的全部路由前缀（含 href 自身），用于判定 rail 激活与 tab 归属。 */
  match: string[];
  /** 仅登录用户可见。 */
  authOnly?: boolean;
  /** 仅平台管理员可见。 */
  adminOnly?: boolean;
  /** 线性图标（玩家信息 / 管理后台 模块用）。 */
  icon?: LucideIcon;
  /** 封面缩略图路径（game 模块用）。 */
  image?: string;
  /** 未启用的游戏：灰显且不可导航。 */
  disabled?: boolean;
  /** 本模块下的二级 tab。 */
  tabs: TopTab[];
}

function gameModule(g: GameMeta): RailModule {
  if (!g.enabled) {
    return {
      key: g.id,
      label: `${g.displayName}（即将到来）`,
      href: "#",
      kind: "game",
      section: "games",
      match: [],
      image: g.cardImage,
      disabled: true,
      tabs: [],
    };
  }
  // 已启用的游戏——目前仅 BF1。默认页 /stats 即该游戏的全服概况。
  if (g.id === "bf1") {
    return {
      key: g.id,
      label: g.displayName,
      href: "/stats",
      kind: "game",
      section: "games",
      // /stats 归属 BF1（其为 BF1 全服统计），同时覆盖所有 /bf1/* 子路由。
      match: ["/stats", "/bf1"],
      image: g.cardImage,
      tabs: [
        { label: "概况", code: "Overview", href: "/stats", exact: true },
        { label: "服务器", code: "Servers", href: "/bf1/servers", match: ["/bf1/server"] },
        { label: "战绩查询", code: "Career", href: "/bf1/players", match: ["/bf1/player"] },
      ],
    };
  }
  // 其它未来启用的游戏：先给空 tab 集，待对应模块上线时补齐。
  return {
    key: g.id,
    label: g.displayName,
    href: `/${g.id}`,
    kind: "game",
    section: "games",
    match: [`/${g.id}`],
    image: g.cardImage,
    tabs: [],
  };
}

/**
 * rail 模块声明顺序（按 section 渲染时再分组）：
 *   games  ：所有游戏（启用 + 灰显），在 rail 中垂直居中
 *   player ：玩家信息（我的主页），居中组紧随其后
 *   admin  ：管理后台（仅 admin），同上
 * 系统区入口（门户首页 / 登出等）由组件层直接处理，不进 MODULES。
 */
export const MODULES: RailModule[] = [
  ...Object.values(GAMES).map(gameModule),
  {
    key: "me",
    label: "我的主页",
    href: "/me",
    kind: "user",
    section: "player",
    match: ["/me"],
    authOnly: true,
    icon: CircleUser,
    tabs: [{ label: "我的主页", code: "Profile", href: "/me", exact: true }],
  },
  {
    key: "admin",
    label: "管理后台",
    href: "/admin",
    kind: "admin",
    section: "player",
    match: ["/admin"],
    adminOnly: true,
    icon: Gauge,
    tabs: [
      { label: "运维概览", code: "Ops", href: "/admin", exact: true },
      { label: "EA 账号池", code: "Accounts", href: "/admin/ea-accounts" },
      { label: "服管权限", code: "Roles", href: "/admin/memberships" },
      { label: "审计日志", code: "Audit", href: "/admin/audit" },
    ],
  },
];

/** 路由前缀匹配：精确相等或以「前缀 + /」开头。 */
function pathMatches(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/**
 * 由当前路径推断激活的一级模块及其二级 tab 集。
 * 各模块 match 前缀互不包含，按声明顺序首个命中即归属；未命中返回空上下文
 * （落地页 / 与未知路由不激活任何模块、不展示 tab）。
 */
export function getNavContext(pathname: string): { activeKey: string | null; tabs: TopTab[] } {
  for (const m of MODULES) {
    if (m.match.some((p) => pathMatches(pathname, p))) {
      return { activeKey: m.key, tabs: m.tabs };
    }
  }
  return { activeKey: null, tabs: [] };
}

/** 判定某一级模块在 rail 中是否处于激活态。 */
export function isModuleActive(pathname: string, module: RailModule): boolean {
  return module.match.some((p) => pathMatches(pathname, p));
}

/** 判定某二级 tab 是否处于激活态：exact 精确匹配，否则按 href 与 match 前缀匹配。 */
export function isTabActive(pathname: string, tab: TopTab): boolean {
  if (tab.exact) return pathname === tab.href;
  const prefixes = [tab.href, ...(tab.match ?? [])];
  return prefixes.some((p) => pathMatches(pathname, p));
}
