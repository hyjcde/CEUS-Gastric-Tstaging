import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "突破方向标注工具",
  description: "胃癌 EUS 突破方向标注",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="bg-[#010409] text-[#f0f6fc] antialiased">{children}</body>
    </html>
  );
}
