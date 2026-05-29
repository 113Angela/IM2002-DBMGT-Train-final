"""
seed_vector.py
--------------
Member C responsibility: load all policy documents from train-mock-data/,
convert each chunk to a vector embedding (Google Gemini text-embedding-004),
and store in the `policy_documents` table in PostgreSQL via pgvector.

Run once (or re-run to refresh):
    python skeleton/seed_vector.py

Requirements (add to requirements.txt):
    google-generativeai>=0.5.0
    psycopg2-binary
    python-dotenv
"""

import json
import os
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# ── Load .env ──────────────────────────────────────────────────────────────────
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DATABASE_URL   = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/transitflow")
MOCK_DATA_DIR  = Path(__file__).parent.parent / "train-mock-data"

# ── Google Generative AI setup ─────────────────────────────────────────────────
try:
    import google.generativeai as genai
    genai.configure(api_key=GOOGLE_API_KEY)
    EMBEDDING_MODEL = "models/text-embedding-004"
    EMBEDDING_DIM   = 768       # text-embedding-004 outputs 768-dim vectors
except ImportError:
    print("ERROR: google-generativeai not installed. Run: pip install google-generativeai")
    sys.exit(1)


# ── DB helpers ─────────────────────────────────────────────────────────────────
def _connect():
    """Return a psycopg2 connection using DATABASE_URL from .env."""
    return psycopg2.connect(DATABASE_URL)


def create_policy_table():
    """
    Create the policy_documents table with a pgvector column.
    Safe to call multiple times (uses IF NOT EXISTS).
    """
    ddl = """
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE IF NOT EXISTS policy_documents (
            id            SERIAL PRIMARY KEY,
            source_file   TEXT NOT NULL,          -- e.g. 'refund_policy.json'
            section_title TEXT NOT NULL,           -- human-readable label
            content       TEXT NOT NULL,           -- the raw policy text
            embedding     vector(%s)               -- pgvector column
        );

        -- Index for fast approximate nearest-neighbour search
        CREATE INDEX IF NOT EXISTS idx_policy_embedding
            ON policy_documents
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 10);
    """ % EMBEDDING_DIM

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
    print("✓ policy_documents table ready.")


