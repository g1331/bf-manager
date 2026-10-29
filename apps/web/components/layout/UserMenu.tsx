"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { LogIn, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSession } from "@/hooks/useSession";
import { logout } from "@/lib/auth";
import { cn } from "@/lib/utils";

/** compact：手机端顶栏用，未登录时是纯文字「登录」，头像缩到 32px。 */
export function UserMenu({ compact = false }: { compact?: boolean }) {
  const session = useSession();
  const router = useRouter();
  const qc = useQueryClient();

  if (session.isLoading) {
    return (
      <div
        className={cn("bg-muted animate-pulse rounded-full", compact ? "size-8" : "size-9")}
        aria-hidden
      />
    );
  }

  const user = session.data;

  if (!user) {
    if (compact) {
      return (
        <Link
          href="/login"
          className="flex h-11 items-center px-2 text-[15px] font-medium text-amber-400 active:text-amber-300"
        >
          登录
        </Link>
      );
    }
    return (
      <Button variant="outline" size="sm" asChild>
        <Link href="/login">
          <LogIn className="size-4" />
          登录
        </Link>
      </Button>
    );
  }

  const primary = user.primary_binding;
  const displayLabel = primary?.display_name ?? user.username;
  const subtitleLabel = primary ? `Persona ${primary.persona_id}` : "本地账号（无 EA 绑定）";
  const initial = displayLabel.slice(0, 1).toUpperCase();

  const onLogout = async () => {
    try {
      await logout();
      qc.setQueryData(["session"], null);
      toast.success("已退出登录");
      router.push("/");
      router.refresh();
    } catch {
      toast.error("退出登录失败，请稍后重试");
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="用户菜单"
          className={cn(
            "border-border focus-visible:ring-ring bg-muted relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full border text-sm font-semibold transition focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none",
            compact ? "size-8" : "size-9",
          )}
        >
          {primary?.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={primary.avatar_url} alt={displayLabel} className="size-full object-cover" />
          ) : (
            <span>{initial}</span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="dark w-56">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="truncate">{displayLabel}</span>
          <span className="text-muted-foreground text-xs font-normal">{subtitleLabel}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onLogout} className="text-destructive focus:text-destructive">
          <LogOut className="size-4" />
          退出登录
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
