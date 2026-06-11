# Team44_DESIGN_DOC.md
# TransitFlow — Design Document

**Team ID:** Team44  
**Members:** [Angela's full name], [Kiki's full name], 王若琳  
**Submission Date:** 2026-06-12

---

## Section 1 — ER Diagram

The TransitFlow system models two transit networks — City Metro and National Rail — along with users, bookings, payments, and feedback.

### Entity Relationship Overview

**Core entities and relationships:**

```
national_rail_stations ──< national_rail_schedule_stops >── national_rail_schedules
                                                                      │
metro_stations ──< metro_schedule_stops >── metro_schedules           │
      │                                                               │
metro_station_lines                                                   │
                                                              bookings (FK → users, schedules)
registered_users ──────────────────────────────────────────────── /
      │                                                        payments (FK → bookings)
      └── metro_travel_history                                  feedback (FK → bookings)

seat_layouts ──< bookings
```

**Key design decisions:**
- `national_rail_schedule_stops` is a normalised junction table with a `stop_order` column, enabling correct route direction queries without storing arrays
- `metro_station_lines` is normalised out of `metro_stations` because one station can serve multiple lines
- `metro_travel_history` is separate from `bookings` because metro tap-in records have no seat assignment or advance booking
- `payments` covers both national rail bookings and metro trips via nullable foreign keys

---

## Section 2 — Normalisation Justification

The schema is designed to **Third Normal Form (3NF)**.

### Key normalisation decisions:

**`national_rail_schedule_stops` junction table**
- The original mock data stores `stops_in_order` as a JSON array inside each schedule record
- Storing this as an array column (JSONB) would violate 1NF and make stop-order queries complex
- We extracted stops into a separate table with `schedule_id`, `station_id`, `stop_order`, and `travel_time_from_origin_min`
- This allows efficient SQL joins to find schedules where origin appears before destination

**`metro_station_lines` junction table**
- A metro station can serve multiple lines (e.g. MS01 serves M1 and M2)
- Storing lines as an array in `metro_stations` would violate 1NF
- The junction table with `(station_id, line)` as composite primary key is fully normalised

**Fare rates stored in `national_rail_schedules`**
- The mock data shows fare classes (standard/first) with base and per-stop rates per schedule
- These are functional dependencies of the schedule, so they belong in the schedules table
- Total fare is calculated at query time: `base_fare + per_stop_rate × stops_travelled` — not stored

**`registered_users` password storage**
- Passwords are hashed with argon2 before storage — never stored as plain text
- `secret_answer` is stored in lowercase to enable case-insensitive comparison

---

## Section 3 — Graph Database Design Rationale

### Node Labels

| Label | Properties | Reason |
|-------|-----------|--------|
| `MetroStation` | station_id, name, lines | Represents city metro stops; separate label from rail for network filtering |
| `NationalRailStation` | station_id, name, city | Represents intercity rail stops |

### Relationship Types

| Type | Between | Properties | Reason |
|------|---------|-----------|--------|
| `METRO_LINK` | MetroStation → MetroStation | line, travel_time_min | Encodes direct metro connections for shortest path |
| `RAIL_LINK` | NationalRailStation → NationalRailStation | line, service_type, travel_time_min | Encodes national rail connections; service_type enables express/normal filtering |
| `INTERCHANGE_TO` | MetroStation ↔ NationalRailStation | — | Connects cross-network interchange stations (e.g. MS01 ↔ NR01) |

### Why Neo4j for routing?

Relational databases require recursive CTEs or repeated self-joins to find multi-hop paths — these become expensive as the network grows. Neo4j's native graph traversal algorithms (APOC Dijkstra, BFS) are optimised for this use case. The `INTERCHANGE_TO` relationship enables cross-network journey planning in a single query, which would require complex union queries in SQL.

---

## Section 4 — Vector / RAG Design

### Policy Document Structure

Four policy JSON files are indexed for RAG (Retrieval-Augmented Generation):

