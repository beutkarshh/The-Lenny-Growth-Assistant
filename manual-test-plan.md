# Manual UI Test Plan: The Lenny Growth Assistant

Automated tests (`backend/tests/`) cover API, retrieval, routing, and
persistence behavior at the HTTP/DB level. This document covers what those
tests structurally cannot: the actual rendered UI, real browser behavior,
and the interaction states defined in `design.md` §3. Per the assignment
brief's ask for "a short manual test plan for the UI" — this is deliberately
a checklist a reviewer can run in 15-20 minutes, not an exhaustive matrix.

**Setup:** `docker compose up -d`, frontend at http://localhost:5173, backend
at http://localhost:8000. `GET /config` should report the active
`llm_provider` before starting — note which provider is active, since some
cases (essay routing reliability, Claude-path banner) behave differently by
provider and that should be recorded alongside results, not assumed away.

---

## 1. Idle / empty state

| Step | Expected | Ref |
|---|---|---|
| Load http://localhost:5173 fresh (no sessions yet, or none selected) | Sidebar shows "No sessions yet." Chat panel shows a prompt inviting a question about growth/product strategy — not a blank panel. | design.md §3 row 1 |
| Open browser devtools console before and during load | No console errors. (Note: React StrictMode double-invokes effects in dev, so `GET /config` and `GET /sessions` firing twice is expected, not a bug.) | — |

## 2. Creating and switching sessions

| Step | Expected | Ref |
|---|---|---|
| Click "+ New session" | A new session appears in the sidebar and becomes active; composer is enabled once the round trip completes. | design.md §2 |
| Click "+ New session", then **immediately** try to type and send a message before the new session finishes loading | Composer must be disabled ("Loading session…" state) for the entire round trip — message must not be sent to the *previous* session. This is a regression check for a real race condition fixed in Phase 6 (see `agent-transcripts/README.md`, Phase 6 entry): the composer's old `disabled={!session}` check stayed false during session creation, so a fast-typed message could attach to the stale session. | Phase 6 fix |
| With a session mid-switch (loading state active), click "+ New session" again rapidly several times | **Known gap, not yet fixed:** the sidebar's "+ New session" button has no disabled state tied to `isSwitchingSession`, so spamming it during a transition is possible. Record whether this produces duplicate/orphaned sessions — flagging for a decision on whether it's worth fixing before submission. | — |
| Click between two existing sessions in the sidebar | Each session's own message history loads correctly; active row is visually highlighted (and has `aria-current="true"` — check via devtools accessibility tree, not just visually). | design.md §5 |

## 3. Grounded question — happy path

| Step | Expected | Ref |
|---|---|---|
| In a fresh session, ask a question clearly covered by the corpus (e.g. "What have guests said about referral program risks?") | User message appears immediately (optimistic render). A "Thinking…" indicator appears on the assistant side while awaiting response. | design.md §3 row 2 |
| Wait for the response | Assistant answer renders as Markdown, with citation chips below it — NOT hidden behind a toggle. Each chip shows `🔗 {episode title} · {timestamp}` and links out to the source video at that timestamp. | design.md §6 |
| Hover/click a citation chip | Link opens the correct episode's YouTube URL with a `t=` timestamp parameter appended. Check a source URL that lacks its own `?` query param elsewhere in the corpus — the chip's `&t=` concatenation assumes a `?` already exists in the URL; confirm this doesn't produce a malformed link. | — |
| Ask a two-turn follow-up referencing "that" / "it" from the previous answer | Response is still correctly grounded (uses conversation context to resolve the follow-up), not a "not covered" fallback. Per `agent-transcripts/README.md` Phase 4, this path is measured at 5/5 success on Ollama after the deterministic follow-up fix — a single failure here on Ollama is plausible small-sample variance, not necessarily a regression; a **repeated** failure would be. | Phase 4 fix |

## 4. No-match / fallback state

| Step | Expected | Ref |
|---|---|---|
| Ask something clearly outside the corpus (e.g. "What's Lenny's favorite pizza topping?") | Assistant response is visually distinct from a confident answer — dashed border / muted styling, with an "ⓘ Not covered in transcripts" header. Must be distinguishable by icon + border, not color alone (accessibility requirement). | design.md §3 row 4, §5 |

## 5. Essay generation

