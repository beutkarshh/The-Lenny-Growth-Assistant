# PRD: The Lenny Growth Assistant

## 1. Overview

The Lenny Growth Assistant is an internal, AI-powered conversational web application that lets product and growth teams ask questions grounded in Lenny's Podcast/Newsletter transcripts, receive sourced answers, and turn those answers into polished, publishable written content — without needing to understand prompting, models, or infrastructure.

This document covers the discovery framing (user, problem, success metric, assumptions, scope, risks), the product flows, and acceptance criteria for the build.

---

## 2. User and Problem

**Primary user:** Priya, a Growth PM at a ~200-person B2B SaaS company.

**Job to be done:** Priya needs to form credible, well-supported opinions quickly — for internal strategy debates, leadership syncs, and roadmap decisions — and periodically turn those insights into external content (LinkedIn posts, blog essays) to build her own voice as a thoughtful growth practitioner.

**Pain removed:** Today, getting expert-backed answers to a specific question ("what do experienced operators say about referral program risks?") means manually scrubbing through hours of podcast audio or trusting her own instinct. The assistant collapses that into a direct, sourced answer in seconds, and removes the separate step of writing polished content from scratch by generating a grounded, formatted essay on request.

**Why this persona:** The brief itself frames the engagement as being for "a product and growth team." Priya is a concrete instantiation of that framing, and — critically — she is the only persona under consideration whose day-to-day work naturally requires *both* required product capabilities (grounded Q&A and content generation), rather than one feeling bolted on to justify the other.

---

## 3. Success Metric

**Primary metric:** Citation accuracy rate — the % of test questions (from a hand-labeled evaluation set of ~20-30 representative queries) that are answered with a correct, verifiable source citation and no hallucinated claim. This directly targets the single largest risk in the system (hallucination) and is measurable without subjective judgment.

**Secondary metrics (tracked but not rigorously benchmarked given project timeline):**
- Time-to-answer (end-to-end response latency, including local-model cold start)
- % of generated Ship 30 for 30 essays meeting the stated format spec (word count, headings, single takeaway) without manual editing

---

## 4. Assumptions

Made explicit because the client brief was intentionally underspecified:

- Single-tenant, no user accounts or auth — one shared workspace, since access control is not the focus of this evaluation
- The transcript corpus is a curated subset (53 episodes spanning a range of PM/growth topics), not Lenny's full 269-episode archive — ingesting everything was judged not to be a meaningful signal of engineering judgment within this timeframe. Selection method: topic-tag-based ranking against a growth+PM-weighted set of the source repo's index files, followed by two rounds of full-text verification against this PRD's own example-flow keywords (referral, incentive gaming, activation metrics, prioritization frameworks, PLG). The verification rounds surfaced genuine gaps the tags alone missed — e.g. Elena Verna and Rahul Vohra weren't tag-matched to any growth/PM topic despite being clearly relevant guests — which grew the set from an initial ~40 to 54. A post-ingestion integrity check then caught one selected episode (`jackie-bavaro`) as an upstream data bug in the source repo — the folder's `guest` field was wrong; its actual content was a duplicate of an already-included Claire Vo episode — and it was dropped, landing at the final 53. Full methodology in architecture.md §4.
- English-language content only
- Ingestion is a one-time/manual script rather than a live refresh pipeline; documented as future work
- The client is comfortable with a local-first demo (Ollama) for privacy-sensitive scenarios, with a cloud provider available as an opt-in for higher answer quality

---

## 5. Scope

**In scope:**
- Grounded conversational Q&A over transcripts, with session persistence and per-claim source citations
- Explicit "not covered in source material" fallback when retrieval has no relevant match
- Ship 30 for 30 essay-generation skill, as a distinct structured tool (not an ad-hoc prompt)
- Markdown/HTML artifact viewer rendered beside the chat
- Sandboxed/sanitized rendering for generated HTML
- Swappable LLM configuration: cloud (Claude) and local (Ollama), selectable via config, with the active provider visible to the user
- One-command local deployment via Docker Compose

