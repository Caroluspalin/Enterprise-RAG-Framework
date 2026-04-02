"use client";

import { useCallback, useEffect, useState } from "react";
import { deleteDocument, listDocuments } from "@/lib/api";
import type { Document } from "@/types";
import UploadPanel from "@/components/UploadPanel";

export default function AdminPanel() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchDocs = useCallback(async () => {
    try {
      setError(null);
      const docs = await listDocuments();
      setDocuments(docs);
    } catch {
      setError("Failed to load documents. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  async function handleDelete(filename: string) {
    setDeleting(filename);
    try {
      await deleteDocument(filename);
      // Refresh the list so the deleted row disappears immediately.
      await fetchDocs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
      setDeleting(null);
    }
  }

  return (
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
          <p className="text-sm text-slate-500">Loading…</p>
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
                      {doc.size_kb != null ? `${doc.size_kb} KB` : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleDelete(doc.name)}
                        disabled={deleting === doc.name}
                        className="rounded-lg px-3 py-1 text-xs font-medium text-red-400 transition-colors hover:bg-red-900/30 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {deleting === doc.name ? "Deleting…" : "Delete"}
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
  );
}
