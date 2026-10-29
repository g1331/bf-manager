import { ErrorState } from "@/components/common/ErrorState";

export const metadata = { title: "页面不存在" };

export default function NotFound() {
  return (
    <div className="dark bg-background text-foreground flex min-h-screen items-center justify-center">
      <ErrorState
        kicker="404"
        title="页面不存在"
        description="链接可能已失效，或者地址输错了。"
        homeHref="/"
      />
    </div>
  );
}
