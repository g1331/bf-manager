"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { LogIn, LogOut, ScrollText, ShieldCheck } from "lucide-react";
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

export function UserMenu() {
  const session = useSession();
  const router = useRouter();
  const qc = useQueryClient();

  if (session.isLoading) {
    return <div className="bg-muted size-9 animate-pulse rounded-full" aria-hidden />;
  }

  const user = session.data;

  if (!user) {
    return (
      <Button variant="outline" size="sm" asChild>
        <Link href="/login">
          <LogIn className="size-4" />
          登录
        </Link>
      </Button>
    );
  }

  const initial = (user.display_name ?? `#${user.persona_id}`).slice(0, 1).toUpperCase();
  const isAdmin = user.role === "admin";

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
          className="border-border focus-visible:ring-ring bg-muted relative inline-flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-full border text-sm font-semibold transition focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          {user.avatar_url ? (
            // EA 头像域不在 next/image remotePatterns 内，用原生 img
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={user.avatar_url}
              alt={user.display_name ?? "avatar"}
              className="size-full object-cover"
            />
          ) : (
            <span>{initial}</span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="truncate">{user.display_name ?? `Persona ${user.persona_id}`}</span>
          <span className="text-muted-foreground text-xs font-normal">ID {user.persona_id}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/audit-logs">
            <ScrollText className="size-4" />
            操作日志
          </Link>
        </DropdownMenuItem>
        {isAdmin ? (
          <DropdownMenuItem asChild>
            <Link href="/admin/memberships">
              <ShieldCheck className="size-4" />
              服管权限授予
            </Link>
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onLogout} className="text-destructive focus:text-destructive">
          <LogOut className="size-4" />
          退出登录
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
