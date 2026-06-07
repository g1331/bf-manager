import { redirect } from "next/navigation";

/**
 * 进入某个游戏时直接落到该游戏的「概况」页。
 *
 * 新的左侧 rail + 顶部 tab 两级导航已取代旧的「战绩查询 / 服务器列表」双卡中转页，
 * 因此这里不再渲染中转内容，而是重定向到概况。目前仅 BF1 启用（其余游戏在
 * [game]/layout 中已 notFound），其概况即 /stats。
 */
export default function GameEntryPage() {
  redirect("/stats");
}
