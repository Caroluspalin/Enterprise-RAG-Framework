import type { Message } from "@/types";
import SourceCitations from "@/components/SourceCitations";

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[75%] ${isUser ? "order-2" : "order-1"}`}>
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
          {/* Preserve line breaks from the LLM response */}
          {message.content.split("\n").map((line, i) => (
            <span key={i}>
              {line}
              {i < message.content.split("\n").length - 1 && <br />}
            </span>
          ))}

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
