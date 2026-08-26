# The Lenny Growth Assistant

A grounded, conversational assistant over 53 episodes of Lenny's Podcast. Ask a growth/product-strategy question and get a cited answer sourced from real transcript chunks (with deep links to the exact moment in the source video), or ask for a Ship 30 for 30–style essay distilling a conversation into a shareable, formatted piece.

Full design reasoning lives in three planning docs, written before any code and kept in sync with what was actually built:

- [`PRD.md`](PRD.md) — problem framing, persona, scope, success metrics
- [`architecture.md`](architecture.md) — schema, API surface, ingestion/retrieval pipeline, agent routing, model choices, resilience
- [`design.md`](design.md) — UI/UX principles and key interaction states

This README covers everything needed to actually run it.

---

## Architecture at a glance

```
Frontend (React/Vite)  ⇄  FastAPI backend  ⇄  PostgreSQL + pgvector
                              │
                    ┌─────────┴─────────┐
              grounded_qa            ship30_essay
              (retrieval-only)      (dedicated generation call)
                    │
              Claude (cloud) or Ollama (local) — selected by LLM_PROVIDER
```

- **Retrieval:** every user message is embedded (always via a local Ollama model, `nomic-embed-text`, regardless of chat provider) and matched against `transcript_chunks` via pgvector cosine distance. Below-threshold results are a normal "not covered" path, not an error.
- **Two tools, kept separate:** `grounded_qa` returns raw matched chunks and lets the outer chat model compose a cited answer; `ship30_essay` makes its own dedicated generation call with a Ship-30-specific system prompt and returns a finished Markdown essay as a stored artifact.
- **Two interchangeable chat providers:** `claude` (Anthropic's Tool Runner) and `ollama` (a hand-rolled loop against Ollama's `/api/chat`), selected by one environment variable, both implementing the same `run(db, messages) -> AgentResult` contract.

See `architecture.md` §1–§6 for the full reasoning behind each of these choices, including the local-model reliability issues that shaped several deterministic workarounds (query formulation, essay-routing pre-checks) — all called out explicitly there as evidenced exceptions, not silent hacks.

---

## Prerequisites

