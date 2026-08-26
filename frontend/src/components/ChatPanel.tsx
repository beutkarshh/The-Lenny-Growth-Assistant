import { useEffect, useRef } from "react";
import type { LlmProvider, SessionDetail } from "../types";
import Composer from "./Composer";
import MessageBubble from "./MessageBubble";

interface Props {
  session: SessionDetail | null;
  provider: LlmProvider | null;
  isSwitchingSession: boolean;
  isAwaitingReply: boolean;
  isAwaitingEssay: boolean;
  onSend: (content: string) => void;
  onOpenArtifact: (artifactId: string) => void;
}

export default function ChatPanel({
  session,
  provider,
  isSwitchingSession,
  isAwaitingReply,
  isAwaitingEssay,
  onSend,
  onOpenArtifact,
}: Props) {
  const threadEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages.length]);

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2.5">
        <h1 className="text-sm font-semibold text-slate-800">The Lenny Growth Assistant</h1>
        {provider && (
          <span
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600"
            title="Active model provider"
          >
            <span
              aria-hidden="true"
              className={`h-1.5 w-1.5 rounded-full ${provider === "claude" ? "bg-purple-500" : "bg-green-500"}`}
            />
            {provider === "claude" ? "Claude (cloud)" : "Ollama (local)"}
          </span>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
        {isSwitchingSession && (
          <div className="flex h-full items-center justify-center text-center text-sm text-slate-400">
            <span className="animate-pulse">Loading session…</span>
          </div>
        )}
        {!isSwitchingSession && !session && (
          <div className="flex h-full items-center justify-center text-center text-sm text-slate-400">
            Select a session, or start a new one, to ask about growth or product
            <br />
            strategy from Lenny's Podcast.
          </div>
        )}
        {!isSwitchingSession && session && session.messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-center text-sm text-slate-400">
            Ask about growth or product strategy from Lenny's Podcast.
          </div>
        )}
        {!isSwitchingSession && session && (
          <div className="mx-auto flex max-w-3xl flex-col gap-3">
            {session.messages.map((message) => (
              <MessageBubble key={message.id} message={message} onOpenArtifact={onOpenArtifact} />
            ))}
            {isAwaitingReply && (
              <div className="flex justify-start">
                <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-sm bg-white px-4 py-2.5 text-sm text-slate-400 shadow-sm ring-1 ring-slate-200">
                  <span className="animate-pulse">
                    {isAwaitingEssay ? "Writing your essay…" : "Thinking…"}
                  </span>
                </div>
              </div>
            )}
            <div ref={threadEndRef} />
          </div>
        )}
      </div>

      <div className="mx-auto w-full max-w-3xl">
        <Composer disabled={!session || isSwitchingSession || isAwaitingReply} onSend={onSend} />
      </div>
    </div>
  );
}
