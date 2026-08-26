export type LlmProvider = "claude" | "ollama";

export interface Citation {
  episode_title: string;
  episode_source_url: string;
  start_timestamp: string;
  chunk_id: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  artifact_id: string | null;
  created_at: string;
}

export interface Session {
  id: string;
  created_at: string;
  llm_provider: LlmProvider;
  metadata: Record<string, unknown>;
}

export interface SessionSummary extends Session {
  first_message_preview: string | null;
}

export interface SessionDetail extends Session {
  messages: Message[];
}

export interface Artifact {
  id: string;
  session_id: string;
  type: "markdown" | "html";
  content: string;
  created_at: string;
}

export interface Config {
  llm_provider: LlmProvider;
  available_providers: LlmProvider[];
}

export interface ApiErrorBody {
  error_code: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public errorCode: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
