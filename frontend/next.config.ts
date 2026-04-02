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
      { source: "/api/chat",                     destination: `${backend}/api/chat` },
      { source: "/api/chat/sessions",             destination: `${backend}/api/chat/sessions` },
      { source: "/api/chat/sessions/:id",         destination: `${backend}/api/chat/sessions/:id` },
      { source: "/api/upload",                    destination: `${backend}/api/upload` },
      { source: "/api/documents",                 destination: `${backend}/api/documents` },
      { source: "/api/documents/:filename",       destination: `${backend}/api/documents/:filename` },
      { source: "/api/health",                    destination: `${backend}/api/health` },
    ];
  },
};

export default nextConfig;
