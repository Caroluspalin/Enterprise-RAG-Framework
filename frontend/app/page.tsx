"use client";

import { useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { v4 as uuidv4 } from "uuid";
import {
  streamChat,
  createSession,
  getSessionMessages,
} from "@/lib/api";
import type { Message } from "@/types";
import Sidebar from "@/components/Sidebar";
import ChatWindow from "@/components/ChatWindow";
import ChatInput from "@/components/ChatInput";

export default function Home() {
  const { data: authSession } = useSession();
  const userId = (authSession?.user as { id?: string })?.id ?? "anonymous";

  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  // Bumped to trigger a sidebar re-fetch after creating a new session.
  const [sidebarRefresh, setSidebarRefresh] = useState(0);
  // Mobile sidebar toggle.
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // -----------------------------------------------------------------------
  // New chat — clear messages and session
  // -----------------------------------------------------------------------
  const handleNewChat = useCallback(() => {
    if (isStreaming) return;
    setMessages([]);
    setActiveSessionId(null);
    setSidebarOpen(false);
  }, [isStreaming]);

  // -----------------------------------------------------------------------
  // Load an existing session from the sidebar
  // -----------------------------------------------------------------------
  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      if (isStreaming) return;
      if (sessionId === activeSessionId) return;

      try {
        const { messages: persisted } = await getSessionMessages(sessionId);
        const loaded: Message[] = persisted.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          sources: m.sources ?? undefined,
        }));
        setMessages(loaded);
        setActiveSessionId(sessionId);
      } catch {
        // If the session can't be loaded, start fresh.
        setMessages([]);
        setActiveSessionId(null);
      }
      setSidebarOpen(false);
    },
    [isStreaming, activeSessionId],
  );

  // -----------------------------------------------------------------------
  // Send a message
  // -----------------------------------------------------------------------
  const handleSend = useCallback(
    async (question: string) => {
      if (isStreaming) return;

      // If no active session yet, create one via the API.
      let sessionId = activeSessionId;
      if (!sessionId) {
        try {
          const newSession = await createSession(userId);
          sessionId = newSession.id;
          setActiveSessionId(sessionId);
          // Tell sidebar to re-fetch so the new session appears.
          setSidebarRefresh((n) => n + 1);
        } catch {
          // Fall back to no-persistence mode if the backend is down.
          sessionId = null;
        }
      }

      // Add the user's message immediately.
      const userMessage: Message = {
        id: uuidv4(),
        role: "user",
        content: question,
      };

      // Placeholder for the assistant's streaming response.
      const assistantId = uuidv4();
      const assistantPlaceholder: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
      setIsStreaming(true);

      // Build the history to send (exclude the placeholder we just added).
      const history = messages.map((m) => ({ role: m.role, content: m.content }));

      try {
        for await (const event of streamChat(
          question,
          history,
          sessionId ?? undefined,
          userId,
        )) {
          if (event.type === "token") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: m.content + event.content }
                  : m,
              ),
            );
          } else if (event.type === "sources") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, sources: event.sources } : m,
              ),
            );
          } else if (event.type === "done") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, isStreaming: false } : m,
              ),
            );
            // Refresh sidebar so the auto-generated title shows up.
            setSidebarRefresh((n) => n + 1);
          }
        }
      } catch (err) {
        const errorText =
          err instanceof Error ? err.message : "Something went wrong.";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `Error: ${errorText}`, isStreaming: false }
              : m,
          ),
        );
      } finally {
        setIsStreaming(false);
      }
    },
    [isStreaming, messages, activeSessionId, userId],
  );

  return (
    <div className="flex h-full bg-slate-950">
      {/* Mobile overlay backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar — always visible on md+, slide-over on mobile */}
      <div
        className={`fixed inset-y-0 left-0 z-40 transition-transform duration-200 md:relative md:z-auto md:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Sidebar
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          refreshKey={sidebarRefresh}
        />
      </div>

      {/* Chat panel */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile top bar with hamburger */}
        <div className="flex items-center gap-3 border-b border-slate-800 px-4 py-2 md:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            aria-label="Open sidebar"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="text-sm font-semibold text-slate-200">DocChat</span>
        </div>

        <ChatWindow messages={messages} />
        <ChatInput onSend={handleSend} disabled={isStreaming} />
      </div>
    </div>
  );
}