- **Docker Desktop** (or Docker Engine + Compose v2) — runs the API, frontend, and Postgres/pgvector.
- **[Ollama](https://ollama.com/download)**, installed and running **natively on your host machine** — not inside Docker. Embeddings always go through it regardless of which chat provider you choose, so it's required either way.
- ~5 GB free disk for the three Ollama models pulled below.
- Optional: an Anthropic API key, only if you want to run the cloud (Claude) chat path instead of the local one.

### Pull the required Ollama models

```bash
ollama pull nomic-embed-text   # embeddings — always required
ollama pull llama3.2:3b        # local chat model — required for LLM_PROVIDER=ollama
ollama pull gemma3:4b          # local essay-generation model — required for LLM_PROVIDER=ollama
```

Confirm Ollama is reachable before starting the app:

```bash
curl http://localhost:11434/api/version
```

---

## Quick start

```bash
git clone <this-repo>
cd "The Lenny Growth Assitant"
cp .env.example .env      # defaults work out of the box for the local (Ollama) path
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000 (`/health`, `/docs` for the auto-generated OpenAPI UI)

**The transcript corpus needs to be ingested once** before grounded answers will return anything — see [Ingesting the transcript corpus](#ingesting-the-transcript-corpus) below. Everything else (sessions, chat, essays) works immediately; retrieval will just always report "not covered" until ingestion has run.

---

## Environment variables

All variables are documented inline in [`.env.example`](.env.example); copy it to `.env` before starting. Summary:

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `lenny` / `change_me` / `lenny_growth_assistant` | Used by both the `db` container and the API's connection string. Change the password for anything beyond local evaluation. |
| `POSTGRES_PORT` | `5432` | Host-side port; change if already taken locally. |
| `POSTGRES_HOST` | `db` | The Compose service name — only change if running outside Compose. |
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | How the `api` container reaches Ollama running on your host. `host.docker.internal` works on Docker Desktop (Mac/Windows). **On native Linux Docker**, replace with your host's actual IP, or run Ollama in a container on the same Compose network. |
| `LLM_PROVIDER` | `ollama` | `ollama` (default, no key needed) or `claude` (needs `ANTHROPIC_API_KEY`). |
| `ANTHROPIC_API_KEY` | *(empty)* | Only required when `LLM_PROVIDER=claude`. The app **fails fast at startup** with a clear error if `LLM_PROVIDER=claude` and this is unset — it won't silently fail on the first request. |
| `OLLAMA_CHAT_MODEL` | `llama3.2:3b` | Used for tool-calling (`grounded_qa` routing). Must support tool calling — empirically, `gemma3:4b` and `phi3:3.8b` do **not** (Ollama returns a hard `"does not support tools"` error), so don't swap this without checking (see `architecture.md` §6). |
| `OLLAMA_ESSAY_MODEL` | `gemma3:4b` | Used only for `ship30_essay`'s generation step — deliberately a *different* model from `OLLAMA_CHAT_MODEL`. This call doesn't need tool-calling, and `llama3.2:3b` measurably under-shoots the ~1,250-word essay target (~450–600 words) where `gemma3:4b` reaches ~1,000–1,150. See `architecture.md` §5/§6. |

**Important:** if you change any `.env` value while containers are already running, `docker compose restart` does **not** pick it up — you need `docker compose up -d <service>` (e.g. `docker compose up -d api`) to recreate the container with the new environment.

---

## Running with the local model (Ollama) — default

No extra setup beyond the Prerequisites section above. `LLM_PROVIDER=ollama` is the default in `.env.example`.

Trade-offs to expect, documented openly rather than glossed over:
- Cold-start latency on first request after Ollama has been idle.
- Local-model answer quality is lower than Claude's — see [Known limitations](#known-limitations) below for the two specific, measured gaps.

## Running with Claude (cloud)

1. Get an Anthropic API key from https://console.anthropic.com/.
2. In `.env`, set:
   ```
   LLM_PROVIDER=claude
   ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Recreate the API container so it picks up the new environment: `docker compose up -d api`.
4. Confirm via `GET /config` or the provider badge in the UI header — it should now show "Claude (cloud)."

Note: embeddings still go through local Ollama even on the Claude path (see architecture.md §6) — Ollama must still be running and reachable.

**Status: code-complete, not fully verified end-to-end.** The Claude provider, its error handling (`anthropic.APIError` → structured `503 CLAUDE_PROVIDER_ERROR`), and the Tool Runner integration were exercised against real live failures during development (an invalid key, then an account with insufficient credit balance — both correctly surfaced as clean structured errors instead of a raw 500). But billing was never resolved in this environment, so a fully successful Claude chat turn, the Claude-path essay-length comparison, and the frontend flow on the Claude provider have not been run against a working key. See [Known limitations](#known-limitations).

---

## Ingesting the transcript corpus

Grounded answers have nothing to retrieve until this has run once:

```bash
docker compose exec api python -m app.ingestion.ingest
```

This fetches 53 curated episodes of Lenny's Podcast from the source transcript archive (selection methodology in `architecture.md` §4), chunks them, embeds each chunk via local Ollama, and stores them in `transcript_chunks`. It's idempotent — re-running clears and rebuilds the table from scratch, so it's safe to re-run after a code change to the chunking logic (this happened for real: see [Known limitations](#known-limitations)).

Takes a few minutes, depending on your machine — it's calling the local embedding model ~1,500+ times.

---

## Running tests

Automated tests run inside the API container against a dedicated test database (`{POSTGRES_DB}_test`, created automatically, fully isolated from the real ingested corpus):

```bash
docker compose exec api python -m pytest tests/ -v
```

39 tests covering API/session endpoints, structured error handling, retrieval (real pgvector queries against inserted test data), transcript chunking (including a regression test for a real regex bug — see below), and essay-generation grounding logic (diversity capping, recency windowing, guest-label parsing).

For UI/interaction states that automated tests can't cover (loading states, citation click-through, accessibility, failure banners), see [`manual-test-plan.md`](manual-test-plan.md) — a ~15–20 minute manual checklist tied to `design.md`'s documented interaction states.

---

## Troubleshooting

**"Not covered in the available transcripts" for everything, even obviously on-topic questions.**
The corpus hasn't been ingested yet. Run the ingestion command above.

**API container fails to start / crashes immediately with `LLM_PROVIDER=claude`.**
`ANTHROPIC_API_KEY` is unset. This is intentional fail-fast behavior (architecture.md §6) — set the key or switch back to `LLM_PROVIDER=ollama`.

**`Ollama unreachable` / `503 OLLAMA_CHAT_UNREACHABLE` / `503 OLLAMA_EMBEDDING_UNREACHABLE`.**
Confirm Ollama is actually running on the host (`curl http://localhost:11434/api/version`) and that `OLLAMA_HOST` in `.env` is reachable from inside the container. On native Linux Docker, `host.docker.internal` doesn't resolve by default — use the host's real IP or run Ollama in a container on the same network.

**Changed `.env` but the app is still behaving with the old values.**
`docker compose restart` doesn't reload environment variables — use `docker compose up -d <service>` instead.

**Frontend shows stale styling / component changes after editing frontend files.**
Two known causes, both already worked around in this repo, but worth knowing if you extend it further:
- Docker Desktop's Windows bind mounts don't always forward file-change events reliably into the Linux container — Vite is configured with `server.watch.usePolling: true` in `vite.config.ts` to compensate.
- `tailwind.config.js` and `index.html` are mounted individually alongside `src/` in `docker-compose.yml`'s `frontend` service — if you add a new top-level frontend config file, remember to add its own volume mount too, or the container will keep using the version baked into the image at build time. (This exact gap caused a custom Tailwind color palette to silently have no effect during development — fixed by adding the missing mount.)

**Backend test changes aren't reflected when running `pytest` in the container.**
Same category of issue: `backend/tests/` is a separate volume mount from `backend/app/` in `docker-compose.yml`. Both are mounted, and `Dockerfile` copies both at build time, but a stale image (built before a mount was added) needs `docker compose up --build` once, not just `up -d`.

**Health check reports `"degraded"`.**
`GET /health` checks real DB connectivity and, on the Ollama path, a live `/api/version` ping — it's telling you the truth about a real dependency being down, not a bug in the check itself. Restart the failing dependency (`docker compose restart db`, or restart Ollama natively) and re-check.

---

## Known limitations

Documented here deliberately, not discovered by an evaluator the hard way. Full investigation trails (including wrong initial diagnoses that were corrected before being written up as final) are in `agent-transcripts/README.md`.

1. **Essay length on the local model path is model-dependent, and was root-caused rather than assumed.** `llama3.2:3b` under-shoots the ~1,250-word Ship 30 target (~450–600 words) even with an explicit hard length requirement in the prompt — confirmed via direct instrumentation to be the model choosing to stop early (`done_reason: "stop"`, well under its token budget), not a context-window or truncation bug. Switching the essay-generation call specifically to `gemma3:4b` (`OLLAMA_ESSAY_MODEL`) resolved it, reaching ~900–1,150 words consistently across repeated real end-to-end trials. This is why essay generation uses a different local model than tool-calling/chat.

2. **Residual cross-guest misattribution in essay generation, on the local model path, for essays synthesizing multiple guests.** When an essay is grounded in chunks from several different episodes, `gemma3:4b` can attribute a real, correctly-retrieved quote to the wrong guest — confirmed by checking specific essay claims against the actual source transcripts, not assumed. Two mitigations are in place and measurably help: capping essay grounding to at most 4 distinct episodes (`MAX_ESSAY_EPISODES` in `ship30_essay.py`) instead of feeding in every citation ever accumulated in a session, and moving each source's guest name to the front of its label in the generation prompt rather than burying it in a long descriptive title. Both were verified across multiple real end-to-end trials to improve specific, previously-wrong attributions (e.g. a "flying formation" quote is now reliably attributed to the correct guest). One specific concept ("data network effects") remained mis-attributed in most trials even after both fixes — tracked as an accepted, measured local-model limitation rather than something a further prompt tweak was likely to fix. **Single-guest, narrowly-scoped essay requests are not affected** — verified accurate against the source transcript in a real trial with no cross-guest content at all.

3. **The Claude (cloud) path is code-complete but not fully verified end-to-end**, purely due to an external billing constraint in the development environment (see [Running with Claude](#running-with-claude-cloud) above). Error handling for real Claude failures (invalid key, insufficient credits) was verified against actual live API responses. What remains unverified: a fully successful Claude chat/essay turn, the frontend on the Claude provider, and whether Claude's larger model resolves limitations #1 and #2 above (expected, based on general model-capability patterns observed elsewhere in this project, but not confirmed).

4. **A real data-quality bug was found and fixed during Phase 8 testing, not before.** The transcript-chunking regex had a latent bug (`\s+` matching across newlines in a "speaker name" capture group) that silently dropped ~22% of turns across 74% of the ingested corpus — caught by a unit test with a 3-line synthetic fixture, not by the much larger manual verification passes earlier in the project. Fixed, and the full corpus was re-ingested (1,570 chunks, up from 1,037). Included here as a known-and-resolved issue, not a currently-open one — flagged specifically because it's a good illustration of why the automated test suite exists, per the assignment brief's own emphasis on meaningful tests.

---

## Project structure

```
backend/
  app/
    agent/          # grounded_qa + ship30_essay tools, provider implementations, routing
    api/routes/      # FastAPI endpoints
    core/            # settings, structured error handlers
    db/              # SQLAlchemy models, session management
    ingestion/       # transcript fetching, chunking, embedding, the ingestion script
  tests/             # pytest suite — see "Running tests" above
frontend/
  src/
    components/      # SessionSidebar, ChatPanel, MessageBubble, CitationChips, Composer, ArtifactPanel
    api.ts           # typed backend client
agent-transcripts/    # raw session logs + a curated index of notable bugs/investigations, per the
                      # assignment's "keep failed attempts visible" deliverable
PRD.md, architecture.md, design.md, manual-test-plan.md   # planning docs (see top of this file)
```
