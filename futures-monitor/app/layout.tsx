import type { Metadata } from "next";
import { JetBrains_Mono, Inter } from "next/font/google";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["300", "400", "500", "600", "700"],
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  weight: ["300", "400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "期货品种监控 | Futures Monitor — Redesign v2",
  description: "30分钟周期期货品种状态监控 Dashboard — 均线、MACD、成交量、持仓量 · Inter + Amber Design System",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark">
      <body className={`${jetbrainsMono.variable} ${inter.variable} font-sans bg-gray-950 text-gray-100 antialiased`}>
        {children}
      </body>
    </html>
  );
}
