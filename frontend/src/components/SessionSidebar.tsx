import type { SessionSummary } from "../types";

interface Props {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  onNewSession: () => void;
  onSelectSession: (sessionId: string) => void;
}

export default function SessionSidebar({
  sessions,
  activeSessionId,
  onNewSession,
  onSelectSession,
}: Props) {
  return (
    <nav
      aria-label="Sessions"
      className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white"
    >
      <div className="border-b border-slate-200 p-3">
        <button
          type="button"
          onClick={onNewSession}
          className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          + New session
        </button>
      </div>
      <ul className="flex-1 overflow-y-auto">
        {sessions.length === 0 && (
          <li className="px-3 py-4 text-sm text-slate-400">No sessions yet.</li>
        )}
        {sessions.map((session) => (
          <li key={session.id}>
            <button
              type="button"
              onClick={() => onSelectSession(session.id)}
              aria-current={session.id === activeSessionId ? "true" : undefined}
              className={`block w-full border-b border-slate-100 px-3 py-3 text-left text-sm hover:bg-slate-50 ${
                session.id === activeSessionId ? "bg-blue-50" : ""
              }`}
            >
              <div className="truncate font-medium text-slate-700">
                {session.first_message_preview ?? "New session"}
              </div>
              <div className="mt-0.5 text-xs text-slate-400">
                {new Date(session.created_at).toLocaleString()} · {session.llm_provider}
              </div>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
