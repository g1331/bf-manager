"use client";

import { Toaster as SonnerToaster } from "sonner";

export function Toaster(props: React.ComponentProps<typeof SonnerToaster>) {
  return (
    <SonnerToaster
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-popover group-[.toaster]:text-popover-foreground " +
            "group-[.toaster]:border group-[.toaster]:border-border group-[.toaster]:shadow-lg",
          // title / description 不固定颜色，继承 toast 根的 color。
          // sonner 内部默认会给 description 一个浅灰，必须用 !important 覆盖，
          // 否则 error toast 的红底上仍会出现 muted 灰字、几乎不可见。
          title: "group-[.toast]:!text-inherit group-[.toast]:font-medium",
          description: "group-[.toast]:!text-inherit group-[.toast]:opacity-80",
          actionButton: "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton: "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
          closeButton:
            "group-[.toast]:bg-popover group-[.toast]:text-popover-foreground group-[.toast]:border-border",
          error: "!bg-destructive !text-destructive-foreground !border-destructive",
        },
      }}
      {...props}
    />
  );
}
