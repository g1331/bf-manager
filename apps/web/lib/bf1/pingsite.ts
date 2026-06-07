/**
 * EA ping 节点（pingSiteAlias）代号 → 数据中心城市标签。
 *
 * BF1 服务器浏览器里显示的 ping 是「客户端到该 ping 节点数据中心」的实测往返延迟，
 * 同一节点的所有服务器显示同一个值；EA 的服务器接口只返回节点代号、不返回延迟数值，
 * 真实服务器 IP 也不经接口暴露，因此服务端拿不到 ping 数值，只能展示节点所在城市。
 * 代号沿用类 IATA 机场码（nrt=东京、fra=法兰克福……）。未收录的代号回退为大写代号本身。
 */
const PING_SITE_LABELS: Record<string, string> = {
  // 亚太
  nrt: "东京",
  kix: "大阪",
  hkg: "香港",
  sin: "新加坡",
  bom: "孟买",
  syd: "悉尼",
  // 欧洲
  fra: "法兰克福",
  ams: "阿姆斯特丹",
  lhr: "伦敦",
  par: "巴黎",
  waw: "华沙",
  mad: "马德里",
  // 北美
  iad: "华盛顿",
  sjc: "圣何塞",
  lax: "洛杉矶",
  dfw: "达拉斯",
  ord: "芝加哥",
  mia: "迈阿密",
  sea: "西雅图",
  // 南美
  brz: "圣保罗",
  gru: "圣保罗",
  scl: "圣地亚哥",
  gig: "里约",
  // 中东 / 非洲
  dxb: "迪拜",
  cpt: "开普敦",
  jnb: "约翰内斯堡",
};

/** ping 节点代号 → 数据中心城市标签；空值返回 null，未收录代号回退为大写代号 */
export function pingSiteLabel(code: string | null | undefined): string | null {
  if (!code) return null;
  return PING_SITE_LABELS[code.toLowerCase()] ?? code.toUpperCase();
}
