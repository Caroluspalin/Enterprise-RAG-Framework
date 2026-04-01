import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Tell Turbopack where the project root is so it doesn't get confused by
  // a package-lock.json that exists in a parent directory.
  turbopack: {
    root: __dirname,
  },
  // Proxy /api/* requests to the FastAPI backend during development.
  // In production, configure your reverse proxy (nginx, etc.) instead.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
