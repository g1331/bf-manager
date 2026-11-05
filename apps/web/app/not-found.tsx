import { ErrorState } from "@/components/common/ErrorState";
import { NotFoundTip } from "@/components/layout/NotFoundTip";

export const metadata = { title: "页面不存在" };

export default function NotFound() {
  return (
    <div className="dark bg-background text-foreground flex min-h-screen flex-col items-center justify-center px-4">
      <ErrorState
        kicker="404"
        title="页面不存在"
        description="链接可能已失效，或者地址输错了。"
        homeHref="/"
      />
      <NotFoundTip />
    </div>
  );
}
