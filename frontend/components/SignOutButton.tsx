"use client";

import { signOut } from "next-auth/react";

interface SignOutButtonProps {
  className?: string;
}

export default function SignOutButton({ className }: SignOutButtonProps) {
  return (
    <button
      onClick={() => signOut({ callbackUrl: "/login" })}
      className={
        className ??
        "rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-400 transition-colors hover:border-slate-500 hover:text-slate-200"
      }
    >
      Sign out
    </button>
  );
}
