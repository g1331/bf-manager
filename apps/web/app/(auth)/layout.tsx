import Link from "next/link";

/**
 * 登录、注册、验证链接、找回密码、绑定 EA 这几页共用的深色战地外壳：
 * 与首页、应用内深色基调连贯，避免浅色卡片「哗白」突兀。
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="dark text-foreground relative flex min-h-screen flex-col bg-black">
      {/* 战地背景：静态大图 + 渐变遮罩压暗，保证表单文字与输入框可读。
          用 absolute inset-0 置于内容流首位，靠 DOM 顺序压在底层，避免 -z-10 被父背景遮挡 */}
      <div className="absolute inset-0" aria-hidden>
        {/* EA 素材域不在 next/image remotePatterns 内，且为静态首屏图，用原生 img */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/bf1/backgrounds/general/general-3.jpg"
          alt=""
          className="h-full w-full object-cover object-center"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/85 to-black/55" />
        <div className="absolute inset-0 bg-gradient-to-r from-black/70 to-transparent" />
      </div>

      {/* relative z-10：压在上面绝对定位的背景层之上，否则链接被盖住、点不到 */}
      <header className="relative z-10 flex items-center justify-between px-4 py-2 sm:px-10 sm:py-6">
        <Link
          href="/"
          className="font-display text-base font-semibold tracking-[0.2em] text-white uppercase"
        >
          BF-Manager
        </Link>
        <Link
          href="/"
          className="text-sm tracking-wide text-white/60 uppercase transition-colors hover:text-white"
        >
          返回首页
        </Link>
      </header>

      <main className="relative z-10 flex flex-1 items-start justify-center px-4 pt-6 pb-8 sm:items-center sm:py-12">
        {children}
      </main>
    </div>
  );
}
