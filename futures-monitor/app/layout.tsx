import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["300", "400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "期货品种监控 | Futures Monitor",
  description: "30分钟周期期货品种状态监控 Dashboard — 均线、MACD、成交量、持仓量",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark">
      <body className={`${jetbrainsMono.variable} font-mono bg-gray-950 antialiased`}>
        {children}
      </body>
    </html>
  );
}
