import { execSync } from "node:child_process";
import type { NextConfig } from "next";

/** 对外宣传用的固定局域网入口（书签 / .env.local / 文档） */
const LAN_FIXED_HOST = process.env.LAN_FIXED_IP?.trim() || "10.13.199.162";

/** 探测当前出网网卡 IP，仅用于 HMR 白名单兜底（DHCP 漂移时也不拦 /_next） */
function detectLanHostname(): string | null {
  try {
    const out = execSync(
      "ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i==\"src\") {print $(i+1); exit}}'",
      { encoding: "utf8" },
    ).trim();
    return out || null;
  } catch {
    return null;
  }
}

/** Tailscale 访问工作台时，浏览器 Origin 使用完整 DNS 名称。 */
function detectTailnetHostname(): string | null {
  try {
    const raw = execSync("tailscale status --json 2>/dev/null", { encoding: "utf8" }).trim();
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { Self?: { DNSName?: string } };
    return parsed.Self?.DNSName?.replace(/\.$/, "") || null;
  } catch {
    return null;
  }
}

function normalizeHost(raw: string): string {
  return raw.trim().replace(/^https?:\/\//, "").replace(/:\d+$/, "");
}

const extraOrigins = (process.env.NEXT_ALLOWED_DEV_ORIGINS || "")
  .split(",")
  .map(normalizeHost)
  .filter(Boolean);

const liveHost = detectLanHostname();
const tailnetHost = detectTailnetHostname();

const allowedDevOrigins = Array.from(
  new Set(
    [
      "localhost",
      "127.0.0.1",
      LAN_FIXED_HOST,
      liveHost,
      tailnetHost,
      ...extraOrigins,
    ].filter((h): h is string => Boolean(h)),
  ),
);

const nextConfig: NextConfig = {
  // Production deployment uses the self-contained server bundle; local dev keeps .next.
  output: 'standalone',
  distDir: process.env.NEXT_DIST_DIR || '.next',
  // Next 16：hostname only。固定 IP 方便地址；liveHost 防止换 IP 后再整页刷新
  allowedDevOrigins,
  // public/videos 供 :8767 阅片 Agent 深链播放时跨域读取
  async headers() {
    return [
      {
        source: "/videos/:path*",
        headers: [
          { key: "Access-Control-Allow-Origin", value: "*" },
          { key: "Cross-Origin-Resource-Policy", value: "cross-origin" },
        ],
      },
    ];
  },
  images: {
    // 允许通过内部 API 路由加载图片
    remotePatterns: [],
    // API 路由图片不走 Next 优化管道，避免 no image
    unoptimized: true,
    formats: ["image/avif", "image/webp"],
    deviceSizes: [640, 750, 828, 1080, 1200, 1920, 2048, 3840],
    imageSizes: [16, 32, 48, 64, 96, 128, 256, 384],
  },
};

export default nextConfig;
