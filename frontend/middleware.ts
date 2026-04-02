/**
 * middleware.ts
 *
 * Runs on every request to enforce authentication.
 *
 * - Unauthenticated users are redirected to /login.
 * - Already-authenticated users visiting /login are redirected to /.
 * - /api/auth/* is excluded so NextAuth's own route handler can respond.
 * - /widget is publicly accessible (no auth) and includes frame-ancestors
 *   CSP so it can be embedded in allowed origins.
 */
import { auth } from "./auth";
import { NextResponse } from "next/server";

/**
 * Origins allowed to embed the /widget route in an iframe.
 * "*" means any origin can embed it (open).  In production, replace with
 * specific origins like "https://example.com https://app.example.com".
 *
 * Set via the WIDGET_ALLOWED_ORIGINS env var (space-separated list of origins).
 */
const ALLOWED_ORIGINS = process.env.WIDGET_ALLOWED_ORIGINS ?? "*";

export default auth((req) => {
  const isLoggedIn = !!req.auth;
  const { pathname } = req.nextUrl;

  // Let NextAuth handle its own API routes without interference.
  if (pathname.startsWith("/api/auth")) return NextResponse.next();

  // Widget route: no auth required, and allow iframe embedding.
  if (pathname.startsWith("/widget")) {
    const response = NextResponse.next();

    // frame-ancestors controls which origins can embed this page in an iframe.
    // Unlike X-Frame-Options it supports multiple origins and wildcards.
    const frameAncestors =
      ALLOWED_ORIGINS === "*" ? "'self' *" : `'self' ${ALLOWED_ORIGINS}`;
    response.headers.set(
      "Content-Security-Policy",
      `frame-ancestors ${frameAncestors}`,
    );
    // Remove the default X-Frame-Options header that some frameworks add,
    // because it would conflict with the CSP frame-ancestors directive.
    response.headers.delete("X-Frame-Options");
    return response;
  }

  if (!isLoggedIn && pathname !== "/login") {
    return NextResponse.redirect(new URL("/login", req.url));
  }

  // Prevent a logged-in user from landing on the login page again.
  if (isLoggedIn && pathname === "/login") {
    return NextResponse.redirect(new URL("/", req.url));
  }

  return NextResponse.next();
});

export const config = {
  // Run on all paths except Next.js build artefacts and static assets.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
