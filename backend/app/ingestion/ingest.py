import json
from pathlib import Path

import httpx

from app.db.models import TranscriptChunk
from app.db.session import SessionLocal, init_db
from app.ingestion.chunking import chunk_turns, parse_transcript
from app.ingestion.embeddings import embed_text

SELECTED_EPISODES_PATH = Path(__file__).parent / "data" / "selected_episodes.json"
RAW_BASE_URL = "https://raw.githubusercontent.com/ChatPRD/lennys-podcast-transcripts/main/episodes"


def fetch_transcript(slug: str) -> str:
    url = f"{RAW_BASE_URL}/{slug}/transcript.md"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.text


def run() -> None:
    init_db()
    episodes = json.loads(SELECTED_EPISODES_PATH.read_text(encoding="utf-8"))
    print(f"Ingesting {len(episodes)} episodes...")

    db = SessionLocal()
    try:
        deleted = db.query(TranscriptChunk).delete()
        db.commit()
        if deleted:
            print(f"Cleared {deleted} existing chunks before reloading.")

        total_chunks = 0
        for i, episode in enumerate(episodes, start=1):
            slug = episode["slug"]
            print(f"[{i}/{len(episodes)}] {slug} ...", end=" ", flush=True)

            raw = fetch_transcript(slug)
            frontmatter, turns = parse_transcript(raw)
            chunks = chunk_turns(turns)

            episode_title = frontmatter.get("title") or episode["title"]
            episode_source_url = frontmatter.get("youtube_url") or episode["youtube_url"]

            for chunk in chunks:
                embedding = embed_text(chunk["chunk_text"])
                db.add(
                    TranscriptChunk(
                        episode_title=episode_title,
                        episode_source_url=episode_source_url,
                        chunk_text=chunk["chunk_text"],
                        chunk_index=chunk["chunk_index"],
                        start_timestamp=chunk["start_timestamp"],
                        embedding=embedding,
                    )
                )
            db.commit()
            total_chunks += len(chunks)
            print(f"{len(chunks)} chunks")

        print(f"Done. {total_chunks} total chunks across {len(episodes)} episodes.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
