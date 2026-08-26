import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import ArtifactPanel from "./components/ArtifactPanel";
import ChatPanel from "./components/ChatPanel";
import ErrorBanner from "./components/ErrorBanner";
import SessionSidebar from "./components/SessionSidebar";
import type { Artifact, Config, SessionDetail, SessionSummary } from "./types";

// Same phrasing heuristic as the backend's Ollama-path deterministic
// pre-check (architecture.md §5) — used here only to decide whether to
// preemptively open the artifact panel with a skeleton before the response
// arrives (design.md §3's "Essay generation in progress" state). A false
// negative here just means the panel opens a beat later once the real
// artifact_id comes back; it never blocks the request itself.
const ESSAY_REQUEST_PATTERN =
  /\b(essay|blog post|write.{0,15}up|turn.{0,20}into|make.{0,20}into|publish|write.{0,10}(post|piece|article))\b/i;

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<SessionDetail | null>(null);
  const [isSwitchingSession, setIsSwitchingSession] = useState(false);
  const [isAwaitingReply, setIsAwaitingReply] = useState(false);
  const [isAwaitingEssay, setIsAwaitingEssay] = useState(false);
  const [activeArtifact, setActiveArtifact] = useState<Artifact | null>(null);
  const [isArtifactPanelOpen, setIsArtifactPanelOpen] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await api.listSessions());
    } catch {
      // Sidebar list failing isn't fatal to the current conversation — the
      // chat panel's own error handling covers the cases that matter more.
    }
  }, []);

  useEffect(() => {
    api
      .getConfig()
      .then(setConfig)
      .catch(() =>
        setGlobalError(
          "Couldn't reach the backend to check the active model provider. Is the API running?",
        ),
      );
    refreshSessions();
  }, [refreshSessions]);

  // Found via real browser testing, not assumed: the composer's old
  // `disabled={!session}` check is already false while the *previous*
  // session is still active, so during the network round-trip to create
  // and fetch a new session, nothing stopped a message from being sent —
  // and it would attach to the stale session, not the new one. A real
  // race, not just a test-timing artifact (the same window exists for any
  // fast typist). isSwitchingSession closes it by disabling the composer
  // for the whole transition, with its own visible loading state.
  async function handleNewSession() {
    setGlobalError(null);
    setIsSwitchingSession(true);
    try {
      const session = await api.createSession(config?.llm_provider ?? "ollama");
      const detail = await api.getSession(session.id);
      setActiveSession(detail);
      setIsArtifactPanelOpen(false);
      setActiveArtifact(null);
      refreshSessions();
    } catch (err) {
      setGlobalError(describeError(err));
    } finally {
      setIsSwitchingSession(false);
    }
  }

  async function handleSelectSession(sessionId: string) {
    setGlobalError(null);
    setIsSwitchingSession(true);
    try {
      setActiveSession(await api.getSession(sessionId));
      setIsArtifactPanelOpen(false);
      setActiveArtifact(null);
    } catch (err) {
      setGlobalError(describeError(err));
    } finally {
      setIsSwitchingSession(false);
    }
  }

  async function handleSend(content: string) {
    if (!activeSession || isSwitchingSession) return;
    setGlobalError(null);

    // Optimistic user-turn append — design.md §3: "User message appears
    // immediately" before the (possibly slow) response arrives.
    const optimisticUser = {
      id: `pending-${Date.now()}`,
      role: "user" as const,
      content,
      citations: null,
      artifact_id: null,
      created_at: new Date().toISOString(),
    };
    setActiveSession({ ...activeSession, messages: [...activeSession.messages, optimisticUser] });

    const looksLikeEssay = ESSAY_REQUEST_PATTERN.test(content);
    setIsAwaitingReply(true);
    if (looksLikeEssay) {
      setIsAwaitingEssay(true);
      setIsArtifactPanelOpen(true);
    }

    try {
      const assistantMessage = await api.sendMessage(activeSession.id, content);
      setActiveSession((prev) =>
        prev
          ? {
              ...prev,
              messages: [
                ...prev.messages.filter((m) => m.id !== optimisticUser.id),
                optimisticUser,
                assistantMessage,
              ],
            }
          : prev,
      );
      if (assistantMessage.artifact_id) {
        const artifact = await api.getArtifact(assistantMessage.artifact_id);
        setActiveArtifact(artifact);
        setIsArtifactPanelOpen(true);
      }
      refreshSessions();
    } catch (err) {
      setGlobalError(describeError(err));
    } finally {
      setIsAwaitingReply(false);
      setIsAwaitingEssay(false);
    }
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50 text-slate-900">
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSession?.id ?? null}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        {globalError && (
          <ErrorBanner message={globalError} onDismiss={() => setGlobalError(null)} />
        )}
        <div className="flex min-h-0 flex-1">
          <ChatPanel
            session={activeSession}
            provider={config?.llm_provider ?? null}
            isSwitchingSession={isSwitchingSession}
            isAwaitingReply={isAwaitingReply}
            isAwaitingEssay={isAwaitingEssay}
            onSend={handleSend}
            onOpenArtifact={async (artifactId) => {
              try {
                setActiveArtifact(await api.getArtifact(artifactId));
                setIsArtifactPanelOpen(true);
              } catch (err) {
                setGlobalError(describeError(err));
              }
            }}
          />
          {isArtifactPanelOpen && (
            <ArtifactPanel
              artifact={activeArtifact}
              isLoading={isAwaitingEssay && !activeArtifact}
              onClose={() => setIsArtifactPanelOpen(false)}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status >= 500) {
      return `Something went wrong on the server (${err.errorCode}): ${err.message}`;
    }
    return err.message;
  }
  return "Couldn't reach the backend. Check that the API is running and reachable.";
}
