/**
 * middleware.ts
 *
 * Runs on every request to enforce authentication.
 *
 * - Unauthenticated users are redirected to /login.
 * - Already-authenticated users visiting /login are redirected to /.
 * - /api/auth/* is excluded so NextAuth's own route handler can respond.
 */
import { auth } from "./auth";
import { NextResponse } from "next/server";

export default auth((req) => {
  const isLoggedIn = !!req.auth;
  const { pathname } = req.nextUrl;

  // Let NextAuth handle its own API routes without interference.
  if (pathname.startsWith("/api/auth")) return NextResponse.next();

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
