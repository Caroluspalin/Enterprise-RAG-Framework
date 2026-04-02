"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { listDocuments, getSessions, deleteSession } from "@/lib/api";
import type { Document, ChatSession } from "@/types";
import SignOutButton from "@/components/SignOutButton";

interface SidebarProps {
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  /** Bumped by the parent whenever a new session is created so we re-fetch. */
  refreshKey?: number;
}

export default function Sidebar({
  activeSessionId,
  onSelectSession,
  onNewChat,
  refreshKey,
}: SidebarProps) {
  const { data: session } = useSession();
  const isAdmin = (session?.user as { role?: string })?.role === "admin";
  const userId = session?.user?.email ?? "anonymous";

  const [documents, setDocuments] = useState<Document[]>([]);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [loadingSessions, setLoadingSessions] = useState(true);

  const fetchDocs = useCallback(async () => {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch {
      // Backend may not be running yet during development.
    } finally {
      setLoadingDocs(false);
    }
  }, []);

  const fetchSessions = useCallback(async () => {
    try {
      const sessions = await getSessions(userId);
      setChatSessions(sessions);
    } catch {
      // Backend may not be running yet during development.
    } finally {
      setLoadingSessions(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions, refreshKey]);

  const handleDelete = useCallback(
    async (e: React.MouseEvent, sessionId: string) => {
      // Stop the click from also selecting the session.
      e.stopPropagation();
      try {
        await deleteSession(sessionId);
        setChatSessions((prev) => prev.filter((s) => s.id !== sessionId));
        // If the deleted session was active, reset to a blank chat.
        if (sessionId === activeSessionId) {
          onNewChat();
        }
      } catch {
        // Ignore — session may already be gone.
      }
    },
    [activeSessionId, onNewChat],
  );

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-900">
      {/* Header */}
      <div className="border-b border-slate-800 px-4 py-4">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600">
            <svg
              className="h-4 w-4 text-white"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-100">DocChat</p>
            <p className="text-xs text-slate-500">B2B RAG Assistant</p>
          </div>
        </div>
      </div>

      {/* New Chat button */}
      <div className="px-3 pt-3">
        <button
          onClick={onNewChat}
          className="flex w-full items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-800"
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
              d="M12 4v16m8-8H4"
            />
          </svg>
          New chat
        </button>
      </div>

      {/* Chat sessions list */}
      <div className="flex flex-col overflow-hidden">
        <p className="px-4 pt-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
          History
        </p>

        {loadingSessions ? (
          <p className="px-4 py-3 text-xs text-slate-500">Loading...</p>
        ) : chatSessions.length === 0 ? (
          <p className="px-4 py-3 text-xs text-slate-500">
            No conversations yet.
          </p>
        ) : (
          <ul className="max-h-48 overflow-y-auto px-3 py-1">
            {chatSessions.map((cs) => (
              <li
                key={cs.id}
                onClick={() => onSelectSession(cs.id)}
                className={`group flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-xs transition-colors ${
                  cs.id === activeSessionId
                    ? "bg-slate-800 text-slate-100"
                    : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                }`}
              >
                <svg
                  className="h-3.5 w-3.5 shrink-0 text-slate-500"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                  />
                </svg>
                <span className="flex-1 truncate">{cs.title}</span>
                {/* Delete button — visible on hover */}
                <button
                  onClick={(e) => handleDelete(e, cs.id)}
                  className="hidden shrink-0 rounded p-0.5 text-slate-500 transition-colors hover:bg-slate-700 hover:text-red-400 group-hover:block"
                  aria-label={`Delete "${cs.title}"`}
                >
                  <svg
                    className="h-3.5 w-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Document list */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <p className="px-4 pt-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
          Documents
        </p>

        {loadingDocs ? (
          <p className="px-4 py-3 text-xs text-slate-500">Loading...</p>
        ) : documents.length === 0 ? (
          <p className="px-4 py-3 text-xs text-slate-500">
            No documents ingested yet.
          </p>
        ) : (
          <ul className="flex-1 overflow-y-auto px-3 py-2">
            {documents.map((doc) => (
              <li
                key={doc.name}
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                title={doc.size_kb != null ? `${doc.name} (${doc.size_kb} KB)` : doc.name}
              >
                <svg
                  className="h-3.5 w-3.5 shrink-0 text-slate-500"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                  />
                </svg>
                <span className="truncate">{doc.name}</span>
                {doc.size_kb != null && (
                  <span className="ml-auto shrink-0 text-slate-600">
                    {doc.size_kb}k
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Footer: admin link + sign out */}
      <div className="border-t border-slate-800 p-3 space-y-2">
        {isAdmin && (
          <Link
            href="/admin"
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200"
          >
            <svg
              className="h-3.5 w-3.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
            Admin Panel
          </Link>
        )}
        <div className="flex items-center justify-between px-1">
          <span className="text-xs text-slate-600">{session?.user?.name}</span>
          <SignOutButton />
        </div>
      </div>
    </aside>
  );
}
