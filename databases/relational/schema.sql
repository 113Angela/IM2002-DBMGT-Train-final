-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
--
--  TWO ROLES:
--    1. Relational  → dual-network transit data you design below
--    2. Vector      → policy documents for RAG (provided — do not modify)
-- ============================================================

-- ============================================================
--  STUDENT TASK — Design and create your relational tables here
-- ============================================================

-- ==========================================
-- 1. USERS & CREDENTIALS
-- ==========================================

-- PK Strategy:
-- We chose SERIAL as the internal primary key because it is compact,
-- database-generated, and more efficient for indexing and joins than VARCHAR.
-- The original JSON user_id is preserved as a UNIQUE external identifier
-- for stable seeding, debugging, and cross-system references.
CREATE TABLE registered_users (
    id SERIAL PRIMARY KEY,
    user_id varchar UNIQUE NOT NULL,
    full_name varchar NOT NULL,
    email varchar UNIQUE NOT NULL,
    phone varchar,
    date_of_birth date,
    secret_question varchar,
    secret_answer_hash text,
    registered_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    is_active boolean DEFAULT true
);

-- PK Strategy: credential_id serves as a unique identifier for each credential record.
-- Delete Strategy: ON DELETE CASCADE. Login credentials cannot exist without the user. If a user is deleted, their credentials must be removed.
-- PK Strategy:
-- We chose SERIAL as the internal primary key. The JSON-derived credential_id
-- is preserved as a UNIQUE external identifier for idempotent seeding.
CREATE TABLE user_credentials (
    id SERIAL PRIMARY KEY,
    credential_id varchar UNIQUE NOT NULL,
    user_id varchar UNIQUE REFERENCES registered_users(user_id) ON DELETE CASCADE,
    password_hash text NOT NULL,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    last_login_at timestamptz
);


-- ==========================================
-- 2. METRO NETWORK
-- ==========================================

-- PK Strategy: station_id uses varchar to match the JSON data exactly (e.g., 'MS01').
-- PK Strategy:
-- We chose SERIAL as the internal primary key for database efficiency.
-- The original JSON station_id is kept as a UNIQUE external identifier because
-- station codes such as MS01 are used in mock data, seeding, and graph references.
CREATE TABLE metro_stations (
    id SERIAL PRIMARY KEY,
    station_id varchar UNIQUE NOT NULL,
    name varchar NOT NULL,
    is_interchange_metro boolean DEFAULT false,
    is_interchange_national_rail boolean DEFAULT false,
    interchange_national_rail_station_id varchar
);

-- PK Strategy: Composite key (station_id, line) prevents duplicate line entries for a single station.
-- Delete Strategy: ON DELETE CASCADE. If a station is removed, its line associations are meaningless and should be deleted.
CREATE TABLE metro_station_lines (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key for consistency across tables.
    -- The pair (station_id, line) remains UNIQUE to prevent duplicate mappings.
    id SERIAL PRIMARY KEY,
    station_id varchar REFERENCES metro_stations(station_id) ON DELETE CASCADE,
    line varchar NOT NULL,
    UNIQUE (station_id, line)
);

-- PK Strategy: Composite key (from_station_id, to_station_id, line) ensures a unique directional link on a specific line.
-- Delete Strategy: ON DELETE CASCADE. If either station is deleted, the adjacency link must be destroyed to maintain graph integrity.
CREATE TABLE metro_adjacent_stations (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key. The directional station pair
    -- and line are kept UNIQUE to preserve the natural network constraint.
    id SERIAL PRIMARY KEY,
    from_station_id varchar REFERENCES metro_stations(station_id) ON DELETE CASCADE,
    to_station_id varchar REFERENCES metro_stations(station_id) ON DELETE CASCADE,
    line varchar NOT NULL,
    travel_time_min int,
    UNIQUE (from_station_id, to_station_id, line)
);

-- ==========================================
-- 3. METRO SCHEDULES & STOPS
-- ==========================================

