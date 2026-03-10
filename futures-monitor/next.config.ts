import type { NextConfig } from "next";
import path from "path";

const isProd = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  // 生产构建输出纯静态文件到 out/，供 Cloudflare Pages 直接托管
  output: isProd ? "export" : undefined,

  // 静态导出不支持 Next.js Image Optimization，需关闭
  images: { unoptimized: true },

  // 修复 Turbopack 对中文路径的 byte-boundary bug
  turbopack: {
    root: path.resolve(__dirname),
  },

  // 关闭遥测
  // env 中若有 NEXT_TELEMETRY_DISABLED=1 则已生效，这里保持干净
};

export default nextConfig;
