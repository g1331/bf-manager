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
          title: "group-[.toast]:text-popover-foreground group-[.toast]:font-medium",
          description: "group-[.toast]:text-muted-foreground",
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
