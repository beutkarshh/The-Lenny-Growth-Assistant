# Architecture: The Lenny Growth Assistant

This document covers the database schema, API surface, ingestion/retrieval flow, agent routing, model configuration, security approach, and deployment topology. It implements the decisions recorded in `PRD.md`.

---

## 1. System Overview

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│   Frontend   │◄────►│   FastAPI Backend │◄────►│  PostgreSQL + pgvector│
│ (Chat + Artifact│    │  (sessions, agent │      │ (sessions, messages, │
│    Viewer)   │      │   routing, retrieval)│    │  chunks + embeddings) │
└─────────────┘      └────────┬──────────┘      └─────────────────────┘
                               │
                     ┌─────────┴─────────┐
                     │   Agent Layer      │
                     │ (Claude Agent SDK) │
                     └──────┬──────┬──────┘
                             │      │
                    ┌────────┘      └────────┐
              ┌─────▼─────┐           ┌──────▼──────┐
              │ Cloud LLM  │           │ Local LLM    │
              │ (Anthropic)│           │ (Ollama)     │
              └───────────┘           └─────────────┘
```

**Why pgvector instead of a separate vector database:** it satisfies both the "PostgreSQL for persistence" and "indexed knowledge base" requirements with one moving part instead of two, which materially reduces what a fresh evaluator has to install and run — a direct trade-off in favor of the "operability" evaluation criterion.

---

## 2. Database Schema (PostgreSQL)

**sessions**
| column | type | notes |
|---|---|---|
| id | uuid, PK | session identifier |
| created_at | timestamptz | |
| llm_provider | text | 'claude' \| 'ollama', set at session creation, overridable per-message |
| metadata | jsonb | free-form (e.g. user label) |

**messages**
| column | type | notes |
|---|---|---|
| id | uuid, PK | |
| session_id | uuid, FK → sessions.id | |
| role | text | 'user' \| 'assistant' |
| content | text | |
| citations | jsonb | array of {episode_title, episode_source_url, start_timestamp, chunk_id} — null if none |
| artifact_id | uuid, FK → artifacts.id, nullable | added Phase 5: set on the assistant turn that triggered `ship30_essay`, so the frontend knows which message to open the artifact panel for |
| created_at | timestamptz | |

**transcript_chunks**
| column | type | notes |
|---|---|---|
| id | uuid, PK | |
| episode_title | text | |
| episode_source_url | text | YouTube URL for the episode |
| chunk_text | text | |
| chunk_index | int | position within episode, for traceability |
| start_timestamp | text | e.g. `"00:12:34"`, captured from the source transcript's per-line speaker timestamps at chunking time; combined with `episode_source_url` this lets a citation deep-link to the exact moment (`{url}&t={seconds}`) rather than just naming the episode |
| embedding | vector(768) | pgvector column; dimension matches the local Ollama `nomic-embed-text` model — see §6 |

**artifacts**
| column | type | notes |
|---|---|---|
| id | uuid, PK | |
| session_id | uuid, FK | |
| type | text | 'markdown' \| 'html' |
| content | text | |
| created_at | timestamptz | |

---

## 3. API Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + dependency check (DB, active LLM provider reachability) |
| POST | `/sessions` | Create a new session |
| GET | `/sessions` | List sessions (id, created_at, llm_provider, first_message_preview), newest first — added Phase 6 for design.md §2's session sidebar; missing from the original table |
| GET | `/sessions/{id}` | Fetch session + message history |
| POST | `/sessions/{id}/messages` | Send a user message, receive assistant response (triggers agent routing) |
| POST | `/sessions/{id}/artifacts` | Generate a Markdown/HTML artifact from current session context |
| GET | `/artifacts/{id}` | Fetch a specific artifact for rendering |
| GET | `/config` | Returns active LLM provider and available options (for UI display) |

All endpoints return structured error responses (`{error_code, message}`) with appropriate HTTP status codes rather than raw stack traces.

---

## 4. Ingestion & Retrieval Flow

1. **Ingestion (offline script, run once):** Load a curated subset (53 episodes) of Lenny's Podcast/Newsletter transcripts from the [ChatPRD/lennys-podcast-transcripts](https://github.com/ChatPRD/lennys-podcast-transcripts) archive (269 episodes total, each `episodes/{guest}/transcript.md` with YAML frontmatter metadata and per-line speaker timestamps). The subset was selected in three passes rather than arbitrarily or randomly, since the persona (a growth PM) and the PRD's own example questions are growth/PM-specific:
   - **Pass 1 — tag-based ranking:** episode lists were pulled from a growth+PM-weighted set of the repo's pre-built topic tags (`index/growth-strategy.md`, `product-led-growth.md`, `retention.md`, `startup-growth.md`, `network-effects.md`, `experimentation.md` for the growth pool; `product-management.md`, `product-strategy.md`, `product-market-fit.md` for the PM pool), ranked by how many topics within each pool an episode was tagged with, taking the top 22 growth + top 20 PM-strategy (42 total, reserving slots for both dimensions rather than letting the much larger PM-tagged pool crowd out growth-specific episodes).
   - **Pass 2 — full-text verification:** the repo's topic tags are AI-generated and incomplete, so all 269 transcripts' full text were searched for terms tied to this PRD's own example flows (`referral`, `incentive gaming`, `activation metric/rate`, `prioritization framework`). This surfaced clearly relevant guests the tags had missed entirely — e.g. Elena Verna (tagged only `ab-testing`, despite being a leading PLG/growth advisor) and Rahul Vohra (tagged only `enterprise-sales`, despite Superhuman's PMF framework being widely referenced in the space). 6 verified additions, confirmed against each episode's actual title/description before inclusion (not added on keyword match alone).
   - **Pass 3 — second full-text pass** on `pricing`, `prioritization framework` (exact phrase), and `PLG` (literal acronym) turned up mostly noise (generic mentions in unrelated episodes) except where the episode's own title confirmed genuine relevance (e.g. "How to grow a subscription business," "Lessons from Airtable's unconventional growth strategy"). 7 candidates passed title verification, but cross-checking against the Pass 1 list caught that one (`geoff-charles`) was already present — a duplicate this pass would have silently reintroduced if the check hadn't been run — leaving 6 genuinely new additions. Separately, one candidate (`elena-verna-20`) was caught as a literal duplicate of an already-included episode (same underlying `video_id` as `elena-verna-30`) and excluded before it was ever added.
   
   - **Pass 4 — data-integrity check during the actual ingestion run:** after chunking and embedding all 54 selected episodes, a post-ingestion check (`count(DISTINCT episode_title)` vs. total episodes) caught that two selected slugs, `claire-vo` and `jackie-bavaro`, resolved to the exact same underlying video (`video_id=aXGo1o_baBo`). Inspecting both files directly showed this is an **upstream data bug in the source repo**, not a selection error: the `jackie-bavaro` folder's `guest` field says "Jackie Bavaro," but its `title`, `youtube_url`, and full transcript body are all Claire Vo's episode. Left uncorrected, this would have let a citation attribute Claire Vo's words to Jackie Bavaro by name — a real grounding-accuracy defect, not just a harmless duplicate. The mislabeled slug was dropped rather than papered over.

   Final count: 42 (tag-ranked) + 6 (Pass 2) + 6 (Pass 3) − 1 (Pass 4, mislabeled duplicate) = 53. The frozen list is committed at `backend/app/ingestion/data/selected_episodes.json` so ingestion is deterministic and doesn't depend on the source repo's tags staying stable over time. Each episode's transcript is split into ~500-800 token chunks with slight overlap. Embeddings are generated per chunk. Chunk text, episode metadata (including `start_timestamp`, parsed from the source's `Speaker (HH:MM:SS):` lines), and the embedding are stored in `transcript_chunks`. Timestamps in the source vary between `MM:SS` (episodes under an hour) and `HH:MM:SS` — the parser normalizes both to `HH:MM:SS` for storage.
2. **Retrieval (runtime, per user message):** Embed the user's query. Run a similarity search (cosine distance via pgvector) against `transcript_chunks`, returning top-k (k≈5) matches above a minimum similarity threshold.
3. **Grounding check:** If no chunk clears the similarity threshold, the agent is instructed to respond with an explicit "not covered in the available transcripts" fallback rather than answering unaided.
4. **Citation attachment:** Each chunk used in the response carries its `episode_title`, `episode_source_url`, and `start_timestamp` forward into the response's `citations` field, so the frontend can display sources per claim and deep-link to the exact moment in the source video (`{episode_source_url}&t={seconds}`).

---

## 5. Agent Routing

**Correction from earlier drafts of this doc:** the literal "Claude Agent SDK" package (`claude-agent-sdk`) is Claude Code repackaged as a library — built for coding/filesystem agents, shipping Bash and file Read/Write/Edit as default tools. For a scoped Q&A/essay assistant with exactly two narrow custom tools and no filesystem or shell access, that's the wrong tool for the job and a real security overreach if not actively locked down. The agent layer instead uses the **Tool Runner** (`client.beta.messages.tool_runner` + `@beta_tool`), part of the standard `anthropic` Python SDK's beta surface — purpose-built for "a custom-tool agent without hand-writing the loop," with no built-in tools to disable in the first place. This is still 100% the official Anthropic SDK ecosystem the brief calls for; it's a different surface within it, chosen for fit and safety.

The Claude-side Tool Runner and the Ollama-side manual loop (§6) orchestrate two distinct tools/skills, kept separate rather than merged into one prompt:

- **`grounded_qa` tool:** takes a self-contained query (formulated by the agent from the user message + session history — the tool itself is stateless) and calls retrieval, returning either the matched transcript chunks (with source metadata) or an explicit "not covered" signal. **Composing the final cited answer is the outer agent LLM's job, not the tool's** — the tool returns raw grounded context; the agent's system prompt instructs it to synthesize a cited answer from that context (or state the "not covered" fallback) in its own response turn. This avoids a second, nested LLM call inside the tool for no benefit (double latency/cost with no quality gain), and is the standard shape for RAG-as-a-tool. Structured citation data (episode/URL/timestamp per chunk) is captured via a side-channel during the tool call — captured because tool results are plain text on both providers and can't carry structured objects back through the tool-calling mechanism itself — and attached to the persisted Message.citations field after the agent loop completes.

  **The tool's `query` argument is never trusted for retrieval — the search text is always built deterministically from session history instead.** Live testing found `llama3.2:3b` unreliably formulates good retrieval queries in both cases it was tested: first-turn questions (only ~1-in-3 to 1-in-4 calls wrote a full question rather than a terse fragment that measurably hurt embedding-based retrieval, even with an explicit instruction and low temperature) and follow-ups (trusting the LLM's own reformulation succeeded in only 3/5 repeated trials of the PRD's own flow-2 example). `resolve_search_text()` (`agent/tools.py`) replaces the LLM's query entirely: for a session's **first** user turn, retrieval embeds the user's raw message directly (naturally well-formed, nothing to reformulate); for a **follow-up** turn, it concatenates the previous user question with the current message (`f"{previous} {current}"`) rather than trusting the model to synthesize the two — less precise than a good reformulation would be, but a fixed string the model can't get wrong beats one it gets wrong a meaningful fraction of the time. The `query` argument the LLM still supplies keeps the tool-calling/routing mechanism functioning but no longer affects what gets embedded. Verified 5/5 for both the first-turn fix and the follow-up fix (up from ~1-in-3 and 3/5 respectively, both measured before fixing); full investigation, including the false-positive "verified" claim caught and corrected on review, in agent-transcripts/README.md.
- **`ship30_essay` tool:** unlike `grounded_qa`, this tool makes its **own dedicated generation call** with a Ship-30-specific system prompt (`agent/ship30_prompt.py`, encoding the actual guide's principles: WHO/WHAT/WHY hook, headline→intro→3-5 H2 "spoke" sections→TL;DR→single takeaway skeleton, bullets for 3+ items, selective bold, ~1,250 words per the brief), producing the finished Markdown essay directly as the tool's return value — a deliberate departure from `grounded_qa`'s retrieval-only pattern, decided explicitly rather than by default: the artifact needs to be a stored, standalone document (not chat text), and the brief's "encode the rules in the skill" instruction is served better by a prompt scoped only to essay-writing than by folding Ship 30 rules into the general conversational system prompt. **Grounding source:** prefers the session's own already-verified `grounded_qa` citations over a fresh retrieval call (per PRD.md §6 flow 4 — the essay synthesizes what was *already discussed*, not a new topic), falling back to a broader retrieval (`top_k=15`) on the latest raw user message only if the session has no prior grounding yet — same reasoning as `resolve_search_text`: never trust an LLM-supplied topic argument when a deterministic source exists.

  **Routing to `ship30_essay` needed its own fix, separate from the argument-quality fix above.** Live testing (5 trials of "ask a grounded question, then ask for an essay") found `llama3.2:3b` chose the *wrong tool or produced malformed output* in 4/5 cases — not an argument-quality problem, a tool-*selection* problem, independent of and in addition to Phase 4's findings. Strengthening the system prompt with explicit few-shot routing examples (the cheapest fix, keeping this section's "not by keyword matching" principle intact) was tried once and re-tested: 2/5 correct, no real improvement. Per the same discipline as the retrieval fixes — one prompt attempt, then act on the evidence rather than keep iterating — the Ollama provider now runs a **deterministic pre-check** (`_looks_like_essay_request()` in `ollama_provider.py`) that pattern-matches the latest user message for essay-request phrasing *before* invoking the LLM, calling the essay generator directly on a match. **This is an explicit, evidenced exception to this section's "not by keyword matching in application code" principle, scoped to the Ollama provider only** — nothing observed suggests Claude has this problem, so the Claude provider keeps pure intent-based tool routing, unchanged. Verified 5/5 correct essay routing and 3/3 no false positives (a plain follow-up question after a grounded answer doesn't trigger the essay path) after the fix. A JSON-recovery safety net (`_recover_malformed_tool_call`) also catches malformed tool-call attempts that leak into `content` as raw text, as defense in depth for cases the pre-check doesn't cover.

  **Essay length shortfall — root-caused to model choice, not context/prompt, and resolved by using a different model for this one call.** Precisely diagnosed, not just observed: instrumenting a real generation call showed `prompt_eval_count` (input) at only 1,193 tokens against a 16,384-token context window (no truncation possible — retrieval only returns chunks clearing the 0.35 distance threshold, often just 1 for a single-topic query, not the full `top_k`) and `done_reason: "stop"` after 725 output tokens with most of a 2,500-token budget unused. `llama3.2:3b` was *choosing* to stop short (~450-600 words against the ~1,250 target), not being cut off — confirmed it can sustain longer output in principle (an open-ended, ungrounded prompt with no structural rules produced ~999 words naturally in a side test). A strengthened, hard-requirement length instruction improved it only partially (~380→~500 words).

  Since `ship30_essay`'s generation call needs no tool-calling capability (unlike `grounded_qa`), the models disqualified in §6's tool-calling bake-off (`gemma3:4b`, `phi3:3.8b`) aren't disqualified here — that failure was tool-call-specific. Tested both, plus `qwen3:4b`, on the identical real `generate_essay()` path (same prompt, same grounding context, same `num_ctx`/`num_predict`): `gemma3:4b` reached ~1,000-1,150 words, `qwen3:4b` ~1,045-1,195 words, both with `done_reason: "stop"` (natural) in 26-58 seconds; `phi3:3.8b` reached comparable word counts but took 113-184 seconds — disqualifying for a demo regardless of output quality. **`OLLAMA_ESSAY_MODEL` (default `gemma3:4b`) is now a separate setting from `OLLAMA_CHAT_MODEL` (`llama3.2:3b`)** — the nested-call architecture already isolates essay generation from tool-calling, so different models for different jobs was a natural fit once the data supported it, not an architecture change. Verified end-to-end through the real HTTP API (not just the isolated comparison): 971 words. The Claude path is expected to perform at least as well at sustained long-form writing but remains **untested** — no `ANTHROPIC_API_KEY` configured in this environment. Full investigation and comparison numbers in agent-transcripts/README.md.

Routing between them is intent-based: a request like "turn this into an essay" or "write this up" routes to `ship30_essay`; everything else routes to `grounded_qa`. This is enforced by the agent's system prompt plus tool descriptions, not by keyword matching in application code — keeping the routing logic auditable and swappable.

---

## 6. Model Configuration

A single `LLM_PROVIDER` environment variable (`claude` | `ollama`) selects the active **chat/generation** backend at startup. Both providers implement the same outward contract — a `run(db, messages) -> AgentResult` function (`AgentResult` = final text + captured citations) — so the rest of the app (the sessions/messages endpoints) is provider-agnostic. Internally the two providers necessarily differ: `claude_provider.py` uses the Tool Runner's iterator-based execution (§5), while `ollama_provider.py` hand-rolls the loop against Ollama's raw `/api/chat` (OpenAI-style `tools` array, `message.tool_calls` with parsed — not string — arguments, continued via a `role: "tool"` message carrying `tool_call_id`; verified live against Ollama 0.13.4). The active provider is exposed via `GET /config` and shown in the UI header. If `LLM_PROVIDER=claude` but no API key is present, the app fails fast at startup with a clear error rather than failing silently on first request.

**Embeddings are a separate concern from `LLM_PROVIDER`.** Ingestion and retrieval always embed via a local Ollama model (`nomic-embed-text`, 768-dim), regardless of which provider is selected for chat. Ollama is already a required dependency for this project (the brief mandates the demo run on it), so this adds no new moving parts, requires no API key to run ingestion, and keeps behavior identical whether `LLM_PROVIDER=claude` or `ollama`. This does mean Ollama must be reachable to run the ingestion script or serve a retrieval-backed query, even when chat itself is running on Claude — documented in README.md's setup steps.

**Local chat model — bake-off resolved, not just decided:** the Phase 4 open item (§6, earlier draft) was to test `llama3.2:3b`, `gemma3:4b`, and `phi3:3.8b` for tool-calling reliability once a real tool existed. Testing against the actual `grounded_qa` schema found this isn't a close call: `gemma3:4b` and `phi3:3.8b` both return a hard error (`"does not support tools"`) from Ollama — they don't support function calling at all, not merely less reliably. `llama3.2:3b` is the only viable option of the three, confirmed empirically rather than assumed from Meta's stated tool-calling support alone. This governs `OLLAMA_CHAT_MODEL`, used for tool-calling (`grounded_qa` routing and retrieval-argument turns) — see §5's Phase 5 addendum for why essay generation (`OLLAMA_ESSAY_MODEL`) deliberately uses a *different* local model: that call needs no tool-calling capability, so `gemma3:4b`'s disqualification here doesn't apply to it, and it turned out to solve a real length shortfall `llama3.2:3b` had for long-form generation specifically.

A fourth candidate, `qwen3:4b`, was also tested as due diligence before finalizing `resolve_search_text()`'s deterministic-bypass fix (above) — some sources report qwen3 as unusually reliable at tool-calling specifically. Confirmed true: `qwen3:4b` scored 5/5 on both first-turn and follow-up retrieval using *its own* query reformulation, no bypass needed, versus `llama3.2:3b`'s ~2/5 and 0/5 in the same harness. But `qwen3:4b` is a "thinking" model — every response carries a visible reasoning trace — and took 15-50x longer per call (5.5-12.2s first-turn, 18.4-33.5s follow-up, versus `llama3.2:3b`'s 0.3-0.6s). Since the deterministic bypass already gets `llama3.2:3b` to 5/5 on both paths at native speed, swapping to `qwen3:4b` would trade no reliability gain for a latency regression severe enough to hurt the demo — not adopted. `OLLAMA_CHAT_MODEL` remains `llama3.2:3b`. Full numbers in agent-transcripts/README.md.

**Cloud chat model:** `claude-sonnet-5`, not `claude-opus-5` — grounded Q&A and essay formatting don't need frontier-tier reasoning, and this project runs on a small API budget (full build-through-demo cost estimated under $5 either way; Sonnet is chosen for cost discipline, not necessity). Not exhaustively benchmarked against Opus for this specific workload.

**Local chat model:** PRD.md §8 mandates keeping the local model small (3B-class) to bound cold-start latency. `llama3.2:3b` is the working default — Meta documents explicit tool-calling support at this size, which matters because §5's agent routing depends on reliable tool-call emission, not just chat quality. This has not yet been empirically verified against alternatives (`gemma3:4b`, `phi3:3.8b`). **Open item for Phase 4:** run a short tool-calling bake-off across these three once the `grounded_qa`/`ship30_essay` tool routing exists, and lock in whichever proves most reliable — the result doubles as the "one important technical trade-off" the demo video is required to cover.

---

## 7. Security: Artifact Rendering

Generated HTML is treated as untrusted user-influenced content. It is rendered inside a **sandboxed iframe** (`sandbox` attribute with no `allow-same-origin` and no `allow-scripts` unless explicitly needed for an interactive artifact) combined with a **sanitization pass** (stripping `<script>`, inline event handlers, and external resource loads) before being written into the iframe's `srcdoc`. Markdown artifacts are rendered through a standard Markdown-to-safe-HTML pipeline with the same sanitization applied. The viewer explicitly does **not** permit arbitrary JavaScript execution against the parent page, network calls out of the sandbox, or access to cookies/localStorage of the main app.

**Phase 6 implementation notes:** the project has no actual HTML-artifact-generating tool (only `ship30_essay`, which produces Markdown) — the frontend still implements the HTML/iframe path per the schema (`artifacts.type` supports `'html'`), using an **empty `sandbox` attribute** (maximum restriction: no scripts, no same-origin, nothing) since there's no legitimate interactive-artifact use case in this project's actual scope, plus a DOMPurify pass stripping `<script>`/`<iframe>`/`<object>`/`<embed>`/inline event handlers before writing to `srcdoc`. Markdown rendering uses `react-markdown` without the `rehype-raw` plugin — it renders its AST directly to React elements and never executes embedded raw HTML by default, which already satisfies "Markdown-to-safe-HTML with sanitization" without a separate DOMPurify pass on that path. Citation chips deep-link to `{episode_source_url}&t={seconds}` per §4, rather than a separate "expand source text" panel — no chunk-text-by-id endpoint exists, and the citation was already designed to point at the exact source moment.

---

## 8. Resilience & Observability

- Missing API key → fail-fast at startup with a clear log line, not a runtime crash on first use
- Ollama unreachable for **chat generation** (`LLM_PROVIDER=ollama`) → caught at the provider-call boundary, surfaced to the user as a structured error, logged with the attempted host
- Ollama unreachable for **embeddings** (ingestion or retrieval's query embedding, per §6 — this applies even when `LLM_PROVIDER=claude`, since embeddings always go through local Ollama) → caught at the embedding-call boundary, surfaced as a structured error distinct from the chat-provider error, not silently treated as "no results"
- Empty retrieval results → handled as a normal (non-error) path, triggering the grounding fallback response
- Database connection failure → health endpoint reports it; request-time failures return a structured 503, not a raw exception
- Structured logs (JSON) emitted around: model calls (provider, latency, token count if available), retrieval (query, chunk count returned, top similarity score), and artifact rendering (type, sanitization outcome)

**Phase 7's actual scope, confirmed against Phase 3's `AppError` foundation (`core/errors.py`):**
`AppError`'s `(status_code, error_code, message)` shape is already generic enough to represent all three request-time failure types above (chat-Ollama-down, embedding-Ollama-down, DB-down) as distinct structured errors — no change to `AppError` itself needed, just new `error_code` constants and `raise AppError(...)` calls at the right boundaries. What Phase 7 actually has to add:
1. **A startup-time fail-fast mechanism, separate from `AppError` entirely** — the missing-API-key case can't go through request-time exception handling (nothing has served a request yet), so it needs its own check in `main.py`'s `lifespan()` (or a `Settings` validator) that prevents the app from starting, with a clear log line.
2. **Two new registered exception handlers in `core/errors.py`**, translating existing/expected domain exceptions into the `AppError` response shape, the same way `RequestValidationError` is already handled — as of Phase 3, neither of these is wired up (verified by grep: `EmbeddingError` is raised in `ingestion/embeddings.py` but caught nowhere, and a DB failure would fall through to the generic `Exception` handler and return `500 INTERNAL_ERROR`, not the `503` §8 specifies):
   - `@app.exception_handler(EmbeddingError)` → `503`, distinct `error_code` from the chat-provider error (this is also the handler the Phase 7 required test case above exercises).
   - `@app.exception_handler(OperationalError)` (SQLAlchemy) → `503`, not lumped in with genuinely unexpected bugs.

**Required Phase 7 test case (do not substitute a generic "Ollama down" test for this):**
`LLM_PROVIDER=claude`, a valid `ANTHROPIC_API_KEY` set, Ollama process stopped. Send a message that requires retrieval. Assert: the response is a structured error naming the embedding/Ollama failure specifically — not a 200 with an empty-retrieval fallback answer, not an unhandled 500, and not misattributed to the chat provider (which is Claude and is working fine here). This is the one combination where chat succeeds while retrieval silently breaks underneath it, so it's the case most likely to be skipped if testing just exercises "Ollama down" once against `LLM_PROVIDER=ollama` and calls it covered.

---

## 9. Deployment Topology

- `docker-compose.yml` defines: `api` (FastAPI), `db` (Postgres + pgvector extension), and optionally `ollama` (if resource-feasible on the evaluator's machine — otherwise documented as "run Ollama natively, point `OLLAMA_HOST` at it")
- `.env.example` documents all required/optional variables with safe placeholder defaults
- Single command (`docker compose up`) brings up the full stack for evaluation