-- PK Strategy: schedule_id uses varchar for the timetable identifier.
-- Delete Strategy: ON DELETE RESTRICT on origin/destination. Prevents accidental deletion of physical stations that are actively part of a schedule.
CREATE TABLE metro_schedules (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key.
    -- The original JSON schedule_id is preserved as a UNIQUE external identifier
    -- so seed data and query logic can still refer to stable schedule codes.
    id SERIAL PRIMARY KEY,
    schedule_id varchar UNIQUE NOT NULL,
    line varchar NOT NULL,
    direction varchar NOT NULL,
    origin_station_id varchar REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    destination_station_id varchar REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    first_train_time time,
    last_train_time time,
    base_fare_usd decimal(10,2),
    per_stop_rate_usd decimal(10,2),
    frequency_min int
);

-- PK Strategy: Composite key (schedule_id, day) maps schedules to operating days.
-- Delete Strategy: ON DELETE CASCADE. If a schedule is cancelled, its operating days are irrelevant.
CREATE TABLE metro_schedule_operates_on (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key. The pair (schedule_id, day)
    -- remains UNIQUE so one schedule cannot duplicate the same operating day.
    id SERIAL PRIMARY KEY,
    schedule_id varchar REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    day varchar NOT NULL,
    UNIQUE (schedule_id, day)
);

-- PK Strategy: Composite key (schedule_id, stop_order) maintains exactly one sequence per schedule.
-- Delete Strategy: ON DELETE CASCADE on schedule_id (stops disappear with the schedule). ON DELETE RESTRICT on station_id (protects physical stations).
CREATE TABLE metro_schedule_stops (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key. The schedule sequence is
    -- protected by UNIQUE(schedule_id, stop_order), preserving normalised stop order.
    id SERIAL PRIMARY KEY,
    schedule_id varchar REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    station_id varchar REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    stop_order int NOT NULL,
    travel_time_from_origin_min int,
    UNIQUE (schedule_id, stop_order),
    UNIQUE (schedule_id, station_id)
);

-- ==========================================
-- 4. NATIONAL RAIL NETWORK
-- ==========================================

-- PK Strategy: station_id uses varchar (e.g., 'NR01').
CREATE TABLE national_rail_stations (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key for database efficiency.
    -- The original JSON station_id is kept as a UNIQUE external identifier because
    -- station codes such as NR01 are used in mock data, seeding, and graph references.
    id SERIAL PRIMARY KEY,
    station_id varchar UNIQUE NOT NULL,
    name varchar NOT NULL,
    is_interchange_national_rail boolean DEFAULT false,
    is_interchange_metro boolean DEFAULT false,
    interchange_metro_station_id varchar
);

-- PK Strategy: Composite key (station_id, line).
-- Delete Strategy: ON DELETE CASCADE. Follows the same logic as the metro station lines.
CREATE TABLE national_rail_station_lines (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key for consistency across tables.
    -- The pair (station_id, line) remains UNIQUE to prevent duplicate line mappings.
    id SERIAL PRIMARY KEY,
    station_id varchar REFERENCES national_rail_stations(station_id) ON DELETE CASCADE,
    line varchar NOT NULL,
    UNIQUE (station_id, line)
);

-- PK Strategy: Composite key (from_station, to_station, line).
-- Delete Strategy: ON DELETE CASCADE. Ensure network links break if physical stations are removed.
CREATE TABLE national_rail_adjacent_stations (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key. The directional station pair
    -- and line are kept UNIQUE to preserve the natural network constraint.
    id SERIAL PRIMARY KEY,
    from_station_id varchar REFERENCES national_rail_stations(station_id) ON DELETE CASCADE,
    to_station_id varchar REFERENCES national_rail_stations(station_id) ON DELETE CASCADE,
    line varchar NOT NULL,
    travel_time_min int,
    UNIQUE (from_station_id, to_station_id, line)
);


-- ==========================================
-- 5. NATIONAL RAIL SCHEDULES & FARES
-- ==========================================

