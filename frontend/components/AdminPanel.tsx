"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { deleteDocument, listDocuments, fetchAnalytics } from "@/lib/api";
import type { Document, AnalyticsData } from "@/types";
import UploadPanel from "@/components/UploadPanel";
import UsersTab from "@/components/UsersTab";
import ApiKeysTab from "@/components/ApiKeysTab";
import ToastContainer from "@/components/Toast";

// ---------------------------------------------------------------------------
// Tab type
// ---------------------------------------------------------------------------

type Tab = "documents" | "analytics" | "users" | "api-keys";

// ---------------------------------------------------------------------------
// Stat card — reusable small component for key metrics
// ---------------------------------------------------------------------------

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
        {label}
      </p>
      <p className="mt-2 text-2xl font-bold text-white">{value}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Simple bar chart — pure CSS, no external library needed
// ---------------------------------------------------------------------------

function MiniBarChart({ data }: { data: { date: string; count: number }[] }) {
  if (data.length === 0) {
    return <p className="text-sm text-slate-500">No data yet.</p>;
  }

  const max = Math.max(...data.map((d) => d.count), 1);

  return (
    <div className="flex items-end gap-1.5" style={{ height: 120 }}>
      {data.map((d) => {
        const pct = (d.count / max) * 100;
        return (
          <div
            key={d.date}
            className="group relative flex-1"
            style={{ height: "100%" }}
          >
            {/* Tooltip */}
            <div className="pointer-events-none absolute -top-8 left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded bg-slate-700 px-2 py-1 text-xs text-white group-hover:block">
              {d.date}: {d.count}
            </div>
            {/* Bar */}
            <div
              className="absolute bottom-0 w-full rounded-t bg-indigo-500 transition-all group-hover:bg-indigo-400"
              style={{ height: `${pct}%`, minHeight: d.count > 0 ? 4 : 0 }}
            />
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AdminPanel() {
  const { data: session } = useSession();
  const userId = (session?.user as { id?: string })?.id;

  const [tab, setTab] = useState<Tab>("documents");

  // -- Documents state --
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // -- Analytics state --
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);

  // -----------------------------------------------------------------------
  // Documents
  // -----------------------------------------------------------------------

  const fetchDocs = useCallback(async () => {
    try {
      setError(null);
      const docs = await listDocuments(userId);
      setDocuments(docs);
    } catch {
      setError("Failed to load documents. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  async function handleDelete(filename: string) {
    setDeleting(filename);
    try {
      await deleteDocument(filename, userId);
      await fetchDocs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
      setDeleting(null);
    }
  }

  // -----------------------------------------------------------------------
  // Analytics — fetch when the tab is selected
  // -----------------------------------------------------------------------

  const loadAnalytics = useCallback(async () => {
    setAnalyticsLoading(true);
    setAnalyticsError(null);
    try {
      const data = await fetchAnalytics(30, userId);
      setAnalytics(data);
    } catch {
      setAnalyticsError("Failed to load analytics. Is the backend running?");
    } finally {
      setAnalyticsLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    if (tab === "analytics") loadAnalytics();
  }, [tab, loadAnalytics]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Tab bar */}
      <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-900 p-1">
        {(["documents", "analytics", "users", "api-keys"] as Tab[]).map((t) => {
          const labels: Record<Tab, string> = {
            documents: "Documents",
            analytics: "Analytics",
            users: "Users",
            "api-keys": "API Keys",
          };
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                tab === t
                  ? "bg-slate-800 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {labels[t]}
            </button>
          );
        })}
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Documents tab                                                      */}
      {/* ----------------------------------------------------------------- */}
      {tab === "documents" && (
        <div className="space-y-10">
          {/* Upload section */}
          <section>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Upload PDF
            </h2>
            <div className="rounded-xl border border-slate-800 bg-slate-900">
              <UploadPanel onUploadComplete={fetchDocs} />
            </div>
          </section>

          {/* Document list */}
          <section>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Documents in vector store
            </h2>

            {error && (
              <p className="mb-4 rounded-lg bg-red-900/30 px-4 py-2 text-sm text-red-400">
                {error}
              </p>
            )}

            {loading ? (
              <p className="text-sm text-slate-500">Loading...</p>
            ) : documents.length === 0 ? (
              <p className="text-sm text-slate-500">
                No documents ingested yet. Upload a PDF above to get started.
              </p>
            ) : (
              <div className="overflow-hidden rounded-xl border border-slate-800">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 bg-slate-900">
                      <th className="px-4 py-3 text-left font-medium text-slate-400">
                        Filename
                      </th>
                      <th className="px-4 py-3 text-right font-medium text-slate-400">
                        Size
                      </th>
                      <th className="px-4 py-3 text-right font-medium text-slate-400">
                        Action
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800 bg-slate-900/50">
                    {documents.map((doc) => (
                      <tr key={doc.name} className="hover:bg-slate-800/40">
                        <td className="px-4 py-3 text-slate-200">{doc.name}</td>
                        <td className="px-4 py-3 text-right text-slate-500">
                          {doc.size_kb != null ? `${doc.size_kb} KB` : "\u2014"}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => handleDelete(doc.name)}
                            disabled={deleting === doc.name}
                            className="rounded-lg px-3 py-1 text-xs font-medium text-red-400 transition-colors hover:bg-red-900/30 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {deleting === doc.name ? "Deleting..." : "Delete"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Analytics tab                                                      */}
      {/* ----------------------------------------------------------------- */}
      {tab === "analytics" && (
        <div className="space-y-8">
          {analyticsError && (
            <p className="rounded-lg bg-red-900/30 px-4 py-2 text-sm text-red-400">
              {analyticsError}
            </p>
          )}

          {analyticsLoading && !analytics ? (
            <p className="text-sm text-slate-500">Loading analytics...</p>
          ) : analytics ? (
            <>
              {/* Stat cards */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <StatCard label="Total Messages" value={analytics.total_messages} />
                <StatCard label="Total Sessions" value={analytics.total_sessions} />
                <StatCard label="Active Sessions (30d)" value={analytics.active_sessions} />
              </div>

              {/* Messages per day chart */}
              <section>
                <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Messages per day (last 30 days)
                </h2>
                <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <MiniBarChart data={analytics.messages_per_day} />
                  {/* X-axis labels */}
                  {analytics.messages_per_day.length > 0 && (
                    <div className="mt-2 flex justify-between text-[10px] text-slate-500">
                      <span>{analytics.messages_per_day[0].date}</span>
                      <span>
                        {analytics.messages_per_day[analytics.messages_per_day.length - 1].date}
                      </span>
                    </div>
                  )}
                </div>
              </section>

              {/* Popular questions */}
              <section>
                <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Most asked questions
                </h2>
                {analytics.popular_questions.length === 0 ? (
                  <p className="text-sm text-slate-500">No questions yet.</p>
                ) : (
                  <div className="space-y-2">
                    {analytics.popular_questions.map((q, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 px-4 py-3"
                      >
                        <p className="truncate text-sm text-slate-200">{q.question}</p>
                        <span className="ml-4 shrink-0 rounded-full bg-indigo-900/50 px-2.5 py-0.5 text-xs font-medium text-indigo-300">
                          {q.count}x
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* Recent questions */}
              <section>
                <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Recent questions
                </h2>
                {analytics.recent_questions.length === 0 ? (
                  <p className="text-sm text-slate-500">No questions yet.</p>
                ) : (
                  <div className="space-y-2">
                    {analytics.recent_questions.map((q, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 px-4 py-3"
                      >
                        <p className="truncate text-sm text-slate-200">{q.question}</p>
                        <span className="ml-4 shrink-0 text-xs text-slate-500">
                          {new Date(q.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </>
          ) : null}
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Users tab                                                          */}
      {/* ----------------------------------------------------------------- */}
      {tab === "users" && <UsersTab />}

      {/* ----------------------------------------------------------------- */}
      {/* API Keys tab                                                       */}
      {/* ----------------------------------------------------------------- */}
      {tab === "api-keys" && <ApiKeysTab />}

      {/* Toast notifications */}
      <ToastContainer />
    </div>
  );
}