**Out of scope (and why):**
- Multi-user authentication — not core to the evaluation criteria (product/AI judgment, not access control)
- Full transcript archive ingestion — a representative subset is sufficient to prove the retrieval/grounding pattern
- Token-by-token streaming responses — nice-to-have, cut under time pressure in favor of correctness and resilience
- Analytics/usage dashboards — not requested by any stated evaluation criterion

---

## 6. Flows (Day in the Life)

1. **Morning prep:** Priya opens a new session and asks a strategic question ("What have guests said about referral program risks?"). The assistant retrieves relevant transcript chunks and answers with per-claim citations.
2. **Follow-up:** She asks a natural follow-up ("How do they prevent incentive gaming?") without restating context — the assistant resolves it within the same session.
3. **Out-of-knowledge question:** She asks something the transcripts don't cover. The assistant explicitly states the material doesn't address it, rather than fabricating an answer.
4. **Content generation:** After the meeting, she asks the assistant to turn the conversation into a Ship 30 for 30–style essay. The skill produces a ~1,250-word grounded piece with a hook, skimmable formatting, and one takeaway.
5. **Artifact review:** The essay renders in a side panel next to the chat, not as raw text in the conversation, so she can read and copy it cleanly.
6. **Return visit:** Days later, she starts a new session for an unrelated topic; her earlier session remains accessible.

---

## 7. Acceptance Criteria

- A user can start a new chat session and receive independently-scoped context from other sessions
- Every factual claim in a grounded answer is attributable to a specific transcript source
- When no relevant transcript content exists, the assistant states this explicitly rather than answering from general knowledge
- The Ship 30 for 30 skill produces output matching the stated format constraints (~1,250 words, headings/bullets, single takeaway) from a grounded conversation
- Generated Markdown/HTML renders in a dedicated artifact viewer alongside the chat, not inline as raw code
- Generated HTML is sandboxed/sanitized; the mechanism is documented in `architecture.md`
- The system runs locally via Ollama with no cloud API key configured, and via a cloud provider when one is supplied — the active provider is visible to the user
- The system degrades gracefully (clear error, not a crash) when: an API key is missing, Ollama is unreachable, retrieval returns zero results, or the database connection fails
- A fresh evaluator can clone the repository and run the full system using only the documented steps in `README.md`

---

## 8. Risks and Trade-offs

| Risk | Mitigation |
|---|---|
| Hallucination (assistant states unsupported claims) | Confidence threshold on retrieval; explicit "not covered" fallback; citation required for every claim |
| Local model (Ollama) answer quality is lower than cloud | Documented openly in README rather than hidden; cloud path available as opt-in |
| Latency, especially local-model cold start | Set clear expectations in README; keep local model small (e.g., 3B-class) |
| Unsafe HTML artifact rendering | Sandboxed iframe rendering with a restrictive sanitization pass; documented in `architecture.md` |
| Data leakage to cloud provider for sensitive queries | Local-first option via Ollama; provider choice visible and explicit in config |
| Incomplete transcript coverage limits usefulness | Explicitly scoped and disclosed as a deliberate trade-off, not a hidden gap |

---

## 9. Implementation Plan (High Level)

1. Ingestion pipeline: transcript chunking, embedding, storage (Postgres/pgvector) with source metadata
2. FastAPI backend: sessions, message persistence, request/response contracts, health endpoint
3. Agent layer (Claude Agent SDK) wired to retrieval as a tool; provider-switch config (cloud/local)
4. Grounded Q&A flow with citation and fallback behavior
5. Ship 30 for 30 skill as a distinct tool with encoded format rules
6. Frontend chat UI with side-panel Artifact Viewer (sandboxed HTML rendering)
7. Docker Compose packaging, `.env.example`, structured logging, resilience handling
8. Tests, documentation (`README.md`, `design.md`, `architecture.md`), demo video