def clear_policy_table():
    """Delete all existing rows (so re-seeding is idempotent)."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM policy_documents;")
        conn.commit()
    print("✓ Cleared old policy rows.")


# ── Embedding ─────────────────────────────────────────────────────────────────
def embed_text(text: str) -> list[float]:
    """
    Call Gemini text-embedding-004 and return a 768-dim float list.
    Retries once on rate-limit (429) with a 5-second pause.

    Args:
        text: The string to embed.

    Returns:
        List of 768 floats.
    """
    for attempt in range(2):
        try:
            result = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=text,
                task_type="retrieval_document",
            )
            return result["embedding"]
        except Exception as e:
            if "429" in str(e) and attempt == 0:
                print("  Rate limited — waiting 5 s …")
                time.sleep(5)
            else:
                raise
    raise RuntimeError("Embedding failed after retry.")


# ── Policy chunkers ───────────────────────────────────────────────────────────
# Each function reads one JSON file and returns a list of dicts:
#   { "source_file": str, "section_title": str, "content": str }
#
# Keep chunks small enough to be informative but not so large the embedding
# loses focus.  150–400 words per chunk is a good rule of thumb.


def chunk_ticket_types(data: list[dict], source_file: str) -> list[dict]:
    """
    ticket_types.json → one chunk per ticket type.
    """
    chunks = []
    for ticket in data:
        name    = ticket.get("ticket_type_name", ticket.get("type_id", "Unknown"))
        lines   = [f"Ticket type: {name}"]
        for k, v in ticket.items():
            if k not in ("ticket_type_name", "type_id"):
                lines.append(f"  {k}: {v}")
        chunks.append({
            "source_file":   source_file,
            "section_title": f"Ticket Type — {name}",
            "content":       "\n".join(lines),
        })
    return chunks


def chunk_refund_policy(data: dict | list, source_file: str) -> list[dict]:
    """
    refund_policy.json → one chunk per network/ticket-type combination.
    Handles both list and dict formats.
    """
    chunks = []

    # Normalise: might be a top-level dict with 'national_rail' and 'metro' keys
    # or a flat list.
    if isinstance(data, dict):
        entries = []
        for network, items in data.items():
            if isinstance(items, list):
                for item in items:
                    item.setdefault("network", network)
                    entries.append(item)
            else:
                entries.append({"network": network, **items})
    else:
        entries = data

    for entry in entries:
        network    = entry.get("network", "")
        ticket_key = entry.get("ticket_type", entry.get("type", ""))
        lines      = [f"Refund policy for {network} — {ticket_key}:"]
        for k, v in entry.items():
            if k not in ("network",):
                lines.append(f"  {k}: {v}")
        chunks.append({
            "source_file":   source_file,
            "section_title": f"Refund Policy — {network} {ticket_key}".strip(),
            "content":       "\n".join(lines),
        })
    return chunks


def chunk_booking_rules(data: dict | list, source_file: str) -> list[dict]:
    """
    booking_rules.json → one chunk per rule section or network.
    """
    chunks = []

    if isinstance(data, dict):
        for section_key, section_val in data.items():
            if isinstance(section_val, dict):
                lines = [f"Booking rules — {section_key}:"]
                for k, v in section_val.items():
                    lines.append(f"  {k}: {v}")
                chunks.append({
                    "source_file":   source_file,
                    "section_title": f"Booking Rules — {section_key}",
                    "content":       "\n".join(lines),
                })
            elif isinstance(section_val, list):
                for i, item in enumerate(section_val):
                    if isinstance(item, dict):
                        lines = [f"Booking rule ({section_key}, #{i+1}):"]
                        for k, v in item.items():
                            lines.append(f"  {k}: {v}")
                        chunks.append({
                            "source_file":   source_file,
                            "section_title": f"Booking Rules — {section_key} #{i+1}",
                            "content":       "\n".join(lines),
                        })
                    else:
                        chunks.append({
                            "source_file":   source_file,
                            "section_title": f"Booking Rules — {section_key}",
                            "content":       f"{section_key}: {item}",
                        })
            else:
                chunks.append({
                    "source_file":   source_file,
                    "section_title": f"Booking Rules — {section_key}",
                    "content":       f"{section_key}: {section_val}",
                })
    elif isinstance(data, list):
        for i, item in enumerate(data):
            title = item.get("rule_name", item.get("type", f"Rule {i+1}"))
            lines = [f"Booking rule: {title}"]
            for k, v in item.items():
                lines.append(f"  {k}: {v}")
            chunks.append({
                "source_file":   source_file,
                "section_title": f"Booking Rule — {title}",
                "content":       "\n".join(lines),
            })

    return chunks


def chunk_travel_policies(data: dict | list, source_file: str) -> list[dict]:
    """
    travel_policies.json → one chunk per policy section.
    """
    chunks = []

    if isinstance(data, dict):
        for section_key, section_val in data.items():
            if isinstance(section_val, list):
                content = f"{section_key}:\n" + "\n".join(
                    f"  - {item}" if not isinstance(item, dict)
                    else "\n".join(f"  {k}: {v}" for k, v in item.items())
                    for item in section_val
                )
            elif isinstance(section_val, dict):
                content = f"{section_key}:\n" + "\n".join(
                    f"  {k}: {v}" for k, v in section_val.items()
                )
            else:
                content = f"{section_key}: {section_val}"

            chunks.append({
                "source_file":   source_file,
                "section_title": f"Travel Policy — {section_key}",
                "content":       content,
            })
    elif isinstance(data, list):
        for i, item in enumerate(data):
            title = item.get("policy_name", item.get("category", f"Policy {i+1}"))
            lines = [f"Travel policy: {title}"]
            for k, v in item.items():
                lines.append(f"  {k}: {v}")
            chunks.append({
                "source_file":   source_file,
                "section_title": f"Travel Policy — {title}",
                "content":       "\n".join(lines),
            })

    return chunks


# ── Main orchestration ────────────────────────────────────────────────────────
POLICY_FILES = {
    "ticket_types.json":   chunk_ticket_types,
    "refund_policy.json":  chunk_refund_policy,
    "booking_rules.json":  chunk_booking_rules,
    "travel_policies.json": chunk_travel_policies,
}


def load_all_chunks() -> list[dict]:
    """
    Read all four policy JSON files and return a flat list of text chunks.

    Returns:
        List of dicts, each with keys: source_file, section_title, content.
    """
    all_chunks = []
    for filename, chunker_fn in POLICY_FILES.items():
        filepath = MOCK_DATA_DIR / filename
        if not filepath.exists():
            print(f"  WARNING: {filepath} not found — skipping.")
            continue
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        chunks = chunker_fn(data, filename)
        print(f"  {filename}: {len(chunks)} chunks")
        all_chunks.extend(chunks)
    return all_chunks


def insert_chunk(cur, chunk: dict, embedding: list[float]):
    """
    Insert a single policy chunk with its embedding into policy_documents.

    Args:
        cur:       psycopg2 cursor with RealDictCursor not required here.
        chunk:     Dict with source_file, section_title, content.
        embedding: 768-dim float list.
    """
    cur.execute(
        """
        INSERT INTO policy_documents (source_file, section_title, content, embedding)
        VALUES (%s, %s, %s, %s::vector)
        """,
        (chunk["source_file"], chunk["section_title"], chunk["content"], str(embedding)),
    )


def seed():
    """
    Full seeding pipeline:
      1. Create table
      2. Clear old rows
      3. Load chunks from JSON
      4. Embed each chunk
      5. Insert into DB
    """
    print("\n=== TransitFlow — Policy Vector Seeder ===\n")

    # 1. Setup
    create_policy_table()
    clear_policy_table()

    # 2. Load chunks
    print("\nLoading policy chunks …")
    chunks = load_all_chunks()
    print(f"Total: {len(chunks)} chunks to embed and store.\n")

    if not chunks:
        print("No chunks found. Check that train-mock-data/ folder exists.")
        sys.exit(1)

    # 3. Embed + insert
    with _connect() as conn:
        with conn.cursor() as cur:
            for i, chunk in enumerate(chunks):
                print(f"  [{i+1}/{len(chunks)}] Embedding: {chunk['section_title'][:60]}")
                try:
                    embedding = embed_text(chunk["content"])
                    insert_chunk(cur, chunk, embedding)
                except Exception as e:
                    print(f"    ERROR embedding chunk — skipping: {e}")
                    continue
                # Small pause to stay within free-tier rate limits
                time.sleep(0.3)
        conn.commit()

    print(f"\n✓ Done! {len(chunks)} policy documents stored in policy_documents table.")


if __name__ == "__main__":
    seed()