"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""

import json
import os
import sys
from argon2 import PasswordHasher

import psycopg2
from psycopg2.extras import execute_values

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR    = os.path.join(PROJECT_DIR, "train-mock-data")

sys.path.insert(0, PROJECT_DIR)
from skeleton import config as cfg


def load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def connect():
    return psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DB,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )


def insert_many(cur, table, columns, rows):
    """Bulk insert with ON CONFLICT DO NOTHING. Returns row count inserted."""
    if not rows:
        return 0
    
    quoted_columns = [f'"{col}"' for col in columns]
    sql = f"INSERT INTO {table} ({', '.join(quoted_columns)}) VALUES %s ON CONFLICT DO NOTHING"
    execute_values(cur, sql, rows)
    return cur.rowcount

ph = PasswordHasher()

def get_hash(text: str) -> str:
    if not text:
        return None
    return ph.hash(text)


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_metro_stations(cur):
    data = load("metro_stations.json")
    
    stations_rows = []
    lines_rows = []
    adjacent_rows = []
    
    for s in data:
        stations_rows.append((
            s["station_id"], s["name"], s.get("is_interchange_metro", False),
            s.get("is_interchange_national_rail", False), s.get("interchange_national_rail_station_id")
        ))
        for line in s.get("lines", []):
            lines_rows.append((s["station_id"], line))
        for adj in s.get("adjacent_stations", []):
            adjacent_rows.append((s["station_id"], adj["station_id"], adj["line"], adj.get("travel_time_min")))
            
    n_sta = insert_many(cur, "metro_stations", ["station_id", "name", "is_interchange_metro", "is_interchange_national_rail", "interchange_national_rail_station_id"], stations_rows)
    n_lines = insert_many(cur, "metro_station_lines", ["station_id", "line"], lines_rows)
    n_adj = insert_many(cur, "metro_adjacent_stations", ["from_station_id", "to_station_id", "line", "travel_time_min"], adjacent_rows)
    print(f"  -> metro_stations: {n_sta} rows, lines: {n_lines} rows, adjacent: {n_adj} rows")


def seed_national_rail_stations(cur):
    data = load("national_rail_stations.json")
    
    stations_rows = []
    lines_rows = []
    adjacent_rows = []
    
    for s in data:
        stations_rows.append((
            s["station_id"], s["name"], s.get("is_interchange_national_rail", False),
            s.get("is_interchange_metro", False), s.get("interchange_metro_station_id")
        ))
        for line in s.get("lines", []):
            lines_rows.append((s["station_id"], line))
        for adj in s.get("adjacent_stations", []):
            adjacent_rows.append((s["station_id"], adj["station_id"], adj["line"], adj.get("travel_time_min")))
            
    n_sta = insert_many(cur, "national_rail_stations", ["station_id", "name", "is_interchange_national_rail", "is_interchange_metro", "interchange_metro_station_id"], stations_rows)
    n_lines = insert_many(cur, "national_rail_station_lines", ["station_id", "line"], lines_rows)
    n_adj = insert_many(cur, "national_rail_adjacent_stations", ["from_station_id", "to_station_id", "line", "travel_time_min"], adjacent_rows)
    print(f"  -> national_rail_stations: {n_sta} rows, lines: {n_lines} rows, adjacent: {n_adj} rows")


