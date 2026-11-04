import { redirect } from "next/navigation";

/** BF6 目前只有战绩查询，进入游戏直接落到这一页 */
export default function Bf6EntryPage() {
  redirect("/bf6/players");
}
