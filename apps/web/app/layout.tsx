import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Toaster } from "@/components/ui/sonner";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
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
    statusBarStyle: "black-translucent",
    title: "BF-Manager",
    // iOS Safari 不支持 SVG 作为 apple-touch-icon，但平台主流 (Android / Chrome / Edge)
    // 都识别 manifest 里的 SVG，所以 SVG 单图就够覆盖 MVP；iOS PWA 安装后会 fallback
    // 到首字母圆形图。后续 UI 出图时把 PNG 192/512 补上即可。
  },
  icons: {
    icon: [{ url: "/icons/icon.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icons/icon.svg", type: "image/svg+xml" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning className={inter.variable}>
      <body className="bg-background text-foreground min-h-screen antialiased">
        <Providers>
          {children}
          <Toaster closeButton position="top-center" />
        </Providers>
      </body>
    </html>
  );
}
