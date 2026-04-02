/**
 * api.ts
 *
 * Thin wrappers around the FastAPI backend.
 * All requests go through Next.js rewrites (/api/* -> FastAPI) so no
 * hardcoded origin is needed in the browser bundle.
 */

import type { Source, Document, ChatSession, PersistedMessage } from "@/types";

// ---------------------------------------------------------------------------
// Chat — streaming SSE
// ---------------------------------------------------------------------------

export interface ChatHistoryMessage {
  role: "user" | "assistant";
  content: string;
}

export type SSEEvent =
  | { type: "token"; content: string }
  | { type: "sources"; sources: Source[] }
  | { type: "done" };

/**
 * Send a question to the backend and yield SSE events as they arrive.
 *
 * Usage:
 *   for await (const event of streamChat(question, history)) {
 *     if (event.type === "token") { ... }
 *   }
 */
export async function* streamChat(
  question: string,
  history: ChatHistoryMessage[],
  sessionId?: string,
  userId?: string,
): AsyncGenerator<SSEEvent> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  // Include the widget API key when configured so the backend allows the request.
  const widgetKey = process.env.NEXT_PUBLIC_WIDGET_API_KEY;
  if (widgetKey) {
    headers["X-Widget-Key"] = widgetKey;
  }

  const res = await fetch("/api/chat", {
    method: "POST",
    headers,
    body: JSON.stringify({
      question,
      history,
      session_id: sessionId ?? null,
      user_id: userId ?? "anonymous",
    }),
  });

  if (!res.ok) {
    throw new Error(`Chat request failed: HTTP ${res.status}`);
  }
  if (!res.body) {
    throw new Error("Response body is empty");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE events are separated by double newlines.
    const parts = buffer.split("\n\n");
    // The last part may be incomplete — keep it in the buffer.
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice(6)) as SSEEvent;
        yield event;
      } catch {
        // Ignore malformed SSE lines.
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export async function listDocuments(): Promise<Document[]> {
  const res = await fetch("/api/documents");
  if (!res.ok) throw new Error("Failed to fetch document list");
  const data = await res.json();
  return data.documents as Document[];
}

export async function deleteDocument(
  filename: string
): Promise<{ message: string; chunks_removed: number }> {
  const res = await fetch(`/api/documents/${encodeURIComponent(filename)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Delete failed" }));
    throw new Error(err.detail ?? "Delete failed");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Chat sessions (history)
// ---------------------------------------------------------------------------

export async function createSession(
  userId: string,
  title?: string,
): Promise<ChatSession> {
  const res = await fetch("/api/chat/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, title: title ?? "New chat" }),
  });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

export async function getSessions(userId: string): Promise<ChatSession[]> {
  const res = await fetch(
    `/api/chat/sessions?user_id=${encodeURIComponent(userId)}`,
  );
  if (!res.ok) throw new Error("Failed to fetch sessions");
  const data = await res.json();
  return data.sessions as ChatSession[];
}

export async function getSessionMessages(
  sessionId: string,
): Promise<{ session: ChatSession; messages: PersistedMessage[] }> {
  const res = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error("Failed to fetch session messages");
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(
    `/api/chat/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error("Failed to delete session");
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

export async function uploadPDF(file: File): Promise<{ message: string }> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch("/api/upload", {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail ?? "Upload failed");
  }

  return res.json();
}
