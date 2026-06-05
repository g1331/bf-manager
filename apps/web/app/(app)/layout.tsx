import { SidebarLayout } from "@/components/layout/SidebarLayout";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <SidebarLayout>{children}</SidebarLayout>;
}
