"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, Copy, KeyRound, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageHeaderSkeleton, RowsSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import { useSession } from "@/hooks/useSession";
import { apiKeysApi, type ApiKeyItem, type ApiKeyQuota } from "@/lib/api/api-keys";
import { ApiException } from "@/lib/api-client";

type Bucket = "lookup" | "read" | "avatar";

const BUCKET_LABEL: Record<Bucket, string> = {
  lookup: "查询",
  read: "只读",
  avatar: "头像",
};

const ENDPOINTS: { group: string; items: [path: string, desc: string, bucket: Bucket][] }[] = [
  {
    group: "玩家",
    items: [
      ["/bf1/players/search?name={昵称}", "按 EA 昵称搜玩家，区分大小写", "lookup"],
      ["/bf1/players/{persona_id}", "玩家昵称、头像、平台", "lookup"],
      ["/bf1/players/avatars?ids=1&ids=2", "批量取头像", "avatar"],
    ],
  },
  {
    group: "战绩",
    items: [
      ["/bf1/stats/{persona_id}", "生涯综合战绩", "lookup"],
      ["/bf1/stats/{persona_id}/weapons", "武器", "lookup"],
      ["/bf1/stats/{persona_id}/vehicles", "载具", "lookup"],
      ["/bf1/stats/{persona_id}/recent-servers", "最近游玩的服务器", "lookup"],
      ["/bf1/stats/{persona_id}/online", "是否在线、在哪个服", "lookup"],
      ["/bf1/stats/{persona_id}/platoon", "所属战队", "lookup"],
      ["/bf1/stats/{persona_id}/ban", "BFEAC / BFBAN 封禁状态", "lookup"],
      ["/bf1/stats/{persona_id}/rounds", "本站记录到的对局", "read"],
    ],
  },
  {
    group: "服务器",
    items: [
      ["/bf1/servers?name={关键字}", "服务器列表，可按地图、模式、地区筛选", "lookup"],
      ["/bf1/servers/{game_id}", "服务器详情、地图轮换", "lookup"],
      ["/bf1/servers/{game_id}/players", "实时玩家名单", "lookup"],
      ["/bf1/servers/{game_id}/player-counts", "近 7 天人数曲线", "read"],
      ["/bf1/servers/{game_id}/map-stats", "近 7 天各地图时长", "read"],
      ["/bf1/servers/{game_id}/leaderboard", "近 7 天在服时长排行", "read"],
      ["/bf1/servers/{game_id}/snapshots", "每分钟名单快照", "read"],
      ["/bf1/servers/{game_id}/rounds", "对局记录", "read"],
      ["/bf1/rounds/{round_id}", "单局详情与每人战绩", "read"],
    ],
  },
  {
    group: "其他",
    items: [
      ["/bf1/platoons?name={战队名}", "搜战队", "lookup"],
      ["/bf1/platoons/{guid}", "战队详情与成员", "lookup"],
      ["/bf1/overview", "全服在线统计", "read"],
      ["/bf1/exchange", "本期交换", "read"],
      ["/bf1/campaign", "当前行动", "read"],
    ],
  },
];

// 示例里的地址跟着当前站点走；服务端渲染时先用线上域名
const SITE_ORIGIN = "https://bfm.umrbotech.com";
const noopSubscribe = () => () => {};
const readOrigin = () => window.location.origin;

