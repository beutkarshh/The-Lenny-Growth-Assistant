import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../types";
import CitationChips from "./CitationChips";

interface Props {
  message: Message;
  onOpenArtifact: (artifactId: string) => void;
}

// A grounded_qa answer always carries citations when it found material; an
// empty/null citations array on an assistant turn with no artifact is the
// "not covered" fallback (architecture.md §4 step 3). Distinguished by
// icon + border style, not color alone — design.md §5.
export default function MessageBubble({ message, onOpenArtifact }: Props) {
  const isUser = message.role === "user";
  const hasArtifact = Boolean(message.artifact_id);
  const hasCitations = Boolean(message.citations && message.citations.length > 0);
  const isFallback = !isUser && !hasArtifact && !hasCitations;

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-2xl whitespace-pre-wrap rounded-2xl rounded-br-sm bg-brand-600 px-4 py-3 text-sm text-white">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div
        className={`max-w-2xl rounded-2xl rounded-bl-sm px-4 py-3 text-sm ${
          isFallback
            ? "border border-dashed border-slate-300 bg-slate-100 text-slate-600"
            : "bg-white text-slate-800 shadow-sm ring-1 ring-slate-200"
        }`}
      >
        {isFallback && (
          <div className="mb-1 flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-slate-500">
            <span aria-hidden="true">ⓘ</span> Not covered in transcripts
          </div>
        )}
        <div className="prose prose-sm max-w-none prose-p:my-1.5">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
        {hasCitations && <CitationChips citations={message.citations!} />}
        {hasArtifact && (
          <button
            type="button"
            onClick={() => onOpenArtifact(message.artifact_id!)}
            className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            📄 View essay
          </button>
        )}
      </div>
    </div>
  );
}
