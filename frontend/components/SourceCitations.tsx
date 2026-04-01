import type { Source } from "@/types";

interface SourceCitationsProps {
  sources: Source[];
}

export default function SourceCitations({ sources }: SourceCitationsProps) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {sources.map((src, i) => (
        <span
          key={i}
          title={`${src.filename}, page ${src.page}`}
          className="inline-flex items-center gap-1.5 rounded-full bg-slate-700 px-2.5 py-1 text-xs text-slate-300"
        >
          {/* Document icon */}
          <svg
            className="h-3 w-3 shrink-0 text-slate-400"
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
          <span className="max-w-[180px] truncate">{src.filename}</span>
          <span className="shrink-0 text-slate-500">p.{src.page}</span>
        </span>
      ))}
    </div>
  );
}
