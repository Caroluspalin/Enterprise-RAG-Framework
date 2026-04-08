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

export interface ChatSession {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
}

/** Message shape returned by the backend session history endpoint. */
export interface PersistedMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[] | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export interface DayCount {
  date: string;
  count: number;
}

export interface RecentQuestion {
  question: string;
  created_at: string;
}

export interface PopularQuestion {
  question: string;
  count: number;
}

export interface AnalyticsData {
  total_messages: number;
  total_sessions: number;
  active_sessions: number;
  messages_per_day: DayCount[];
  recent_questions: RecentQuestion[];
  popular_questions: PopularQuestion[];
}

// ---------------------------------------------------------------------------
// Admin — Users & API Keys
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  username: string;
  name: string;
  role: "owner" | "admin" | "member" | "viewer";
  created_at: string;
}

export interface ApiKey {
  id: string;
  label: string;
  prefix: string;
  is_active: boolean;
  created_at: string;
}

/** Returned only once when a new key is created. */
export interface ApiKeyWithSecret extends ApiKey {
  raw_key: string;
}
