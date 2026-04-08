import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Tell Turbopack where the project root is so it doesn't get confused by
  // a package-lock.json that exists in a parent directory.
  turbopack: {
    root: __dirname,
  },
  // Disable the dev-mode indicator ("N" badge) so it does not overlap the
  // chat input inside the embeddable widget iframe.
  devIndicators: false,
  // Proxy only the RAG-specific routes to the FastAPI backend.
  // /api/auth/* is intentionally omitted — NextAuth handles those internally.
  // In production, configure your reverse proxy (nginx, etc.) instead.
  async rewrites() {
    const backend =
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [
      { source: "/api/v1/chat",                     destination: `${backend}/api/v1/chat` },
      { source: "/api/v1/chat/sessions",             destination: `${backend}/api/v1/chat/sessions` },
      { source: "/api/v1/chat/sessions/:id",         destination: `${backend}/api/v1/chat/sessions/:id` },
      { source: "/api/v1/upload",                    destination: `${backend}/api/v1/upload` },
      { source: "/api/v1/documents",                 destination: `${backend}/api/v1/documents` },
      { source: "/api/v1/documents/:filename",       destination: `${backend}/api/v1/documents/:filename` },
      { source: "/api/v1/health",                    destination: `${backend}/api/v1/health` },
      { source: "/api/v1/auth/login",                destination: `${backend}/api/v1/auth/login` },
      { source: "/api/v1/auth/register",             destination: `${backend}/api/v1/auth/register` },
      { source: "/api/v1/analytics",                 destination: `${backend}/api/v1/analytics` },
    ];
  },
};

export default nextConfig;
