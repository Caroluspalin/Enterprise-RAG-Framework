import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type { Message } from "@/types";
import SourceCitations from "@/components/SourceCitations";

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[90%] md:max-w-[75%] ${isUser ? "order-2" : "order-1"}`}>
        {/* Avatar label */}
        <p className={`mb-1 text-xs text-slate-500 ${isUser ? "text-right" : "text-left"}`}>
          {isUser ? "You" : "Assistant"}
        </p>

        {/* Bubble */}
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "rounded-tr-sm bg-blue-600 text-white"
              : "rounded-tl-sm bg-slate-800 text-slate-100"
          }`}
        >
          {isUser ? (
            // User messages are plain text — preserve line breaks.
            message.content.split("\n").map((line, i) => (
              <span key={i}>
                {line}
                {i < message.content.split("\n").length - 1 && <br />}
              </span>
            ))
          ) : (
            // Assistant messages rendered as markdown (code blocks, bold, lists, tables).
            <div className="prose-invert prose-sm prose max-w-none prose-p:my-1 prose-pre:my-2 prose-pre:bg-slate-900 prose-pre:text-slate-200 prose-code:before:content-none prose-code:after:content-none prose-headings:text-slate-100 prose-a:text-blue-400 prose-strong:text-slate-100 prose-li:my-0.5">
              <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}

          {/* Blinking cursor while streaming */}
          {message.isStreaming && (
            <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-slate-400" />
          )}
        </div>

        {/* Source citations shown below assistant bubbles */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <SourceCitations sources={message.sources} />
        )}
      </div>
    </div>
  );
}
