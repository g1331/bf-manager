import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CodexArticle } from "@/components/bf1/codex/CodexArticle";
import { CodexBack, CodexCopyActions } from "@/components/bf1/codex/CodexActions";
import { CodexCard, CodexPlate } from "@/components/bf1/codex/CodexCard";
import { CodexFootnote } from "@/components/bf1/codex/CodexHeader";
import {
  Breadcrumbs,
  DetailPanel,
  type StepItem,
  StepNav,
} from "@/components/bf1/codex/DetailParts";
import { ZoomableImage } from "@/components/bf1/codex/ZoomableImage";
import {
  CODEX_ENTRIES,
  CODEX_IMAGE_HEIGHT,
  CODEX_IMAGE_WIDTH,
  type CodexEntry,
  codexImage,
  codexKind,
  codexListHref,
  codexNeighbors,
  codexRelated,
  codexSrcSet,
  getCodexEntry,
} from "@/lib/bf1/codex/codex";
import texts from "@/lib/bf1/codex/data/codex-text.json";

// 正文 JSON 只在服务端读，每页只把自己那一段带进 HTML
const TEXTS = texts as Record<string, string>;

export const dynamicParams = false;

export function generateStaticParams() {
  return CODEX_ENTRIES.map((e) => ({ code: e.code }));
}

interface Props {
  params: Promise<{ game: string; code: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const entry = getCodexEntry((await params).code);
  if (!entry) return {};
  const body = TEXTS[entry.code] ?? "";
  const description = `${entry.header !== entry.name ? `${entry.header}。` : ""}${body.replace(/\s+/g, " ").slice(0, 90)}…`;
  return {
    // 静态导出时没有请求域名，分享卡片的图片地址按正式站点拼成绝对地址
    metadataBase: new URL("https://bfm.umrbotech.com"),
    title: `${entry.name} · 战地 1 百科`,
    description,
    openGraph: {
      title: entry.name,
      description,
      images: [
        { url: codexImage(entry.code), width: CODEX_IMAGE_WIDTH, height: CODEX_IMAGE_HEIGHT },
      ],
    },
  };
}

export default async function CodexEntryPage({ params }: Props) {
  const entry = getCodexEntry((await params).code);
  if (!entry) notFound();
  const body = TEXTS[entry.code] ?? "";
  const { prev, next } = codexNeighbors(entry.code);
  const related = codexRelated(entry, 6);

  return (
    <main className="mx-auto max-w-6xl px-4 py-4 text-white sm:py-8">
      <CodexBack fallback="/bf1/codex" />

      <Breadcrumbs
        items={[
          { label: "图鉴", href: "/bf1/codex" },
          { label: "百科", href: "/bf1/codex" },
          {
            label: codexKind(entry),
            href: codexListHref({ cat: entry.category, wc: entry.weaponClass }),
          },
        ]}
      />

      <div className="mt-5 grid items-start gap-7 lg:mt-6 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)] lg:gap-14">
        <div className="lg:sticky lg:top-6">
          <ZoomableImage
            src={codexImage(entry.code)}
            srcSet={codexSrcSet(entry.code)}
            sizes="(min-width: 640px) 400px, 300px"
            alt={entry.name}
            width={CODEX_IMAGE_WIDTH}
            height={CODEX_IMAGE_HEIGHT}
            priority
            className="@container mx-auto w-full max-w-[300px] rounded-[6px] shadow-[0_30px_60px_-24px_#000] ring-1 ring-white/10 sm:max-w-[400px]"
          >
            <CodexPlate entry={entry} />
          </ZoomableImage>
          <p className="mt-2 text-center text-[11px] text-white/40">
            <span className="hidden lg:inline">点击图片放大 2 倍，移动鼠标看细节</span>
            <span className="lg:hidden">点按图片放大，拖动看细节</span>
          </p>
        </div>

        <DetailPanel>
          <CodexArticle entry={entry} body={body} as="h1" />
          <div className="mt-7 border-t border-white/10 pt-4">
            <CodexCopyActions entry={entry} body={body} />
          </div>
        </DetailPanel>
      </div>

      <StepNav prev={prev && stepItem(prev)} next={next && stepItem(next)} />

      {related.length ? (
        <section className="mt-12">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-base font-semibold tracking-wide">
              同类条目
              <span className="ml-2 text-xs font-normal tracking-wider text-amber-400/75">
                {codexKind(entry)}
              </span>
            </h2>
            <Link
              href={codexListHref({ cat: entry.category, wc: entry.weaponClass })}
              className="inline-action text-xs text-amber-400/90 underline-offset-4 hover:underline"
            >
              查看全部
            </Link>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-x-2.5 gap-y-5 sm:grid-cols-6 sm:gap-x-4">
            {related.map((e) => (
              <CodexCard key={e.code} entry={e} sizes="(min-width: 640px) 160px, 31vw" />
            ))}
          </div>
        </section>
      ) : null}

      <CodexFootnote />
    </main>
  );
}

function stepItem(e: CodexEntry): StepItem {
  return {
    href: `/bf1/codex/${e.code}`,
    name: e.name,
    image: codexImage(e.code, 480),
    shape: "card",
  };
}
