"""
databases/vector/queries.py
---------------------------
Member C responsibility: semantic search over policy documents stored in pgvector.

Usage (after seed_vector.py has been run):
    from databases.vector.queries import query_policy, query_policy_by_category

All functions follow the same pattern as the relational queries:
  - Use _connect() helper
  - Return list[dict] or Optional[dict]
  - Never raise for "not found" — return [] or None
"""

import os
from typing import Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DATABASE_URL   = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/transitflow")
EMBEDDING_MODEL = "models/text-embedding-004"


# ── Connection helper ─────────────────────────────────────────────────────────
def _connect():
    """Return a psycopg2 connection using DATABASE_URL from .env."""
    return psycopg2.connect(DATABASE_URL)


# ── Embedding helper ──────────────────────────────────────────────────────────
def _embed_query(text: str) -> list[float]:
    """
    Embed a user question using Gemini text-embedding-004.
    Uses task_type='retrieval_query' (vs 'retrieval_document' used at index time).

    Args:
        text: The user's natural language question.

    Returns:
        768-dim float list.
    """
    import google.generativeai as genai
    genai.configure(api_key=GOOGLE_API_KEY)
    result = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=text,
        task_type="retrieval_query",
    )
    return result["embedding"]


# ── Query functions ───────────────────────────────────────────────────────────

def query_policy(question: str, top_k: int = 5) -> list[dict]:
    """
    Semantic search: find the most relevant policy chunks for a user question.

    Embeds the question and performs a cosine-similarity search against all
    policy_documents embeddings. Returns the top_k closest results.

    Args:
        question: Natural language question, e.g. "Can I get a refund on a metro ticket?"
        top_k:    Number of results to return (default 5).

    Returns:
        List of dicts with keys:
            id, source_file, section_title, content, similarity_score
        Ordered by descending similarity.
        Returns [] if no documents are found or on DB error.
    """
    try:
        embedding = _embed_query(question)
    except Exception:
        return []

    sql = """
        SELECT
            id,
            source_file,
            section_title,
            content,
            1 - (embedding <=> %s::vector) AS similarity_score
        FROM policy_documents
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """
    embedding_str = str(embedding)

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (embedding_str, embedding_str, top_k))
            return [dict(row) for row in cur.fetchall()]


def query_policy_by_category(category: str) -> list[dict]:
    """
    Return all policy chunks from a specific source file (category).

    Useful when the agent wants to dump all rules for a particular topic
    without doing a semantic search (e.g. show all refund policies).

    Args:
        category: One of 'ticket_types.json', 'refund_policy.json',
                  'booking_rules.json', 'travel_policies.json'.

    Returns:
        List of dicts with keys: id, source_file, section_title, content.
        Returns [] if no documents found for that category.
    """
    sql = """
        SELECT id, source_file, section_title, content
        FROM policy_documents
        WHERE source_file = %s
        ORDER BY id;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (category,))
            return [dict(row) for row in cur.fetchall()]


def query_policy_by_title(keyword: str) -> list[dict]:
    """
    Simple keyword search on section_title (case-insensitive ILIKE).
    Useful as a fallback when no embedding is available.

    Args:
        keyword: Search term, e.g. "refund" or "luggage".

    Returns:
        List of dicts with keys: id, source_file, section_title, content.
        Returns [] if nothing matches.
    """
    sql = """
        SELECT id, source_file, section_title, content
        FROM policy_documents
        WHERE section_title ILIKE %s
        ORDER BY source_file, id;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (f"%{keyword}%",))
            return [dict(row) for row in cur.fetchall()]


def get_policy_summary() -> dict:
    """
    Return a count of policy documents per source file.
    Useful for debugging after seeding.

    Returns:
        Dict mapping source_file name to row count,
        e.g. {"refund_policy.json": 8, "ticket_types.json": 4, ...}
        Returns {} on error.
    """
    sql = """
        SELECT source_file, COUNT(*) AS count
        FROM policy_documents
        GROUP BY source_file
        ORDER BY source_file;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return {row["source_file"]: row["count"] for row in rows}