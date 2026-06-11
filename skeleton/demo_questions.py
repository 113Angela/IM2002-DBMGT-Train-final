"""
demo_questions.py
-----------------
Member C responsibility: design demo questions that showcase all three
database systems working together.

Run this before your demo to verify each question works:
    python demo_questions.py

Each question is mapped to:
  - Which database(s) it exercises
  - The expected query path
  - A sample expected output format
"""

DEMO_QUESTIONS = [
    # ── Policy / Vector Search questions ─────────────────────────────────────
    {
        "id": "Q1",
        "category": "Policy — Refund",
        "question": "Can I get a refund if I cancel my national rail ticket on the day of travel?",
        "exercises": ["vector_search"],
        "why": "Tests semantic similarity: 'cancel on day of travel' should match refund_policy.json chunks",
    },
    {
        "id": "Q2",
        "category": "Policy — Ticket Types",
        "question": "What is the difference between a single and a return ticket?",
        "exercises": ["vector_search"],
        "why": "Tests ticket_types.json retrieval — two different ticket types in one question",
    },
    {
        "id": "Q3",
        "category": "Policy — Booking Rules",
        "question": "How far in advance can I book a national rail seat?",
        "exercises": ["vector_search"],
        "why": "Tests booking_rules.json — advance booking window rule",
    },
    {
        "id": "Q4",
        "category": "Policy — Travel Rules",
        "question": "What luggage am I allowed to bring on the metro?",
        "exercises": ["vector_search"],
        "why": "Tests travel_policies.json — luggage allowance section",
    },

    # ── Relational DB questions ───────────────────────────────────────────────
    {
        "id": "Q5",
        "category": "Booking",
        "question": "Show me my upcoming bookings.",
        "exercises": ["relational"],
        "why": "Calls query_user_bookings — demonstrates PostgreSQL integration with logged-in user",
    },
    {
        "id": "Q6",
        "category": "Schedule",
        "question": "What trains are available from Central Square to Riverside tomorrow?",
        "exercises": ["relational"],
        "why": "Calls query_national_rail_availability with origin/destination/date",
    },
    {
        "id": "Q7",
        "category": "Fare",
        "question": "How much does a first-class ticket cost from NR01 to NR05?",
        "exercises": ["relational"],
        "why": "Calls query_national_rail_fare — fare calculation with fare_class and stops",
    },

    # ── Graph / Route questions ───────────────────────────────────────────────
    {
        "id": "Q8",
        "category": "Route",
        "question": "What is the fastest route from MS01 to MS15?",
        "exercises": ["graph"],
        "why": "Calls query_shortest_route — Neo4j Dijkstra/shortest path algorithm",
    },
    {
        "id": "Q9",
        "category": "Route",
        "question": "What stations are directly connected to Central Square?",
        "exercises": ["graph"],
        "why": "Calls query_station_connections — shows direct Neo4j neighbourhood query",
    },

    # ── Multi-source questions (best for demo climax!) ────────────────────────
    {
        "id": "Q10",
        "category": "Multi-source",
        "question": "I want to travel from MS01 to NR05. What is the cheapest route and what is the refund policy if I need to cancel?",
        "exercises": ["graph", "relational", "vector_search"],
        "why": "SHOWCASE QUESTION: triggers all three databases. Route from Neo4j, fare from PostgreSQL, refund policy from pgvector.",
    },
    {
        "id": "Q11",
        "category": "Multi-source",
        "question": "What seat classes are available on tomorrow's train from NR01 to NR03, and what is the cancellation policy?",
        "exercises": ["relational", "vector_search"],
        "why": "Combines seat availability (PostgreSQL) with cancellation rules (pgvector)",
    },
]


def print_demo_script():
    """Print a formatted demo script for the presentation."""
    print("\n" + "="*60)
    print("  TransitFlow — Demo Questions (Member C)")
    print("="*60)

    categories = {}
    for q in DEMO_QUESTIONS:
        cat = q["category"].split("—")[0].strip()
        categories.setdefault(cat, []).append(q)

    for cat, questions in categories.items():
        print(f"\n── {cat.upper()} ──")
        for q in questions:
            systems = " + ".join(q["exercises"])
            print(f"\n  {q['id']}. [{systems}]")
            print(f"  Q: \"{q['question']}\"")
            print(f"  → {q['why']}")

    print("\n" + "="*60)
    print("  RECOMMENDED DEMO ORDER")
    print("="*60)
    print("""
  1. Start simple:  Q1  — policy question (vector search only)
  2. Show DB:       Q6  — schedule search (relational only)
  3. Show routes:   Q8  — fastest route (graph only)
  4. CLIMAX:        Q10 — multi-source question (all three!)
  5. Optional:      Q5  — personal bookings (logged-in user)
  """)


def run_demo_test():
    """
    Quick test: run each demo question through the vector search
    and print the top result. Use this to verify before presenting.
    """
    from databases.vector.queries import query_policy

    print("\n=== Pre-Demo Vector Search Test ===\n")
    for q in DEMO_QUESTIONS:
        if "vector_search" not in q["exercises"]:
            continue
        results = query_policy(q["question"], top_k=1)
        if results:
            top = results[0]
            print(f"  {q['id']}: ✓ Top match: \"{top['section_title']}\" "
                  f"(score={top.get('similarity_score', 0):.2f})")
        else:
            print(f"  {q['id']}: ✗ No results for: \"{q['question'][:50]}...\"")


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        run_demo_test()
    else:
        print_demo_script() 