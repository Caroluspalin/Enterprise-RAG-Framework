export interface Source {
  filename: string;
  page: number | string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  /** True while tokens are still streaming in for this message. */
  isStreaming?: boolean;
}

export interface Document {
  name: string;
  // null when the PDF has been removed from disk but embeddings still exist
  size_kb: number | null;
}