def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    
    sched_rows = []
    op_rows = []
    stop_rows = []
    
    for sch in data:
        sched_rows.append((
            sch["schedule_id"], sch["line"], sch["direction"], sch["origin_station_id"], sch["destination_station_id"],
            sch.get("first_train_time"), sch.get("last_train_time"), sch.get("base_fare_usd"), sch.get("per_stop_rate_usd"), sch.get("frequency_min")
        ))
        for day in sch.get("operates_on", []):
            op_rows.append((sch["schedule_id"], day))
        for stop in sch.get("stops", []):
            stop_rows.append((sch["schedule_id"], stop["station_id"], stop["stop_order"], stop.get("travel_time_from_origin_min")))
            
    n_sch = insert_many(cur, "metro_schedules", ["schedule_id", "line", "direction", "origin_station_id", "destination_station_id", "first_train_time", "last_train_time", "base_fare_usd", "per_stop_rate_usd", "frequency_min"], sched_rows)
    n_op = insert_many(cur, "metro_schedule_operates_on", ["schedule_id", "day"], op_rows)
    n_stops = insert_many(cur, "metro_schedule_stops", ["schedule_id", "station_id", "stop_order", "travel_time_from_origin_min"], stop_rows)
    print(f"  -> metro_schedules: {n_sch} rows, operates_on: {n_op} rows, stops: {n_stops} rows")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    
    sched_rows = []
    op_rows = []
    stop_rows = []
    fare_rows = []
    
    for sch in data:
        sched_rows.append((
            sch["schedule_id"], sch["line"], sch["service_type"], sch["direction"], sch["origin_station_id"], sch["destination_station_id"],
            sch.get("first_train_time"), sch.get("last_train_time"), sch.get("base_fare_usd"), sch.get("per_stop_rate_usd"), sch.get("frequency_min")
        ))
        for day in sch.get("operates_on", []):
            op_rows.append((sch["schedule_id"], day))
        for stop in sch.get("stops", []):
            stop_rows.append((sch["schedule_id"], stop["station_id"], stop["stop_order"], stop.get("travel_time_from_origin_min")))
            
        fare_classes_dict = sch.get("fare_classes", {})
        if isinstance(fare_classes_dict, dict):
            for fare_class, details in fare_classes_dict.items():
                fare_rows.append((
                    sch["schedule_id"], 
                    fare_class, 
                    details.get("base_fare_usd"), 
                    details.get("per_stop_rate_usd")
                ))
            
    n_sch = insert_many(cur, "national_rail_schedules", ["schedule_id", "line", "service_type", "direction", "origin_station_id", "destination_station_id", "first_train_time", "last_train_time", "base_fare_usd", "per_stop_rate_usd", "frequency_min"], sched_rows)
    n_op = insert_many(cur, "national_rail_schedule_operates_on", ["schedule_id", "day"], op_rows)
    n_stops = insert_many(cur, "national_rail_schedule_stops", ["schedule_id", "station_id", "stop_order", "travel_time_from_origin_min"], stop_rows)
    n_fares = insert_many(cur, "national_rail_fare_classes", ["schedule_id", "fare_class", "base_fare_usd", "per_stop_rate_usd"], fare_rows)
    print(f"  -> national_rail_schedules: {n_sch} rows, stops: {n_stops} rows, fares: {n_fares} rows")


def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    
    layout_rows = []
    coach_rows = []
    seat_rows = []
    
    for lay in data:
        layout_rows.append((lay["layout_id"], lay["schedule_id"]))
        for co in lay.get("coaches", []):
            coach_rows.append((lay["layout_id"], co["coach"], co["fare_class"]))
            for seat in co.get("seats", []):
                seat_rows.append((lay["layout_id"], co["coach"], seat["seat_id"], seat.get("row"), seat.get("seat_column")))
                
    n_lay = insert_many(cur, "national_rail_seat_layouts", ["layout_id", "schedule_id"], layout_rows)
    n_co = insert_many(cur, "national_rail_coaches", ["layout_id", "coach", "fare_class"], coach_rows)
    n_se = insert_many(cur, "national_rail_seats", ["layout_id", "coach", "seat_id", "row", "seat_column"], seat_rows)
    print(f"  -> seat_layouts: {n_lay} rows, coaches: {n_co} rows, seats: {n_se} rows")


def seed_users(cur):
    data = load("registered_users.json")

    user_rows = []
    cred_rows = []

    for u in data:
        user_rows.append((
            u["user_id"],
            u["full_name"],
            u["email"],
            u.get("phone"),
            u.get("date_of_birth"),
            u.get("secret_question"),
            get_hash(u.get("secret_answer")),
            u.get("registered_at"),
            True
        ))

        cred_rows.append((
            f"CRED-{u['user_id']}",
            u["user_id"],
            get_hash(u["password"]),
            u.get("registered_at"),
            None
        ))

    n_users = insert_many(
        cur,
        "registered_users",
        [
            "user_id",
            "full_name",
            "email",
            "phone",
            "date_of_birth",
            "secret_question",
            "secret_answer_hash",
            "registered_at",
            "is_active"
        ],
        user_rows
    )

    n_creds = insert_many(
        cur,
        "user_credentials",
        [
            "credential_id",
            "user_id",
            "password_hash",
            "created_at",
            "last_login_at"
        ],
        cred_rows
    )

    print(f"  -> registered_users: {n_users} rows, user_credentials: {n_creds} rows")


