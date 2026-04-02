"use client";

import { useState, useCallback } from "react";
import { v4 as uuidv4 } from "uuid";
import { streamChat } from "@/lib/api";
import type { Message } from "@/types";
import ChatWindow from "@/components/ChatWindow";
import ChatInput from "@/components/ChatInput";

/**
 * Standalone widget page designed to be embedded via iframe.
 * No sidebar, no auth — just a full-screen chat interface.
 */
export default function WidgetPage() {
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
      history.push({ role: "user", content: question });

      try {
        for await (const event of streamChat(question, history.slice(0, -1))) {
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

  return (
    <div className="flex h-screen w-full flex-col bg-slate-950">
      <ChatWindow messages={messages} />
      <ChatInput onSend={handleSend} disabled={isStreaming} />
    </div>
  );
}