-- PK Strategy: schedule_id uses varchar.
-- Delete Strategy: ON DELETE RESTRICT for origin/destination to protect underlying station records.
CREATE TABLE national_rail_schedules (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key.
    -- The original JSON schedule_id is preserved as a UNIQUE external identifier
    -- for stable seed import and query references.
    id SERIAL PRIMARY KEY,
    schedule_id varchar UNIQUE NOT NULL,
    line varchar NOT NULL,
    service_type varchar NOT NULL,
    direction varchar NOT NULL,
    origin_station_id varchar REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    destination_station_id varchar REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    first_train_time time,
    last_train_time time,
    base_fare_usd decimal(10,2),
    per_stop_rate_usd decimal(10,2),
    frequency_min int
);

-- PK Strategy: Composite key (schedule_id, day).
-- Delete Strategy: ON DELETE CASCADE. Ties operating days firmly to the existence of the schedule.
CREATE TABLE national_rail_schedule_operates_on (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key. The pair (schedule_id, day)
    -- remains UNIQUE so one schedule cannot duplicate the same operating day.
    id SERIAL PRIMARY KEY,
    schedule_id varchar REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    day varchar NOT NULL,
    UNIQUE (schedule_id, day)
);

-- PK Strategy: Composite key (schedule_id, stop_order). Independent stops table as requested.
-- Delete Strategy: ON DELETE CASCADE on schedule, RESTRICT on station.
CREATE TABLE national_rail_schedule_stops (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key. The schedule sequence is
    -- protected by UNIQUE(schedule_id, stop_order), preserving normalised stop order.
    id SERIAL PRIMARY KEY,
    schedule_id varchar REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    station_id varchar REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    stop_order int NOT NULL,
    travel_time_from_origin_min int,
    UNIQUE (schedule_id, stop_order),
    UNIQUE (schedule_id, station_id)
);
-- PK Strategy: Composite key (schedule_id, fare_class).
-- Delete Strategy: ON DELETE CASCADE. If a schedule is retired, its fare rules go with it.
CREATE TABLE national_rail_fare_classes (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key. The pair (schedule_id, fare_class)
    -- remains UNIQUE because each schedule has one fare rule per fare class.
    id SERIAL PRIMARY KEY,
    schedule_id varchar REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    fare_class varchar NOT NULL,
    base_fare_usd decimal(10,2) NOT NULL,
    per_stop_rate_usd decimal(10,2) NOT NULL,
    UNIQUE (schedule_id, fare_class)
);


-- ==========================================
-- 6. NATIONAL RAIL SEATS & LAYOUTS
-- ==========================================

CREATE TABLE national_rail_seat_layouts (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key.
    -- The original JSON layout_id is kept UNIQUE because seat layout data
    -- refers to stable layout codes.
    id SERIAL PRIMARY KEY,
    layout_id varchar UNIQUE NOT NULL,
    schedule_id varchar REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE
);

CREATE TABLE national_rail_coaches (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key. The pair (layout_id, coach)
    -- remains UNIQUE because each coach belongs to one layout.
    id SERIAL PRIMARY KEY,
    layout_id varchar REFERENCES national_rail_seat_layouts(layout_id) ON DELETE CASCADE,
    coach varchar NOT NULL,
    fare_class varchar NOT NULL,
    UNIQUE (layout_id, coach)
);

-- PK Strategy: Composite key (layout_id, coach, seat_id).
-- Delete Strategy: ON DELETE CASCADE.

CREATE TABLE national_rail_seats (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key. The natural seat identity
    -- (layout_id, coach, seat_id) remains UNIQUE to prevent duplicate seats.
    id SERIAL PRIMARY KEY,
    layout_id varchar,
    coach varchar,
    seat_id varchar,
    row int,
    seat_column varchar,
    UNIQUE (layout_id, coach, seat_id),
    FOREIGN KEY (layout_id, coach) REFERENCES national_rail_coaches(layout_id, coach) ON DELETE CASCADE
);

-- ==========================================
-- 7. TRANSACTIONS: BOOKINGS & TRAVEL HISTORY
-- ==========================================