def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    
    rows = []
    for b in data:
        rows.append((
            b["booking_id"], b["user_id"], b.get("schedule_id"), b.get("fare_class"),
            b.get("origin_station_id"), b.get("destination_station_id"), b.get("layout_id"),
            b.get("coach"), b.get("seat_id"), b.get("travel_date"), b.get("departure_time"),
            b.get("ticket_type"), b.get("stops_travelled"), b.get("amount_usd"),
            b.get("status"), b.get("booked_at"), b.get("travelled_at")
        ))
        
    n = insert_many(cur, "bookings", ["booking_id", "user_id", "schedule_id", "fare_class", "origin_station_id", "destination_station_id", "layout_id", "coach", "seat_id", "travel_date", "departure_time", "ticket_type", "stops_travelled", "amount_usd", "status", "booked_at", "travelled_at"], rows)
    print(f"  -> bookings: {n} rows")


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    
    rows = []
    for h in data:
        rows.append((
            h["trip_id"], h["user_id"], h.get("schedule_id"), h.get("origin_station_id"), h.get("destination_station_id"),
            h.get("travel_date"), h.get("ticket_type"), h.get("stops_travelled"), h.get("amount_usd"),
            h.get("status"), h.get("purchased_at"), h.get("travelled_at")
        ))
        
    n = insert_many(cur, "metro_travel_history", ["trip_id", "user_id", "schedule_id", "origin_station_id", "destination_station_id", "travel_date", "ticket_type", "stops_travelled", "amount_usd", "status", "purchased_at", "travelled_at"], rows)
    print(f"  -> metro_travel_history: {n} rows")


def seed_payments(cur):
    data = load("payments.json")

    rows = []

    for p in data:
        booking_id = p.get("booking_id")
        trip_id = p.get("trip_id")

        # Some metro payments incorrectly store trip IDs in booking_id
        if booking_id and booking_id.startswith("MT"):
            trip_id = booking_id
            booking_id = None

        rows.append((
            p["payment_id"],
            p.get("user_id"),
            booking_id,
            trip_id,
            p["amount_usd"],
            p.get("method"),
            p.get("status"),
            p.get("paid_at")
        ))

    n = insert_many(
        cur,
        "payments",
        [
            "payment_id",
            "user_id",
            "booking_id",
            "trip_id",
            "amount_usd",
            "method",
            "status",
            "paid_at"
        ],
        rows
    )

    print(f"  -> payments: {n} rows")
        
    

def seed_feedback(cur):
    data = load("feedback.json")

    rows = []

    for f in data:
        booking_id = f.get("booking_id")
        trip_id = f.get("trip_id")

        # Some metro feedback records store trip IDs in booking_id
        if booking_id and booking_id.startswith("MT"):
            trip_id = booking_id
            booking_id = None

        rows.append((
            f["feedback_id"],
            booking_id,
            trip_id,
            f["user_id"],
            f.get("rating"),
            f.get("comment"),
            f.get("submitted_at")
        ))

    n = insert_many(
        cur,
        "feedback",
        [
            "feedback_id",
            "booking_id",
            "trip_id",
            "user_id",
            "rating",
            "comment",
            "submitted_at"
        ],
        rows
    )

    print(f"  -> feedback: {n} rows")

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        seed_metro_stations(cur)
        seed_national_rail_stations(cur)
        seed_metro_schedules(cur)
        seed_national_rail_schedules(cur)
        seed_seat_layouts(cur)
        seed_users(cur)
        seed_national_rail_bookings(cur)
        seed_metro_travels(cur)
        seed_payments(cur)
        seed_feedback(cur)
        conn.commit()
        print("\nAll done. Database seeded successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()