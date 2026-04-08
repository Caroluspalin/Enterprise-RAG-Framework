"use client";

import { DragEvent, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { uploadPDF } from "@/lib/api";

interface UploadPanelProps {
  onUploadComplete: () => void;
}

export default function UploadPanel({ onUploadComplete }: UploadPanelProps) {
  const { data: session } = useSession();
  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setStatus("error");
      setMessage("Only PDF files are accepted.");
      return;
    }

    setStatus("uploading");
    setMessage(`Uploading ${file.name}…`);

    try {
      const userId = session?.user?.id ?? undefined;
      const res = await uploadPDF(file, userId);
      setStatus("success");
      setMessage(res.message);
      onUploadComplete();
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Upload failed.");
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function handleInputChange() {
    const file = inputRef.current?.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="p-3">
      {/* Drop zone */}
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`cursor-pointer rounded-xl border-2 border-dashed px-4 py-5 text-center transition ${
          isDragging
            ? "border-blue-500 bg-blue-500/10"
            : "border-slate-700 hover:border-slate-500"
        }`}
      >
        <svg
          className="mx-auto mb-2 h-6 w-6 text-slate-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
          />
        </svg>
        <p className="text-xs text-slate-400">
          {status === "uploading" ? "Processing…" : "Drop PDF or click to upload"}
        </p>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={handleInputChange}
      />

      {/* Status feedback */}
      {status !== "idle" && message && (
        <p
          className={`mt-2 text-xs ${
            status === "success"
              ? "text-green-400"
              : status === "error"
              ? "text-red-400"
              : "text-slate-400"
          }`}
        >
          {message}
        </p>
      )}
    </div>
  );
}
