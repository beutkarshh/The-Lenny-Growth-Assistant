# Design: The Lenny Growth Assistant

This document covers UI/UX principles, information architecture, key interaction states, responsive behavior, accessibility considerations, and the reasoning behind each design decision. It is written to be consistent with the persona, flows, and technical constraints defined in `PRD.md` and `architecture.md`.

---

## 1. Design Principles

1. **Trust over polish.** Priya is using this to back real decisions in real meetings — every answer must make its sourcing visible and its confidence legible. Where a choice exists between a cleaner-looking UI and a more transparent one (e.g., hiding vs. showing citations), transparency wins.
2. **Two things happen here, and both should feel first-class.** Asking a grounded question and generating a shareable essay are equally core (see PRD §2) — the interface should not visually demote one to a "bonus feature."
3. **Never let the user wonder what the system is doing.** Retrieval, model calls, and artifact generation all take real time (especially on a local model). Every asynchronous action needs a visible, honest state — no silent waiting, no fake instant results.
4. **Fail loud, fail politely.** Per the resilience requirements in `architecture.md` §8, every failure mode (missing key, Ollama down, empty retrieval, DB failure) must surface as a clear, human-readable message — never a raw error or a silently stuck UI.

---

## 2. Information Architecture

```
App
├── Session Sidebar
│   ├── New Session button
│   └── List of past sessions (created_at, first-message preview)
├── Main Chat Panel
│   ├── Message thread (user + assistant turns)
│   ├── Citation chips under grounded assistant replies
│   ├── Message composer (text input + send)
│   └── Active provider indicator (Claude / Ollama), from GET /config
└── Artifact Viewer Panel (collapsible, appears on generation)
    ├── Artifact type label (Markdown / HTML)
    ├── Rendered content (sandboxed for HTML, per architecture.md §7)
    └── Copy / download action
```

**Why a two-panel layout (chat + artifact), not a modal or separate page:** the PRD's flow (§6, step 5) has Priya reading a generated essay *while* the conversation that produced it is still visible — she needs to compare the two, not lose context by navigating away. This directly satisfies the brief's requirement that artifacts render "beside the chat instead of displaying only raw code or redirecting to another application."

**Why a session sidebar, not a single ongoing thread:** the PRD's return-visit flow (§6, step 6) requires that Priya's sessions persist independently and are revisitable — a sidebar makes that persistence visible rather than implicit.

---

## 3. Key Interaction States

| State | What the user sees | Why it matters |
|---|---|---|
| **Idle / empty session** | Empty thread with a short prompt suggestion (e.g., "Ask about growth or product strategy from Lenny's Podcast") | Avoids a blank, uninviting first impression; sets expectation of what the tool covers |
| **Sending / awaiting response** | User message appears immediately; a lightweight "thinking" indicator on the assistant side | Confirms the message was received before the (potentially slow, especially on local model) response arrives |
| **Grounded answer returned** | Assistant text with inline or below-message citation chips (episode name, clickable to expand source text) | Citations are not an afterthought — they are a first-class visual element, matching Principle 1 |
| **No-match / fallback answer** | Assistant explicitly states the transcripts don't cover this, styled distinctly (e.g., muted tone) from a normal answer | Must be visually distinguishable from a confident answer so the user doesn't mistake caution for content |
| **Essay generation in progress** | Artifact panel opens with a skeleton/loading state, not a blank panel | Signals that generation is a distinct, slower operation from a normal chat reply |
| **Artifact ready** | Rendered Markdown/HTML in the panel, with word count shown for essays (validating the ~1,250-word target from the PRD) | Lets Priya immediately verify the output roughly matches the spec without reading the whole thing first |
| **Provider unavailable (Ollama down / key missing)** | Inline banner explaining the specific failure and what to do (e.g., "Local model unreachable — check Ollama is running") | Matches the resilience requirement in architecture.md §8; avoids a silent hang |
| **Empty retrieval result** | Handled as the "no-match" state above, not as an error | Per architecture.md §4, this is an expected, normal path, not a failure — the UI should not alarm the user unnecessarily |

---

## 4. Responsive Behavior

- **Desktop (primary target):** side-by-side chat and artifact panels, session sidebar visible by default.
- **Narrower viewports (tablet):** artifact panel becomes an overlay/drawer triggered from the chat rather than a fixed side panel; session sidebar collapses to a toggle.
- **Mobile:** single-column view; artifact viewer opens as a full-screen view with a clear "back to chat" action, since side-by-side panels aren't usable at that width.

Given the project timeline (per the PRD's scope decisions), full mobile polish is treated as a lower priority than desktop correctness — this is stated explicitly rather than silently under-built, consistent with the PRD's approach to scope trade-offs.

---

## 5. Accessibility Considerations

- All interactive elements (send button, new session, artifact copy/download) are keyboard-navigable and have visible focus states.
- Citation chips and provider/status indicators use both color and text/icon (not color alone) to convey state, for colorblind accessibility.
- Loading and error states are announced via `aria-live` regions so screen reader users aren't left waiting silently.
- Sufficient color contrast maintained between the "confident answer" and "fallback answer" styling, so the distinction (Principle 1) doesn't rely purely on subtle color shifts.
- The sandboxed artifact iframe (architecture.md §7) is labeled with an appropriate `title` attribute for assistive technology.

---

## 6. Design Decisions Worth Defending

- **Citations are visually inline, not hidden behind a "sources" toggle.** A collapsed/hidden source list would technically satisfy the requirement but would undercut the actual product goal — Priya needs to trust the answer at a glance, not dig for proof.
- **The fallback ("not covered in transcripts") state is deliberately styled differently, not just worded differently.** This makes the distinction robust even if the user skims rather than reads carefully — a real risk in a fast-paced work context.
- **The artifact panel is collapsible rather than always-open.** Most turns in a session are ordinary Q&A, not essay generation; keeping the panel closed by default keeps the interface focused on the primary use case and only expands for the secondary one.
