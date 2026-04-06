"use client";

import { useCallback, useEffect, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ToastType = "success" | "error" | "info";

export interface ToastMessage {
  id: number;
  type: ToastType;
  text: string;
}

// ---------------------------------------------------------------------------
// Hook — call addToast() from any component that renders <ToastContainer />
// ---------------------------------------------------------------------------

let _nextId = 0;
let _addListener: ((t: ToastMessage) => void) | null = null;

/**
 * Fire-and-forget toast from anywhere.
 * The component using <ToastContainer /> will pick it up.
 */
export function toast(type: ToastType, text: string) {
  _addListener?.({ id: ++_nextId, type, text });
}

// ---------------------------------------------------------------------------
// Container — renders all active toasts, auto-dismisses after 4s
// ---------------------------------------------------------------------------

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = useCallback((t: ToastMessage) => {
    setToasts((prev) => [...prev, t]);
  }, []);

  // Register the global listener so toast() calls reach this component.
  useEffect(() => {
    _addListener = addToast;
    return () => {
      _addListener = null;
    };
  }, [addToast]);

  // Auto-dismiss after 4 seconds.
  useEffect(() => {
    if (toasts.length === 0) return;
    const timer = setTimeout(() => {
      setToasts((prev) => prev.slice(1));
    }, 4000);
    return () => clearTimeout(timer);
  }, [toasts]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`animate-slide-in rounded-lg px-4 py-3 text-sm font-medium shadow-lg ${
            t.type === "success"
              ? "bg-emerald-900/90 text-emerald-200"
              : t.type === "error"
                ? "bg-red-900/90 text-red-200"
                : "bg-slate-800/90 text-slate-200"
          }`}
          role="alert"
        >
          {t.text}
        </div>
      ))}
    </div>
  );
}
