"use client";

/**
 * providers.tsx
 *
 * Client-side context providers wrapped around the whole app.
 * SessionProvider makes useSession() available in any client component
 * without having to call auth() on every server component.
 */
import { SessionProvider } from "next-auth/react";

export default function Providers({ children }: { children: React.ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
