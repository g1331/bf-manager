import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getGame } from "@/lib/game-registry";

interface PageProps {
  params: Promise<{ game: string }>;
}

export default async function GameEntryPage({ params }: PageProps) {
  const { game } = await params;
  const meta = getGame(game)!;

  return (
    <main className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold sm:text-3xl">{meta.displayName}</h1>
        <p className="text-muted-foreground">{meta.tagline}</p>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>战绩查询</CardTitle>
            <CardDescription>按昵称或 persona ID 查询玩家生涯数据</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild className="w-full">
              <Link href={`/${game}/players`}>开始查询</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>服务器列表</CardTitle>
            <CardDescription>浏览所有 {meta.shortName} 服务器</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="outline" className="w-full">
              <Link href={`/${game}/servers`}>查看服务器</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
