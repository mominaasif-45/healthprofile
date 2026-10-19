import type { NextConfig } from "next";

// The browser only ever talks to Next.js. Every /api/* call is forwarded to
// Django, so the browser sees ONE origin: cookies work with SameSite=Lax
// and no CORS setup is needed.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Django's URLs end with "/", so don't let Next strip the slash.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      { source: "/api/:path*/", destination: `${BACKEND_URL}/api/:path*/` },
      { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*/` },
    ];
  },
};

export default nextConfig;
