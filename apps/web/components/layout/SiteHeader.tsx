"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { UserMenu } from "@/components/layout/UserMenu";

interface SiteHeaderProps {
  /** 显示返回按钮（取代左侧 logo） */
  showBack?: boolean;
}

export function SiteHeader({ showBack = false }: SiteHeaderProps) {
  const router = useRouter();
  return (
    <header className="bg-background/95 supports-[backdrop-filter]:bg-background/60 sticky top-0 z-40 border-b backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:px-6">
        {showBack ? (
          <Button
            variant="ghost"
            size="sm"
            className="-ml-2 gap-1.5 px-2"
            onClick={() => router.back()}
          >
            <ArrowLeft className="size-4" />
            <span>返回</span>
          </Button>
        ) : (
          <Link href="/" className="font-semibold tracking-tight">
            BF-Manager
          </Link>
        )}
        <div className="ml-auto">
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
