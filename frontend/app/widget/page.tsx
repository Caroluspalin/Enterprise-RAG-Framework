"use client";

import { useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { v4 as uuidv4 } from "uuid";
import { streamChat } from "@/lib/api";
import type { Message } from "@/types";
import ChatWindow from "@/components/ChatWindow";
import ChatInput from "@/components/ChatInput";

/**
 * Standalone widget page designed to be embedded via iframe.
 * No sidebar, no auth — just a full-screen chat interface.
 *
 * Supports theme configuration via query parameters:
 *   ?title=Support Bot     — custom title shown in the header bar
 *   ?accent=2563eb         — hex color (without #) for the accent / send button
 *   ?bg=0f172a             — hex color (without #) for the background
 */
function WidgetInner() {
  const searchParams = useSearchParams();
  const title = searchParams.get("title");
  const accent = searchParams.get("accent");
  const bg = searchParams.get("bg");

  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const handleSend = useCallback(
    async (question: string) => {
      if (isStreaming) return;

      const userMessage: Message = {
        id: uuidv4(),
        role: "user",
        content: question,
      };

      const assistantId = uuidv4();
      const assistantPlaceholder: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
      setIsStreaming(true);

      const history = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      try {
        for await (const event of streamChat(question, history)) {
          if (event.type === "token") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: m.content + event.content }
                  : m
              )
            );
          } else if (event.type === "sources") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, sources: event.sources } : m
              )
            );
          } else if (event.type === "done") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, isStreaming: false } : m
              )
            );
          }
        }
      } catch (err) {
        const errorText =
          err instanceof Error ? err.message : "Something went wrong.";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `Error: ${errorText}`, isStreaming: false }
              : m
          )
        );
      } finally {
        setIsStreaming(false);
      }
    },
    [isStreaming, messages]
  );

  // Build inline style overrides from query params.
  const bgStyle = bg ? { backgroundColor: `#${bg}` } : undefined;
  const accentStyle = accent ? `#${accent}` : undefined;

  return (
    <div
      className="flex h-screen w-full flex-col bg-slate-950"
      style={bgStyle}
    >
      {/* Optional header bar — shown when a title is provided */}
      {title && (
        <div
          className="flex items-center gap-2 border-b border-slate-800 px-4 py-2.5"
          style={accentStyle ? { backgroundColor: accentStyle } : undefined}
        >
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
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
          <span className="text-sm font-semibold text-white">{title}</span>
        </div>
      )}

      <ChatWindow messages={messages} />
      <ChatInput
        onSend={handleSend}
        disabled={isStreaming}
        accentColor={accentStyle}
      />
    </div>
  );
}

/**
 * Wrapping in Suspense because useSearchParams() requires it in App Router
 * when the page is statically rendered.
 */
export default function WidgetPage() {
  return (
    <Suspense>
      <WidgetInner />
    </Suspense>
  );
}
