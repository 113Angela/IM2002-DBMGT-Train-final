# Work Allocation Report — Team44

> **Instructions:** Complete this document as a team before or alongside your final submission.
> Submit one copy per team via EEClass. This document is shared with all markers.

---

## 1. Team Members

| Full Name | Student ID | GitHub Username | Email                         |
| --------- | ---------- | --------------- | ----------------------------- |
| 梁瑋文    | 113403506  | 113Angela       | angela.ww.liang@gmail.com     |
| 蘇晏婷    | 113403006  | kiisu950626     | kikisu950626@gmail.com        |
| 王若琳    | 1134034    | michellewm20    | michelleaurelwangsa@gmail.com |

---

## 2. Task Ownership

### Code Repository

| Task                                                                                                                                                         | Primary Owner         | Supporting Member(s)  | Notes                                                                                        |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------- | --------------------- | -------------------------------------------------------------------------------------------- |
| **Task 1** — Relational schema design (`schema.sql`)                                                                                                         |蘇晏婷  | 王若琳 (michellewm20)               | Schema designed based on all mock data JSON files                                            |
| **Task 2a** — Core availability & fare queries (`query_national_rail_availability`, `query_metro_schedules`, `query_national_rail_fare`, `query_metro_fare`) | 王若琳 (michellewm20) | —                     | Implemented with stop-order join logic                                                       |
| **Task 2b** — Seat & user queries (`query_available_seats`, `query_user_profile`, `query_user_bookings`, `query_payment_info`)                               | 王若琳 (michellewm20) | —                     | Covers both national rail and metro history                                                  |
| **Task 2c** — Write operations (`execute_booking`, `execute_cancellation`)                                                                                   | 王若琳 (michellewm20) | —                     | Atomic transactions; refund policy applied                                                   |
| **Task 2d** — Authentication queries (`login_user`, `register_user`, `get_user_secret_question`, `verify_secret_answer`, `update_password`)                  | 王若琳 (michellewm20) | —                     | Argon2 password hashing used throughout                                                      |
| **Task 3** — PostgreSQL seeding (`seed_postgres.py`)                                                                                                         | 蘇晏婷                | 王若琳 (michellewm20) | Idempotent seeding with ON CONFLICT DO NOTHING                                               |
| **Task 4** — Neo4j graph design & seeding (`seed_neo4j.py`, `seed.cypher`)                                                                                   | 梁瑋文                | —                     | MetroStation, NationalRailStation nodes; METRO_LINK, RAIL_LINK, INTERCHANGE_TO relationships |
| **Task 5** — Neo4j query functions (`graph/queries.py`)                                                                                                      | 梁瑋文                | —                     | Shortest path, cheapest route, interchange path, delay ripple                                |
| **Task 6** _(if attempted)_ — Optional extension                                                                                                             | —                     | —                     | Not attempted                                                                                |

### Design Document

| Section                                     | Primary Author | Supporting Member(s) | Notes                                 |
| ------------------------------------------- | -------------- | -------------------- | ------------------------------------- |
| Section 1 — ER Diagram                      | 梁瑋文         | —                    | Designed using ERD tools              |
| Section 2 — Normalisation Justification     | 王若琳         | —                    | Based on schema design decisions      |
| Section 3 — Graph Database Design Rationale | 梁瑋文         | —                    | Neo4j node/relationship design        |
| Section 4 — Vector / RAG Design             | 王若琳         | —                    | ChromaDB + policy document indexing   |
| Section 5 — AI Tool Usage Evidence          | All members    | —                    | Each member documented their AI usage |
| Section 6 — Reflection & Trade-offs         | All members    | —                    | Collaborative reflection              |

---

## 3. Estimated Contribution Percentages

| Member    | Estimated % | Brief justification                                                                         |
| --------- | ----------- | ------------------------------------------------------------------------------------------- |
| 梁瑋文    | 34%         | ERD design, Neo4j graph design, Neo4j query functions, graph seeding                        |
| 蘇晏婷    | 33%         | PostgreSQL seeding, data loading, schema support                                            |
| 王若琳    | 33%         | Relational schema, all SQL query functions, vector search, policy documents, authentication |
| **Total** | **100%**    |                                                                                             |

---

## 4. Mid-Project Changes

| Change        | Original plan              | Revised plan        | Reason                                              |
| ------------- | -------------------------- | ------------------- | --------------------------------------------------- |
| Schema design | Originally assigned 蘇晏婷 | Taken over (王若琳) | Needed to ensure compatibility with query functions |

---

## 5. Team Declaration

We confirm that this work allocation accurately reflects how responsibilities were divided within our team.

| Name | Student ID  
| 梁瑋文 | 113403506  
| 蘇晏婷 | 113403006  
| 王若琳 | 113403049
