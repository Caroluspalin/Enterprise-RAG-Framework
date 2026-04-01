"use client";

import { useCallback, useEffect, useState } from "react";
import { listDocuments } from "@/lib/api";
import type { Document } from "@/types";
import UploadPanel from "@/components/UploadPanel";

export default function Sidebar() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchDocs = useCallback(async () => {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch {
      // Silently fail — backend may not be running yet during development.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-900">
      {/* Header */}
      <div className="border-b border-slate-800 px-4 py-4">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600">
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
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-100">DocChat</p>
            <p className="text-xs text-slate-500">B2B RAG Assistant</p>
          </div>
        </div>
      </div>

      {/* Upload */}
      <div className="border-b border-slate-800">
        <p className="px-4 pt-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
          Upload
        </p>
        <UploadPanel onUploadComplete={fetchDocs} />
      </div>

      {/* Document list */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <p className="px-4 pt-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
          Documents
        </p>

        {loading ? (
          <p className="px-4 py-3 text-xs text-slate-500">Loading…</p>
        ) : documents.length === 0 ? (
          <p className="px-4 py-3 text-xs text-slate-500">
            No documents ingested yet.
          </p>
        ) : (
          <ul className="flex-1 overflow-y-auto px-3 py-2">
            {documents.map((doc) => (
              <li
                key={doc.name}
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                title={`${doc.name} (${doc.size_kb} KB)`}
              >
                <svg
                  className="h-3.5 w-3.5 shrink-0 text-slate-500"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                  />
                </svg>
                <span className="truncate">{doc.name}</span>
                <span className="ml-auto shrink-0 text-slate-600">
                  {doc.size_kb}k
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