| Step | Expected | Ref |
|---|---|---|
| After a grounded question has been answered in a session, ask for an essay (e.g. "Turn that into a Ship 30 essay") | Artifact panel opens showing a loading/skeleton state ("Writing your essay…", `aria-live="polite"`) — not a blank panel — while generation is in progress. | design.md §3 row 5 |
| Wait for generation to complete | Rendered essay appears in the panel with a visible word count. Confirm the count is in a reasonable range of the ~1,250-word target — see `agent-transcripts/README.md` Phase 5 for the measured range per provider/model (roughly 900-1000 words on the current default Ollama setup with `gemma3:4b`; expect materially higher on the Claude path, untested as of Phase 8). | design.md §3 row 6, Phase 5 |
| In the chat thread, find the message that triggered the essay | Message shows a "📄 View essay" button; clicking it reopens the artifact panel to that essay. | — |
| In the artifact panel, click "Copy" | Button label changes to "Copied!" for ~1.5s, then reverts. Paste somewhere to confirm actual essay text was copied, not e.g. HTML markup. | — |
| Click "Download" | A file downloads with the correct extension (`.md` for Markdown artifacts, `.html` for HTML artifacts) and matching content. | — |
| Ask for an essay in a **brand-new** session with no prior grounded question | Assistant should clearly explain there isn't enough grounded material yet, not fail silently or produce an empty/garbled artifact. | Phase 6 (original bug this masked) |
| Try phrasings that don't match common essay-request wording (e.g. "compose a piece about this") | On Ollama, essay-vs-question routing is a known reliability area (see `agent-transcripts/README.md` Phase 5) — a missed classification just delays the artifact panel opening until the backend actually returns an `artifact_id`, it should not send the wrong request type entirely. Record any case where a clearly essay-shaped request instead returns a plain grounded answer. | Phase 5 |

## 6. HTML artifact sandboxing (if/when an HTML artifact type is exercised)

| Step | Expected | Ref |
|---|---|---|
| Open an HTML-type artifact in the panel | Renders inside a sandboxed iframe with `sandbox=""` (no scripts, no same-origin, no forms — verify via devtools that the iframe element's `sandbox` attribute is present and empty, not missing). | architecture.md §7 |
| Inspect the iframe content vs. the original artifact content (devtools) | Script tags, `iframe`/`object`/`embed`/`link`/`meta`/`base` tags, and `on*` event attributes should all be stripped (DOMPurify pass before rendering). | architecture.md §7 |

## 7. Provider indicator

| Step | Expected | Ref |
|---|---|---|
| Check the chat panel header | A provider badge is visible, colored purple for "Claude" or green for "Ollama (local)", matching whatever `GET /config` currently reports. | design.md §2 |

## 8. Failure states (resilience)

Each of these requires deliberately breaking a dependency — confirm you can restore it afterward before moving on, since later test sections depend on a working system.

| Step | Expected | Ref |
|---|---|---|
| Stop the Ollama process (or `ollama_chat`/`ollama_essay` container/service, whichever applies to your setup), then send a message | A clear inline error banner appears (not a silent hang, not a raw stack trace) explaining the local model is unreachable. Restart Ollama and confirm the next message succeeds. | design.md §3 row 7, architecture.md §8 |
| Stop the `db` container (`docker compose stop db`), then send a message or load sessions | Structured error banner surfaces a database-unavailable message, not a blank/broken UI. Restart the `db` container and confirm recovery. | architecture.md §8 |
| Send a message, then immediately kill the network tab / block the request (devtools) to force a client-side network failure | Error banner shows a generic "couldn't reach the backend" message. **Check the message bubble that was already optimistically rendered for that failed send** — per the current implementation, a failed send does not remove the optimistic user bubble, so it may appear to have "sent successfully" in the thread even though only the top banner indicates failure. Record whether this is confusing enough to flag for a fix. | — |
| Dismiss an error banner (✕) | Banner disappears; a new error later still displays correctly (i.e. dismissal doesn't break the banner permanently). | — |

## 9. Accessibility spot-checks

| Step | Expected | Ref |
|---|---|---|
| Tab through the page using only the keyboard | Composer input, send button, "+ New session", session rows, citation chips, artifact copy/download/close all reachable in a sensible order with a visible focus outline. | design.md §5 |
| Trigger an error banner with a screen reader running (or inspect `aria-live` in devtools) | Banner is announced (`role="alert"`, `aria-live="assertive"`) without requiring focus to move there manually. | design.md §5 |
| Inspect the message thread container | Uses `aria-live="polite"` — confirm this doesn't produce excessive/distracting announcements as multiple messages stream in during a single exchange. | design.md §5 |

## 10. Responsive behavior (lower priority — see design.md §4)

| Step | Expected | Ref |
|---|---|---|
| Resize the browser to a narrow/mobile width | Layout should not silently break (overlapping panels, unreadable text). Full mobile polish is explicitly out of scope per design.md §4 — the bar here is "not broken," not "fully optimized." | design.md §4 |

---

## Known gaps surfaced while writing this plan (not fixed, flagged for a decision)

These were found by reading the actual component implementation while
grounding this test plan, not by running the tests yet. Listed here rather
than silently patched, consistent with this project's scope-discipline
practice:

1. **Sidebar "+ New session" has no disabled state during a session switch** — only the composer is protected against the race the Phase 6 fix addressed; the sidebar button itself isn't.
2. **A failed message send leaves the optimistic user bubble in the thread permanently** — only the global error banner indicates failure; there's no visual marker on the specific failed message itself.
3. **Artifact word count on empty content reports `1`, not `0`** — `"".trim().split(/\s+/)` produces `[""]`, length 1. Unlikely to occur in practice (an essay artifact should never be empty), but worth a quick look if it ever surfaces during testing.
4. **Citation chip links assume the source URL already contains a `?` query parameter** before appending `&t={seconds}` — untested against a source URL that doesn't.

None of these are severe enough to have blocked writing this plan, but they're real, so they're listed rather than omitted.