-- PK Strategy: booking_id uses varchar for booking reference strings (e.g. 'BK001').
-- Delete Strategy: ON DELETE SET NULL for user/schedule to maintain accounting records. RESTRICT for stations and seats to preserve historical integrity.
CREATE TABLE bookings (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key for efficient relational joins.
    -- The original JSON booking_id is preserved as a UNIQUE external booking reference
    -- because it is used in seed data, payment records, and debugging.
    id SERIAL PRIMARY KEY,
    booking_id varchar UNIQUE NOT NULL,
    user_id varchar REFERENCES registered_users(user_id) ON DELETE SET NULL,
    
    schedule_id varchar REFERENCES national_rail_schedules(schedule_id) ON DELETE SET NULL,
    fare_class varchar,
    
    origin_station_id varchar REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    destination_station_id varchar REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    
    layout_id varchar,
    coach varchar,
    seat_id varchar,
    
    travel_date date,
    departure_time time,
    ticket_type varchar,
    stops_travelled int,
    amount_usd decimal(10,2),
    status varchar,
    booked_at timestamptz,
    travelled_at timestamptz,

    -- Foreign keys with multiple columns
    FOREIGN KEY (schedule_id, fare_class) REFERENCES national_rail_fare_classes(schedule_id, fare_class) ON DELETE RESTRICT,
    FOREIGN KEY (layout_id, coach, seat_id) REFERENCES national_rail_seats(layout_id, coach, seat_id) ON DELETE RESTRICT
);

-- PK Strategy: payment_id as primary key.
-- Delete Strategy: ON DELETE SET NULL. Never delete financial ledger records even if the booking or trip is removed.
CREATE TABLE metro_travel_history (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key.
    -- The original JSON trip_id is preserved as a UNIQUE external trip reference
    -- because metro payments and feedback records refer to trip codes such as MT001.
    id SERIAL PRIMARY KEY,
    trip_id varchar UNIQUE NOT NULL,
    user_id varchar REFERENCES registered_users(user_id) ON DELETE SET NULL,
    schedule_id varchar REFERENCES metro_schedules(schedule_id) ON DELETE SET NULL,
    origin_station_id varchar REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    destination_station_id varchar REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    travel_date date,
    ticket_type varchar,
    stops_travelled int,
    amount_usd decimal(10,2),
    status varchar,
    purchased_at timestamptz,
    travelled_at timestamptz
);
CREATE TABLE payments (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key for compact indexing.
    -- The original JSON payment_id is preserved as a UNIQUE external payment reference
    -- for stable seeding and debugging.
    id SERIAL PRIMARY KEY,
    payment_id varchar UNIQUE NOT NULL,
    user_id varchar REFERENCES registered_users(user_id) ON DELETE SET NULL,
    booking_id varchar REFERENCES bookings(booking_id) ON DELETE SET NULL,
    trip_id varchar REFERENCES metro_travel_history(trip_id) ON DELETE SET NULL,
    amount_usd decimal(10,2) NOT NULL,
    method varchar,
    status varchar,
    paid_at timestamptz
);

-- PK Strategy: feedback_id as primary key.
-- Delete Strategy: ON DELETE SET NULL on user and booking. We want to retain the feedback text itself for service improvement even if the user leaves.
CREATE TABLE feedback (
    -- PK Strategy:
    -- We chose SERIAL as the internal primary key.
    -- The original JSON feedback_id is preserved as a UNIQUE external identifier
    -- for stable seed import and traceability.
    id SERIAL PRIMARY KEY,
    feedback_id varchar UNIQUE NOT NULL,
    booking_id varchar REFERENCES bookings(booking_id) ON DELETE SET NULL,
    trip_id varchar REFERENCES metro_travel_history(trip_id) ON DELETE SET NULL,
    user_id varchar REFERENCES registered_users(user_id) ON DELETE SET NULL,
    rating int CHECK (rating >= 1 AND rating <= 5),
    comment text,
    submitted_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (booking_id IS NOT NULL AND trip_id IS NULL)
        OR
        (booking_id IS NULL AND trip_id IS NOT NULL)
    )
);

-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  -- 'refund', 'booking', 'conduct'
    content     TEXT         NOT NULL,
    -- 768-dim  → Ollama nomic-embed-text (default)
    -- 3072-dim → Gemini gemini-embedding-001
    -- If you switch LLM_PROVIDER to gemini, change to vector(3072) and reset the database.
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_policy_embedding ON policy_documents USING hnsw (embedding vector_cosine_ops);