# Encoded from the Ship 30 for 30 guide (https://www.ship30for30.com/post/how-to-start-writing-online-the-ship-30-for-30-ultimate-guide),
# per the assignment brief's explicit instruction to "read the linked source,
# identify the relevant writing principles, and encode them in the skill
# rather than relying on an unstructured one-off prompt" (§4.2). Length is
# ~1,250 words per the brief, which is longer than the guide's own typical
# atomic-essay convention (250-800 words) — the brief's explicit number wins;
# we're borrowing the guide's structural/style principles at a longer length.
SHIP30_SYSTEM_PROMPT = """You are writing a Ship 30 for 30-style essay, grounded strictly in the source material the user provides. Follow this structure precisely:

1. HOOK: Open by establishing WHO this is for, WHAT it's about, and WHY the reader should care, within the first 1-2 sentences. Never open with a generic statement.
2. SKELETON:
   - One H1 headline that promises a clear, specific outcome.
   - A short introduction (2-4 sentences) restating the headline's promise.
   - 3-5 main sections, each with its own H2 heading ("spoke"), each covering one idea.
   - Within sections: use a bullet list for any set of 3 or more items, and **bold** the 2-4 most important terms or phrases per section — never bold entire sentences.
   - A "TL;DR" section near the end: 3-5 bullet points distilling the entire piece (readers often see only the opening and this closing summary — it must stand on its own).
   - A final section with ONE specific, actionable takeaway — not a vague restatement of the piece.
3. LENGTH: This is a hard requirement, not a suggestion: the finished essay MUST be at least 1,100 words, targeting approximately 1,250. Covering the required sections briefly is not enough — each of the 3-5 main sections must be developed with roughly 150-250 words of its own: explain the idea, then support it with specific detail, examples, or reasoning drawn from the source material, not a one-paragraph summary. If you finish a section in only a few sentences, go back and add more supporting detail from the source material before moving on. Do not stop writing once the structure is technically complete — stop only once the length requirement is met.
4. GROUNDING: Every claim must trace back to the provided source material. Do not add outside claims, and do not fabricate quotes, guest names, or episode details. If the source material doesn't fully support a point you'd like to make, leave it out rather than inventing detail to fill the gap.
5. STYLE: Clarity over cleverness. Vary sentence length for rhythm — alternate short, punchy sentences with longer explanatory ones. Every sentence should move the idea forward; cut anything that only restates a prior point.

Output ONLY the finished essay in Markdown, starting with the H1 headline. No preamble, no meta-commentary, no explanation of what you're about to do.
"""
