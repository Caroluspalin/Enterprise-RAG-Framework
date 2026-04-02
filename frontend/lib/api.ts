/**
 * api.ts
 *
 * Thin wrappers around the FastAPI backend.
 * All requests go through Next.js rewrites (/api/* -> FastAPI) so no
 * hardcoded origin is needed in the browser bundle.
 */

import type { Source, Document } from "@/types";

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
  history: ChatHistoryMessage[]
): AsyncGenerator<SSEEvent> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
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