function formatTime(value: string | null): string {
  return value
    ? new Date(value).toLocaleString("zh-CN", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
}

function QuotaText({ quota, multiplier }: { quota: ApiKeyQuota; multiplier: number }) {
  return (
    <>
      <span className="whitespace-nowrap">查询 {quota.lookup_per_minute * multiplier}/分</span>
      {" · "}
      <span className="whitespace-nowrap">只读 {quota.read_per_minute * multiplier}/分</span>
    </>
  );
}

export default function MyApiKeysPage() {
  const router = useRouter();
  const session = useSession();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<{ name: string; key: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [pendingRevoke, setPendingRevoke] = useState<ApiKeyItem | null>(null);
  const origin = useSyncExternalStore(noopSubscribe, readOrigin, () => SITE_ORIGIN);

  useEffect(() => {
    if (!session.isLoading && !session.isError && !session.data) {
      router.replace("/login?next=/me/api");
    }
  }, [session.isLoading, session.isError, session.data, router]);

  const keys = useQuery({
    queryKey: ["my-api-keys"],
    queryFn: apiKeysApi.listMine,
    enabled: !!session.data,
  });

  const create = useMutation({
    mutationFn: (keyName: string) => apiKeysApi.create(keyName),
    onSuccess: (res) => {
      setCreated({ name: res.item.name, key: res.key });
      setCopied(false);
      setCreateOpen(false);
      setName("");
      qc.invalidateQueries({ queryKey: ["my-api-keys"] });
    },
    onError: (err) => toast.error(err instanceof ApiException ? err.message : "创建失败"),
  });

  const revoke = useMutation({
    mutationFn: (id: number) => apiKeysApi.revokeMine(id),
    onSuccess: () => {
      toast.success("已吊销，用这个 key 的请求会立即被拒绝");
      setPendingRevoke(null);
      qc.invalidateQueries({ queryKey: ["my-api-keys"] });
    },
    onError: (err) => toast.error(err instanceof ApiException ? err.message : "吊销失败"),
  });

  if (session.isLoading || !session.data) {
    return (
      <main className="mx-auto max-w-4xl space-y-6 px-4 py-4 sm:space-y-8 sm:px-6 sm:py-8">
        <PageHeaderSkeleton />
        <RowsSkeleton rows={5} />
      </main>
    );
  }

  const data = keys.data;
  const activeCount = data?.items.filter((k) => !k.revoked_at).length ?? 0;
  const atLimit = data ? activeCount >= data.max_keys : false;
  const sampleKey = created?.key ?? "bfm_你的key";

  const copyKey = () => {
    if (!created) return;
    void navigator.clipboard?.writeText(created.key).then(
      () => {
        setCopied(true);
        toast.success("已复制");
      },
      () => toast.error("复制失败，请手动选中复制"),
    );
  };

  const columns: Column<ApiKeyItem>[] = [
    {
      key: "name",
      header: "名称",
      cell: (k) => (
        <div>
          <div className="font-medium">{k.name}</div>
          <div className="text-muted-foreground font-mono text-xs">{k.prefix}…</div>
        </div>
      ),
      isCardTitle: true,
    },
    {
      key: "quota",
      header: "额度",
      cell: (k) =>
        data ? (
          <div className="text-sm">
            <span className="tabular-nums">×{k.rate_multiplier}</span>
            <div className="text-muted-foreground text-xs">
              <QuotaText quota={data.quota} multiplier={k.rate_multiplier} />
            </div>
          </div>
        ) : null,
    },
    {
      key: "usage",
      header: "今天 / 7 天",
      className: "whitespace-nowrap",
      cell: (k) => (
        <span className="tabular-nums">
          {k.used_today} / {k.used_7d}
        </span>
      ),
    },
    {
      key: "last_used",
      header: "最近使用",
      className: "whitespace-nowrap",
      cell: (k) => formatTime(k.last_used_at),
    },
    {
      key: "actions",
      header: "状态",
      className: "whitespace-nowrap",
      cell: (k) =>
        k.revoked_at ? (
          <span className="text-muted-foreground text-sm">已吊销</span>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="compact-action text-destructive h-auto p-0 hover:bg-transparent hover:underline"
            onClick={() => setPendingRevoke(k)}
          >
            吊销
          </Button>
        ),
    },
  ];

  return (
    <main className="mx-auto max-w-4xl space-y-6 px-4 py-4 sm:space-y-8 sm:px-6 sm:py-8">
      <PageHeader
        kicker="Open API"
        title="开放 API"
        description="给 QQ 机器人、工具站这类程序调用本站的公开查询。带上 API Key 后按 key 单独计额度，不和网页、不和同一出口 IP 的其他人共用。"
      />

      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <SectionHeading className="mb-0">我的 API Key</SectionHeading>
          <Button size="sm" disabled={atLimit} onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" />
            新建
          </Button>
        </div>

        {created ? (
          <div className="border-primary/40 bg-primary/5 mb-4 space-y-3 rounded-sm border p-4">
            <div className="flex items-center gap-2 font-medium">
              <KeyRound className="size-4" />「{created.name}」已创建
            </div>
            <p className="text-muted-foreground text-sm">
              完整 key
              只显示这一次，本站只保存它的指纹，离开页面后再也看不到。请现在复制保存好，丢了只能吊销重建。
            </p>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <code className="border-border bg-background min-w-0 flex-1 rounded-sm border px-3 py-2 font-mono text-sm break-all select-all">
                {created.key}
              </code>
              <Button variant="outline" onClick={copyKey} className="shrink-0">
                {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                {copied ? "已复制" : "复制"}
              </Button>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setCreated(null)}>
              我已保存，收起
            </Button>
          </div>
        ) : null}

        {keys.isLoading ? (
          <p className="text-muted-foreground text-sm">加载中…</p>
        ) : (
          <ResponsiveTable
            data={data?.items ?? []}
            columns={columns}
            rowKey={(k) => k.id}
            emptyState="还没有 API Key。网页正常查询不需要 key，写程序调用时再来申请。"
          />
        )}
        {data ? (
          <p className="text-muted-foreground mt-2 text-xs">
            每人最多 {data.max_keys} 个有效 key，当前 {activeCount}{" "}
            个。额度不够用可以联系管理员调高倍数。
          </p>
        ) : null}
      </section>

      <section className="space-y-3">
        <SectionHeading>怎么调用</SectionHeading>
        <p className="text-sm leading-relaxed">
          在请求头 <code className="font-mono">X-API-Key</code> 里带上 key，地址前缀是{" "}
          <code className="font-mono break-all">{origin}/api/v1</code>，返回 JSON。key
          只能放在你自己的服务端，别写进网页或发到群里；泄露了就到上面吊销。
        </p>
        <pre className="border-border bg-card overflow-x-auto rounded-sm border p-3 font-mono text-xs leading-relaxed sm:text-sm">
          {`curl -H "X-API-Key: ${sampleKey}" \\
  "${origin}/api/v1/bf1/players/search?name=SomePlayer"`}
        </pre>
        <p className="text-muted-foreground text-sm leading-relaxed">
          每个响应都带 <code className="font-mono">RateLimit-Remaining</code>（剩余次数）和{" "}
          <code className="font-mono">RateLimit-Reset</code>
          （几秒后重置），据此控制节奏。完整字段说明见{" "}
          <a
            href="/api/v1/openapi.public.json"
            target="_blank"
            rel="noreferrer"
            className="text-foreground inline-action underline underline-offset-2"
          >
            OpenAPI 文档
          </a>
          ，可以直接导入 Apifox、Postman，或用来生成类型。
        </p>
        <div className="border-border overflow-x-auto rounded-sm border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-left">
              <tr>
                <th className="px-3 py-2 font-medium">状态码</th>
                <th className="px-3 py-2 font-medium">含义与处理</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["401", "key 写错了或已吊销。带了无效 key 不会退回按 IP 计，直接拒绝"],
                ["429", "额度用完，按 Retry-After 头等几秒再试"],
                ["503 EA_BUSY", "全站查询账号忙不过来，和你的额度无关，稍后重试"],
              ].map(([code, desc]) => (
                <tr key={code} className="border-border border-t">
                  <td className="px-3 py-2 font-mono whitespace-nowrap">{code}</td>
                  <td className="px-3 py-2">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {data ? (
        <section className="space-y-3">
          <SectionHeading>额度</SectionHeading>
          <p className="text-muted-foreground text-sm leading-relaxed">
            「查询」类接口要占用本站的 EA
            账号，账号只有几个，额度最紧；「只读」类读本站自己记录的数据，额度宽松。下表是倍数 ×1
            的基础额度，你的 key
            实际额度再乘上它的倍数。本站是公益项目，能缓存的结果请在你那边缓存。
          </p>
          <div className="border-border overflow-x-auto rounded-sm border">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-muted-foreground text-left">
                <tr>
                  <th className="px-3 py-2 font-medium">类别</th>
                  <th className="px-3 py-2 font-medium">每分钟</th>
                  <th className="px-3 py-2 font-medium">每天</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                <tr className="border-border border-t">
                  <td className="px-3 py-2">查询</td>
                  <td className="px-3 py-2">{data.quota.lookup_per_minute}</td>
                  <td className="px-3 py-2">{data.quota.lookup_per_day}</td>
                </tr>
                <tr className="border-border border-t">
                  <td className="px-3 py-2">只读</td>
                  <td className="px-3 py-2">{data.quota.read_per_minute}</td>
                  <td className="px-3 py-2">{data.quota.read_per_day}</td>
                </tr>
                <tr className="border-border border-t">
                  <td className="px-3 py-2">头像</td>
                  <td className="px-3 py-2">{data.quota.avatar_per_minute}</td>
                  <td className="px-3 py-2">—</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section className="space-y-4">
        <SectionHeading>接口列表</SectionHeading>
        <p className="text-muted-foreground text-sm">
          全部是 GET 请求，路径接在 <code className="font-mono">/api/v1</code> 后面。
        </p>
        {ENDPOINTS.map((group) => (
          <div key={group.group} className="space-y-2">
            <h3 className="text-muted-foreground text-xs font-medium tracking-[0.15em] uppercase">
              {group.group}
            </h3>
            <ul className="border-border divide-border divide-y rounded-sm border">
              {group.items.map(([path, desc, bucket]) => (
                <li
                  key={path}
                  className="flex flex-col gap-1 px-3 py-2.5 sm:flex-row sm:items-center sm:gap-4"
                >
                  <code className="min-w-0 font-mono text-sm break-all sm:flex-1">{path}</code>
                  <div className="flex items-center gap-2 text-sm sm:w-72 sm:shrink-0">
                    <span className="text-muted-foreground flex-1">{desc}</span>
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] ${
                        bucket === "lookup"
                          ? "bg-foreground text-background"
                          : "bg-secondary text-secondary-foreground"
                      }`}
                    >
                      {BUCKET_LABEL[bucket]}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <ConfirmSheet
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open);
          if (!open) setName("");
        }}
        title="新建 API Key"
        description="起个名字记住它用在哪，比如机器人的名字。"
        confirmText="创建"
        loading={create.isPending}
        confirmDisabled={!name.trim()}
        onConfirm={() => create.mutate(name.trim())}
      >
        <Input
          autoFocus
          maxLength={32}
          placeholder="比如：战地群机器人"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && name.trim() && !create.isPending) create.mutate(name.trim());
          }}
        />
      </ConfirmSheet>

      <ConfirmSheet
        open={pendingRevoke !== null}
        onOpenChange={(open) => !open && setPendingRevoke(null)}
        title={pendingRevoke ? `吊销「${pendingRevoke.name}」？` : "确认吊销"}
        description="吊销后用这个 key 的请求立即返回 401，不能恢复，只能新建一个。"
        confirmText="吊销"
        variant="destructive"
        loading={revoke.isPending}
        onConfirm={() => {
          if (pendingRevoke) revoke.mutate(pendingRevoke.id);
        }}
      />
    </main>
  );
}
