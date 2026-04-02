/**
 * Admin page — server component.
 *
 * Reads the session on the server before rendering so non-admin users are
 * redirected immediately without a client-side flash.
 */
import { auth } from "@/auth";
import { redirect } from "next/navigation";
import Link from "next/link";
import AdminPanel from "@/components/AdminPanel";
import SignOutButton from "@/components/SignOutButton";

export default async function AdminPage() {
  const session = await auth();

  // Guard: only users with role === "admin" may access this page.
  if (!session || (session.user as { role?: string }).role !== "admin") {
    redirect("/");
  }

  return (
    <div className="flex h-full flex-col bg-slate-950">
      {/* Top bar */}
      <header className="shrink-0 border-b border-slate-800 bg-slate-900 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-slate-200"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 19l-7-7 7-7"
                />
              </svg>
              Back to chat
            </Link>
            <span className="text-slate-700">|</span>
            <h1 className="text-sm font-semibold text-white">Admin Panel</h1>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500">{session.user?.name}</span>
            <SignOutButton />
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto px-6 py-8">
        <div className="mx-auto max-w-3xl">
          <AdminPanel />
        </div>
      </main>
    </div>
  );
}
