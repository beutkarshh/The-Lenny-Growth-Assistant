import re
from dataclasses import dataclass

import yaml

# Matches a line that is *only* a turn marker, e.g. "Ada Chen Rekhi (00:00:00):"
# or a same-speaker continuation "(00:01:21):". The transcript text itself
# follows on subsequent lines, up to the next marker.
#
# Timestamp format varies across the corpus: episodes under an hour are
# stamped "MM:SS" (e.g. "Barbra Gago (00:00):"), longer ones "HH:MM:SS".
# The hours group is optional to handle both; missing hours are treated as 0.
TURN_MARKER = re.compile(r"^(?:.+?\s+)?\((?:(\d{1,2}):)?(\d{2}):(\d{2})\):\s*$", re.MULTILINE)

# architecture.md §4 specifies "~500-800 token chunks with slight overlap".
# Approximated in words (~0.75 words per token) rather than pulling in a real
# tokenizer (e.g. tiktoken), which would mean silently depending on a hosted
# OpenAI vocab file just to size chunk boundaries — not worth it for an
# approximate target.
TARGET_WORDS = 450
MAX_WORDS = 600
OVERLAP_WORDS = 60


@dataclass
class Turn:
    timestamp: str  # "HH:MM:SS"
    text: str


def parse_transcript(raw: str) -> tuple[dict, list[Turn]]:
    """Split a transcript.md file into its YAML frontmatter and an ordered
    list of speaker turns, each carrying the timestamp it started at."""
    parts = raw.split("---", 2)
    frontmatter = yaml.safe_load(parts[1]) or {}
    body = parts[2] if len(parts) > 2 else ""

    transcript_start = body.find("## Transcript")
    if transcript_start != -1:
        body = body[transcript_start:]

    markers = list(TURN_MARKER.finditer(body))
    turns = []
    for i, marker in enumerate(markers):
        start = marker.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(body)
        text = body[start:end].strip()
        if text:
            hours = int(marker.group(1)) if marker.group(1) else 0
            minutes, seconds = int(marker.group(2)), int(marker.group(3))
            timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            turns.append(Turn(timestamp=timestamp, text=text))
    return frontmatter, turns


def chunk_turns(turns: list[Turn]) -> list[dict]:
    """Greedily accumulate turns into ~TARGET_WORDS-sized chunks, then add
    textual overlap from the previous chunk's tail for embedding context.

    start_timestamp always reflects the chunk's own new content, not the
    borrowed overlap text — that's what a citation should point to.
    """
    base_groups: list[list[Turn]] = []
    buffer: list[Turn] = []
    word_count = 0

    for turn in turns:
        words_in_turn = len(turn.text.split())
        if buffer and word_count + words_in_turn > MAX_WORDS:
            base_groups.append(buffer)
            buffer, word_count = [], 0
        buffer.append(turn)
        word_count += words_in_turn
        if word_count >= TARGET_WORDS:
            base_groups.append(buffer)
            buffer, word_count = [], 0
    if buffer:
        base_groups.append(buffer)

    chunks = []
    prev_tail = ""
    for i, group in enumerate(base_groups):
        own_text = "\n\n".join(t.text for t in group)
        chunk_text = f"{prev_tail}\n\n{own_text}".strip() if prev_tail else own_text
        chunks.append({
            "chunk_text": chunk_text,
            "chunk_index": i,
            "start_timestamp": group[0].timestamp,
        })
        words = own_text.split()
        prev_tail = " ".join(words[-OVERLAP_WORDS:]) if len(words) > OVERLAP_WORDS else own_text

    return chunks
