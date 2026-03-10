// ============================================================
// AKShare 数据接入 API 路由
// - AKSHARE_SERVICE_URL 已配置 → 拉取真实行情（无服务端缓存）
// - 未配置或服务离线 → 回退 Mock 数据
// ============================================================

import { NextResponse } from "next/server";
import { generateAllMockData } from "@/lib/mockData";

// 禁止 Next.js 对此路由做任何缓存，保证每次都取实时数据
export const dynamic = "force-dynamic";

const AKSHARE_SERVICE_URL =
  process.env.AKSHARE_SERVICE_URL?.replace(/\/$/, "") ?? "";

export async function GET() {
  if (AKSHARE_SERVICE_URL) {
    try {
      const res = await fetch(`${AKSHARE_SERVICE_URL}/futures/all`, {
        signal: AbortSignal.timeout(90_000),
        cache: "no-store", // 禁用 fetch 级别的缓存
      });

      if (!res.ok) throw new Error(`AKShare 服务响应 ${res.status}`);

      const data = await res.json();
      if (!Array.isArray(data) || data.length === 0) {
        throw new Error("AKShare 返回数据为空");
      }

      return NextResponse.json({ source: "akshare", data });
    } catch (err) {
      console.error("[API /futures] AKShare 请求失败，回退 Mock:", err);
    }
  }

  const mockData = generateAllMockData(Date.now() % 50000);
  return NextResponse.json({ source: "mock", data: mockData });
}
