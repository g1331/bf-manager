import type { Metadata, Viewport } from "next";
import { Inter, Oswald } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Toaster } from "@/components/ui/sonner";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

// 工业风 condensed 字体，用于品牌标题与展示性大字（对标 BF/CoD 官方的 DIN/Industry 字形）
const oswald = Oswald({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "BF-Manager",
    template: "%s · BF-Manager",
  },
  description: "Battlefield 系列战绩查询与服务器管理平台",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    // 不透明黑色状态栏：网页从状态栏下方开始排版，顶栏、吸顶导航都不会被时间和刘海压住。
    // black-translucent 会把网页铺到状态栏底下，每个贴顶元素都得自己补 safe-area-inset-top；
    // default 是白底状态栏，放在深色站上很突兀。
    statusBarStyle: "black",
    title: "BF-Manager",
  },
  icons: {
    icon: [
      { url: "/icons/icon.svg", type: "image/svg+xml" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    // iOS 不认 SVG 的 apple-touch-icon；这张不透明、无圆角，圆角由系统加
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5efe6" },
    { media: "(prefers-color-scheme: dark)", color: "#1a1208" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning className={`${inter.variable} ${oswald.variable}`}>
      <body className="bg-background text-foreground min-h-screen antialiased">
        <Providers>
          {children}
          <Toaster position="top-center" />
        </Providers>
      </body>
    </html>
  );
}
