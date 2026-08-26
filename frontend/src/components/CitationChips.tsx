import type { Citation } from "../types";

function timestampToSeconds(hhmmss: string): number {
  const [h, m, s] = hhmmss.split(":").map(Number);
  return h * 3600 + m * 60 + s;
}

// design.md §2/§3: citation chips are a first-class visual element, clickable
// to reach the source. architecture.md §4 designed citations specifically to
// deep-link to the exact moment in the source video — that's what "expand
// source" means here, rather than a separate chunk-text lookup endpoint.
export default function CitationChips({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Sources">
      {citations.map((citation) => (
        <a
          key={citation.chunk_id}
          href={`${citation.episode_source_url}&t=${timestampToSeconds(citation.start_timestamp)}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
          title={`Jump to ${citation.start_timestamp} in the source episode`}
        >
          🔗 {citation.episode_title} · {citation.start_timestamp}
        </a>
      ))}
    </div>
  );
}
