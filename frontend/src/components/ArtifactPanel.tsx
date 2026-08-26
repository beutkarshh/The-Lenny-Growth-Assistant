import DOMPurify from "dompurify";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Artifact } from "../types";

interface Props {
  artifact: Artifact | null;
  isLoading: boolean;
  onClose: () => void;
}

// architecture.md §7: HTML artifacts are untrusted. Sanitize (strip <script>,
// inline event handlers, external resource loads) AND render inside a
// sandboxed iframe with no allow-same-origin / no allow-scripts — two
// independent layers, neither relied on alone. Markdown artifacts don't need
// the same treatment: react-markdown renders its AST directly to React
// elements and never executes embedded raw HTML unless the rehype-raw plugin
// is added (deliberately not used here), so it's inherently safe as a
// Markdown-to-safe-output pipeline without a separate sanitization pass.
const SANITIZE_CONFIG: DOMPurify.Config = {
  FORBID_TAGS: ["script", "iframe", "object", "embed", "link", "meta", "base"],
  FORBID_ATTR: ["srcset"],
  FORBID_ATTR_PREFIXES: ["on"],
  ALLOW_DATA_ATTR: false,
};

function sanitizeHtml(rawHtml: string): string {
  return DOMPurify.sanitize(rawHtml, SANITIZE_CONFIG);
}

export default function ArtifactPanel({ artifact, isLoading, onClose }: Props) {
  const [copied, setCopied] = useState(false);

  const sanitizedHtml = useMemo(
    () => (artifact?.type === "html" ? sanitizeHtml(artifact.content) : null),
    [artifact],
  );
  const wordCount = artifact ? artifact.content.trim().split(/\s+/).length : 0;

  async function handleCopy() {
    if (!artifact) return;
    await navigator.clipboard.writeText(artifact.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function handleDownload() {
    if (!artifact) return;
    const extension = artifact.type === "html" ? "html" : "md";
    const blob = new Blob([artifact.content], {
      type: artifact.type === "html" ? "text/html" : "text/markdown",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `artifact.${extension}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <aside
      aria-label="Artifact viewer"
      className="flex w-[480px] shrink-0 flex-col border-l border-slate-200 bg-white"
    >
      <header className="flex items-center justify-between border-b border-slate-200 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-800">Artifact</span>
          {artifact && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium uppercase text-slate-500">
              {artifact.type}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close artifact panel"
          className="text-slate-400 hover:text-slate-700"
        >
          ✕
        </button>
      </header>

      {isLoading && (
        <div className="flex-1 animate-pulse space-y-3 p-4" aria-live="polite">
          <p className="text-sm text-slate-400">Writing your essay…</p>
          <div className="h-4 w-3/4 rounded bg-slate-200" />
          <div className="h-4 w-full rounded bg-slate-200" />
          <div className="h-4 w-full rounded bg-slate-200" />
          <div className="h-4 w-5/6 rounded bg-slate-200" />
          <div className="h-4 w-full rounded bg-slate-200" />
          <div className="h-4 w-2/3 rounded bg-slate-200" />
        </div>
      )}

      {!isLoading && !artifact && (
        <div className="flex-1 p-4 text-sm text-slate-400">No artifact selected.</div>
      )}

      {!isLoading && artifact && (
        <>
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2 text-xs text-slate-500">
            <span>{wordCount} words</span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleCopy}
                className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-600 hover:bg-slate-50"
              >
                {copied ? "Copied!" : "Copy"}
              </button>
              <button
                type="button"
                onClick={handleDownload}
                className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-600 hover:bg-slate-50"
              >
                Download
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {artifact.type === "html" ? (
              <iframe
                title="Generated artifact preview (sandboxed)"
                sandbox=""
                srcDoc={sanitizedHtml ?? ""}
                className="h-full w-full border-0"
              />
            ) : (
              <div className="prose prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{artifact.content}</ReactMarkdown>
              </div>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
