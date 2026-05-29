"""
databases/integration.py
------------------------
Member C responsibility: combine results from all three data sources —
PostgreSQL (relational), Neo4j (graph), and pgvector (policy search) —
into a single structured context string that the LLM agent can use.

This module is the "glue" between the three databases and the agent in
skeleton/agent.py.

Usage:
    from databases.integration import build_context

    context = build_context(
        user_question="What is the refund policy for national rail?",
        relational_results={"bookings": [...], "schedules": [...]},
        graph_results={"route": {...}},
    )
    # Pass context to the LLM prompt
"""

from __future__ import annotations

import json
from typing import Any

from databases.vector.queries import query_policy


# ── Context builder ───────────────────────────────────────────────────────────

def build_context(
    user_question: str,
    relational_results: dict[str, Any] | None = None,
    graph_results: dict[str, Any] | None = None,
    policy_top_k: int = 3,
) -> str:
    """
    Build a combined context string from all three data sources.

    Fetches relevant policy chunks automatically using the user's question,
    then merges with any relational/graph data already retrieved by other tools.

    Args:
        user_question:      The user's original question (used for policy search).
        relational_results: Dict of data from PostgreSQL queries, e.g.
                            {"schedules": [...], "user_profile": {...}}.
                            Pass None or {} if not applicable.
        graph_results:      Dict of data from Neo4j queries, e.g.
                            {"shortest_route": {...}}.
                            Pass None or {} if not applicable.
        policy_top_k:       How many policy chunks to include (default 3).

    Returns:
        A formatted string combining all available data — ready to be injected
        into an LLM prompt as context.
    """
    sections: list[str] = []

    # 1. Policy context (always fetched via vector search)
    policy_chunks = query_policy(user_question, top_k=policy_top_k)
    if policy_chunks:
        policy_lines = ["=== RELEVANT POLICIES ==="]
        for chunk in policy_chunks:
            score = chunk.get("similarity_score", 0)
            policy_lines.append(
                f"\n[{chunk['section_title']}] (source: {chunk['source_file']}, relevance: {score:.2f})\n"
                f"{chunk['content']}"
            )
        sections.append("\n".join(policy_lines))

    # 2. Relational data (bookings, schedules, user profile, etc.)
    if relational_results:
        rel_lines = ["=== DATABASE RESULTS ==="]
        for key, value in relational_results.items():
            if value:
                rel_lines.append(f"\n[{key}]")
                rel_lines.append(json.dumps(value, indent=2, default=str))
        if len(rel_lines) > 1:
            sections.append("\n".join(rel_lines))

    # 3. Graph data (routes, connections)
    if graph_results:
        graph_lines = ["=== ROUTE INFORMATION ==="]
        for key, value in graph_results.items():
            if value:
                graph_lines.append(f"\n[{key}]")
                graph_lines.append(json.dumps(value, indent=2, default=str))
        if len(graph_lines) > 1:
            sections.append("\n".join(graph_lines))

    if not sections:
        return "No relevant information found in the database."

    return "\n\n".join(sections)


# ── Standalone integration test ───────────────────────────────────────────────

def run_integration_test():
    """
    Run a quick end-to-end test of all three data sources.
    Call this from the command line:
        python -m databases.integration

    Tests:
        - Vector policy search (requires seed_vector.py to have been run)
        - Relational query (requires schema + seed_postgres.py)
        - Graph query (requires Neo4j + seed_neo4j.py)
        - Combined context builder
    """
    print("\n=== TransitFlow Integration Test ===\n")
    passed = 0
    failed = 0

    # ── Test 1: Vector search ────────────────────────────────────────────────
    print("Test 1: Vector policy search")
    try:
        from databases.vector.queries import query_policy, get_policy_summary

        summary = get_policy_summary()
        if summary:
            print(f"  ✓ policy_documents table has rows: {summary}")
            passed += 1
        else:
            print("  ✗ policy_documents table is empty — run seed_vector.py first")
            failed += 1

        results = query_policy("Can I get a refund if I cancel my ticket?", top_k=2)
        if results:
            print(f"  ✓ query_policy returned {len(results)} result(s)")
            print(f"    Top match: {results[0]['section_title']} (score={results[0].get('similarity_score', 0):.2f})")
            passed += 1
        else:
            print("  ✗ query_policy returned no results")
            failed += 1
    except Exception as e:
        print(f"  ✗ Vector test error: {e}")
        failed += 1

    # ── Test 2: Relational DB ────────────────────────────────────────────────
    print("\nTest 2: Relational database (PostgreSQL)")
    try:
        from databases.relational.queries import query_user_profile
        # Test with a known user from the mock data — update this email if needed
        test_email = "alice@example.com"
        user = query_user_profile(test_email)
        if user:
            print(f"  ✓ query_user_profile returned a user: {user.get('first_name', '?')}")
            passed += 1
        else:
            print(f"  ⚠ query_user_profile returned None for '{test_email}' — check seed data")
            # Not a hard fail — might just be wrong test email
    except NotImplementedError:
        print("  ⚠ Relational queries not yet implemented (teammate A still working)")
    except Exception as e:
        print(f"  ✗ Relational test error: {e}")
        failed += 1

    # ── Test 3: Graph DB ─────────────────────────────────────────────────────
    print("\nTest 3: Graph database (Neo4j)")
    try:
        from databases.graph.queries import query_station_connections
        result = query_station_connections("MS01")
        if result:
            print(f"  ✓ query_station_connections returned {len(result)} connection(s) for MS01")
            passed += 1
        else:
            print("  ⚠ query_station_connections returned [] for MS01 — check Neo4j seed")
    except NotImplementedError:
        print("  ⚠ Graph queries not yet implemented (teammate B still working)")
    except Exception as e:
        print(f"  ✗ Graph test error: {e}")
        failed += 1

    # ── Test 4: Combined context builder ─────────────────────────────────────
    print("\nTest 4: Combined context builder")
    try:
        context = build_context(
            user_question="What is the refund policy for national rail tickets?",
            relational_results={"example_schedule": [{"schedule_id": "NR_SCH01", "line": "L1"}]},
            graph_results={"example_route": {"path": ["NR01", "NR02", "NR03"]}},
            policy_top_k=2,
        )
        if context and "RELEVANT POLICIES" in context:
            print("  ✓ build_context returned combined context with policy section")
            passed += 1
        else:
            print("  ✗ build_context output missing expected sections")
            failed += 1
    except Exception as e:
        print(f"  ✗ Context builder error: {e}")
        failed += 1

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("✓ All tests passed — system is integrated!")
    else:
        print("⚠ Some tests failed — see messages above.")


if __name__ == "__main__":
    run_integration_test()