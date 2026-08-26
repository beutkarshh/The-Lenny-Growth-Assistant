from app.ingestion.chunking import chunk_turns, parse_transcript

SAMPLE_HHMMSS = """---
guest: Test Guest
title: A Test Episode
youtube_url: https://www.youtube.com/watch?v=abc123
video_id: abc123
---

# A Test Episode

## Transcript

Test Guest (00:00:00):
This is the first turn of the conversation, said by the guest.

Lenny (00:00:36):
This is Lenny's reply, continuing the conversation.

(00:01:21):
This is a same-speaker continuation with no name repeated.
"""

# architecture.md §4: source timestamps vary between MM:SS (episodes under an
# hour) and HH:MM:SS (longer episodes) — chunking.py must normalize both.
SAMPLE_MMSS = """---
guest: Short Guest
title: A Short Episode
youtube_url: https://www.youtube.com/watch?v=xyz789
video_id: xyz789
---

## Transcript

Short Guest (00:00):
Short episodes use MM:SS instead of HH:MM:SS.

Lenny (00:05):
This turn is five seconds in.
"""


def test_parse_transcript_extracts_frontmatter():
    frontmatter, _ = parse_transcript(SAMPLE_HHMMSS)
    assert frontmatter["guest"] == "Test Guest"
    assert frontmatter["youtube_url"] == "https://www.youtube.com/watch?v=abc123"


def test_parse_transcript_splits_turns_hhmmss():
    _, turns = parse_transcript(SAMPLE_HHMMSS)
    assert len(turns) == 3
    assert turns[0].timestamp == "00:00:00"
    assert "first turn" in turns[0].text
    assert turns[1].timestamp == "00:00:36"
    assert turns[2].timestamp == "00:01:21"
    assert "continuation" in turns[2].text


def test_parse_transcript_normalizes_mmss_to_hhmmss():
    """Regression test for a real Phase 4 bug: 8 of 54 ingested episodes
    silently produced zero chunks because the original regex only matched
    HH:MM:SS, not MM:SS (see agent-transcripts/README.md)."""
    _, turns = parse_transcript(SAMPLE_MMSS)
    assert len(turns) == 2
    assert turns[0].timestamp == "00:00:00"
    assert turns[1].timestamp == "00:00:05"


def test_chunk_turns_preserves_start_timestamp_of_first_turn():
    _, turns = parse_transcript(SAMPLE_HHMMSS)
    chunks = chunk_turns(turns)
    assert len(chunks) == 1
    assert chunks[0]["start_timestamp"] == "00:00:00"
    assert chunks[0]["chunk_index"] == 0


def test_chunk_turns_splits_on_word_budget():
    # Build enough turns to force at least two chunks (MAX_WORDS=600).
    long_text = " ".join(["word"] * 400)
    turns_source = "\n\n".join(f"Guest ({i:02d}:00:00):\n{long_text}" for i in range(4))
    transcript = f"---\nguest: G\ntitle: T\nyoutube_url: https://x\n---\n\n## Transcript\n\n{turns_source}"
    _, turns = parse_transcript(transcript)
    chunks = chunk_turns(turns)
    assert len(chunks) > 1
    # Each chunk's own new content should roughly respect the target/max
    # word budget (allowing for the prepended overlap tail).
    for chunk in chunks:
        assert len(chunk["chunk_text"].split()) < 900
