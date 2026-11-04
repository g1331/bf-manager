/**
 * BF6 页面外壳：主题色切到 BF6 的信号橙，铺一层深色底盖住 BF1 的战场氛围背景。
 */
export default function Bf6Layout({ children }: { children: React.ReactNode }) {
  return (
    <div data-theme="bf6" className="text-bf6-fg lg:h-full lg:min-h-0">
      <div
        aria-hidden
        className="bg-bf6-bg pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(1200px_600px_at_80%_-10%,rgba(255,90,31,0.07),transparent_60%)]"
      />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
