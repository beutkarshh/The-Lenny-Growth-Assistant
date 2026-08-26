import {
  ApiError,
  type ApiErrorBody,
  type Artifact,
  type Config,
  type Message,
  type Session,
  type SessionDetail,
  type SessionSummary,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body: ApiErrorBody = await response
      .json()
      .catch(() => ({ error_code: "UNKNOWN", message: response.statusText }));
    throw new ApiError(response.status, body.error_code, body.message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  getConfig: () => request<Config>("/config"),

  listSessions: () => request<SessionSummary[]>("/sessions"),

  createSession: (llm_provider: "claude" | "ollama") =>
    request<Session>("/sessions", {
      method: "POST",
      body: JSON.stringify({ llm_provider }),
    }),

  getSession: (sessionId: string) => request<SessionDetail>(`/sessions/${sessionId}`),

  sendMessage: (sessionId: string, content: string) =>
    request<Message>(`/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  getArtifact: (artifactId: string) => request<Artifact>(`/artifacts/${artifactId}`),
};

export { ApiError };
