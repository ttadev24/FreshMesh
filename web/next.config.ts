import type { NextConfig } from "next";

// FastAPI gateway (api/main.py). The browser only ever talks to /api/* on the Next origin;
// Next proxies it so the token never crosses origins and CORS is not needed.
const apiOrigin = (process.env.FRESHMESH_API_URL ?? "http://localhost:8100").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Allows the dev server's HMR/_next resources to be reached when the page is loaded
  // from the host's LAN IP instead of localhost (e.g. over SSH port access).
  allowedDevOrigins: ["192.168.92.67", "127.0.0.1", "localhost"],
  // The agent chat endpoint streams Server-Sent Events through the rewrite proxy; gzip would
  // buffer the stream until the turn ends.
  compress: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
};

export default nextConfig;
