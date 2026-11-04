import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ai-dev-digest",
  description: "生成 AI の開発に関する公式の発信を、日付ごとにまとめます。",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
