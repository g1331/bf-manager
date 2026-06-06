"use client";

import { useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/layout/PageHeader";
import { toast } from "sonner";
import { bf1Api, type PersonaBrief } from "@/lib/api/bf1";
import { ApiException } from "@/lib/api-client";

export default function PlayerSearchPage() {
  const params = useParams<{ game: string }>();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PersonaBrief[]>([]);

  const search = useMutation({
    mutationFn: (name: string) => bf1Api.searchPlayers(name),
    onSuccess: (res) => {
      setResults(res.personas);
      if (res.personas.length === 0) {
        toast.info("未找到匹配的玩家");
      }
    },
    onError: (err) => {
      const msg = err instanceof ApiException ? err.message : "查询失败";
      toast.error(msg);
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      toast.warning("昵称至少 2 个字符");
      return;
    }
    search.mutate(trimmed);
  };

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-6 sm:px-6">
      <PageHeader
        kicker="Stats"
        title="玩家战绩查询"
        description="按 EA 昵称查询 Battlefield 1 玩家战绩"
      />

      <form onSubmit={submit} className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="输入 EA 昵称（不区分大小写）"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          className="flex-1"
        />
        <Button type="submit" disabled={search.isPending} size="lg" className="px-6">
          <Search className="size-4" />
          {search.isPending ? "查询中…" : "查询"}
        </Button>
      </form>

      {results.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-muted-foreground text-sm font-medium">
            找到 {results.length} 个匹配
          </h2>
          <ul className="space-y-2">
            {results.map((p) => (
              <li key={p.persona_id}>
                <Card
                  className="hover:border-primary cursor-pointer transition"
                  onClick={() => router.push(`/${params.game}/player/${p.persona_id}`)}
                >
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between text-base">
                      <span>{p.display_name}</span>
                      <span className="text-muted-foreground text-xs font-normal">
                        ID {p.persona_id}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-muted-foreground text-sm">
                    点击查看战绩详情
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}
