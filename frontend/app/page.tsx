"use client";

import { useState, useCallback } from "react";
import { v4 as uuidv4 } from "uuid";
import { streamChat } from "@/lib/api";
import type { Message } from "@/types";
import Sidebar from "@/components/Sidebar";
import ChatWindow from "@/components/ChatWindow";
import ChatInput from "@/components/ChatInput";

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const handleSend = useCallback(async (question: string) => {
    if (isStreaming) return;

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
    history.push({ role: "user", content: question });

    try {
      for await (const event of streamChat(question, history.slice(0, -1))) {
        if (event.type === "token") {
          // Append each token to the assistant placeholder.
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + event.content }
                : m
            )
          );
        } else if (event.type === "sources") {
          // Attach source citations once the stream is done.
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, sources: event.sources }
                : m
            )
          );
        } else if (event.type === "done") {
          // Mark streaming as complete.
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, isStreaming: false } : m
            )
          );
        }
      }
    } catch (err) {
      // Show the error inside the assistant bubble.
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
  }, [isStreaming, messages]);

  return (
    <div className="flex h-full bg-slate-950">
      <Sidebar />

      {/* Chat panel */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <ChatWindow messages={messages} />
        <ChatInput onSend={handleSend} disabled={isStreaming} />
      </div>
    </div>
  );
}