| File | Contents |
|------|---------|
| `ticket_types.json` | Ticket type definitions, eligibility, and rules for both networks |
| `refund_policy.json` | Refund windows and percentages by network, ticket type, and fare class |
| `booking_rules.json` | Advance booking windows, seat selection, modification rules, payment methods |
| `travel_policies.json` | Luggage allowances, passenger conduct, accessibility, delay compensation, pets |

### Embedding and Storage

- Policy documents are converted to plain-English text chunks combining title, description, and structured rules
- Each chunk is embedded using the configured LLM provider (Ollama `nomic-embed-text` producing 768-dim vectors, or Gemini `gemini-embedding-001` producing 3072-dim vectors)
- Embeddings are stored in the `policy_documents` table using the `pgvector` extension
- An HNSW index (`vector_cosine_ops`) enables fast approximate nearest-neighbour search

### Query Flow

1. User asks a natural language question (e.g. "Can I get a refund if I cancel tomorrow?")
2. The LLM embeds the question into a vector
3. `query_policy_vector_search` queries `policy_documents` using cosine similarity
4. The top-k most relevant policy chunks are returned to the agent as context
5. The LLM uses this context to generate a grounded, policy-accurate answer

### Design Choice: pgvector over ChromaDB

We chose `pgvector` (PostgreSQL extension) rather than a separate vector database because it keeps all data in one system, simplifies deployment (single Docker container), and allows vector search to be combined with SQL joins in future extensions.

---

## Section 5 — AI Tool Usage Evidence

All three team members used AI coding assistants (Claude) during this project. The following documents our usage patterns:

### How we used AI tools

- **Schema design:** We provided the mock JSON data to Claude and asked it to propose table structures. We reviewed and adjusted the AI output as a team before finalising — for example, we changed the fare storage approach after discussing normalisation trade-offs.
- **Query function implementation:** We pasted the stub function signatures and our agreed schema into Claude, then reviewed every generated function against the rubric criteria (correct return types, use of `_connect()` helper, atomic transactions).
- **Policy document writing:** Claude helped draft the four policy JSON files based on the system description. We reviewed each policy for accuracy and consistency with the booking logic.
- **Debugging:** When functions returned unexpected results during testing, we pasted the error and the relevant schema section into Claude to identify the issue.

### What we verified manually

- All table and column names were checked against the mock data before committing
- The `execute_booking` atomic transaction was tested by deliberately triggering a failure after the booking insert to confirm the rollback worked
- Argon2 password hashing was verified by calling `register_user` and checking the stored hash in pgAdmin

---

## Section 6 — Reflection & Trade-offs

### What worked well

The mock data provided a clear, consistent target for schema design. Having real JSON files meant we could verify our seed scripts produced the exact data structure the query functions expected. Dividing the three databases (PostgreSQL, Neo4j, pgvector) across three team members allowed parallel development with minimal blocking.

### Trade-offs made

**VARCHAR IDs vs SERIAL/UUID**
We chose VARCHAR primary keys (e.g. `"NR01"`, `"MS_SCH01"`) to match the mock data format. This makes the data human-readable and simplifies debugging, but means the application must generate IDs rather than relying on the database. For the generated booking and payment IDs we use a random suffix (`BK-XXXXXX`) which has a small theoretical collision risk that a UUID would eliminate.

**Soft deletes throughout**
All tables use status flags or `is_active` columns instead of physical deletion. This preserves booking history and audit trails, which is important for a transit system. The trade-off is that queries must always filter out inactive records, which adds a small overhead and requires developers to remember the pattern consistently.

**Fare calculation at query time**
Total fares are calculated in Python (`base + per_stop_rate × stops`) rather than stored as a computed column. This avoids stale data if rates change, but means the calculation logic must be consistent across `query_national_rail_fare`, `execute_booking`, and the cancellation refund calculation.

**Metro and national rail in one schema**
Combining both networks in a single PostgreSQL schema means some tables (like `seat_layouts`) only apply to national rail. This is simpler to deploy than a split database but requires careful documentation so developers know which tables are network-specific.
