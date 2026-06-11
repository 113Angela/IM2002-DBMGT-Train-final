"""
TransitFlow — PostgreSQL / Relational Database Layer
=====================================================
Member C — SQL Query Functions
All query functions for PostgreSQL. Called by skeleton/agent.py as tools.
"""

from __future__ import annotations

import random
import string
import uuid
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


# ── Connection helper ──────────────────────────────────────────────────────────
def _connect():
    """Return a new psycopg2 connection with autocommit enabled."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


def _gen_id(prefix: str, length: int = 6) -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=length))
    return f"{prefix}-{suffix}"


# ── NATIONAL RAIL AVAILABILITY ────────────────────────────────────────────────

def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None,
) -> list[dict]:
    """
    Return national rail schedules serving both origin and destination in order.

    Args:
        origin_id:      e.g. "NR01"
        destination_id: e.g. "NR05"
        travel_date:    e.g. "2025-06-01" — filters by operating day if provided
    """
    sql = """
        SELECT DISTINCT
            s.schedule_id,
            s.line,
            s.service_type,
            s.direction,
            s.first_train_time::text,
            s.last_train_time::text,
            s.frequency_min,
            orig.name AS origin_name,
            dest.name AS destination_name,
            os.stop_order AS origin_stop_order,
            ds.stop_order AS dest_stop_order,
            (ds.stop_order - os.stop_order) AS stops_travelled
        FROM national_rail_schedules s
        JOIN national_rail_schedule_stops os
            ON s.schedule_id = os.schedule_id AND os.station_id = %s
        JOIN national_rail_schedule_stops ds
            ON s.schedule_id = ds.schedule_id AND ds.station_id = %s
        JOIN national_rail_stations orig ON orig.station_id = %s
        JOIN national_rail_stations dest ON dest.station_id = %s
        WHERE os.stop_order < ds.stop_order
        ORDER BY s.first_train_time;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id, origin_id, destination_id))
            rows = [dict(r) for r in cur.fetchall()]

    if travel_date and rows:
        try:
            day_map = {0:"monday",1:"tuesday",2:"wednesday",3:"thursday",
                       4:"friday",5:"saturday",6:"sunday"}
            day_name = day_map[datetime.strptime(travel_date, "%Y-%m-%d").weekday()]
            with _connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        "SELECT schedule_id FROM national_rail_schedule_operates_on WHERE day = %s",
                        (day_name,)
                    )
                    valid_ids = {r["schedule_id"] for r in cur.fetchall()}
            rows = [r for r in rows if r["schedule_id"] in valid_ids]
        except ValueError:
            pass

    return rows


def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    """
    Calculate the fare for a national rail journey.

    Args:
        schedule_id:     e.g. "NR_SCH01"
        fare_class:      "standard" or "first"
        stops_travelled: number of stops between origin and destination
    """
    sql = """
        SELECT
            fc.schedule_id,
            fc.fare_class,
            fc.base_fare_usd,
            fc.per_stop_rate_usd,
            ROUND(fc.base_fare_usd + (fc.per_stop_rate_usd * %s), 2) AS total_fare_usd
        FROM national_rail_fare_classes fc
        WHERE fc.schedule_id = %s AND LOWER(fc.fare_class) = LOWER(%s);
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (stops_travelled, schedule_id, fare_class))
            row = cur.fetchone()
            return dict(row) if row else None


# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules serving both origin and destination in correct order.

    Args:
        origin_id:      e.g. "MS01"
        destination_id: e.g. "MS09"
    """
    sql = """
        SELECT DISTINCT
            s.schedule_id,
            s.line,
            s.direction,
            s.first_train_time::text,
            s.last_train_time::text,
            s.frequency_min,
            orig.name AS origin_name,
            dest.name AS destination_name,
            os.stop_order AS origin_stop_order,
            ds.stop_order AS dest_stop_order,
            (ds.stop_order - os.stop_order) AS stops_travelled
        FROM metro_schedules s
        JOIN metro_schedule_stops os
            ON s.schedule_id = os.schedule_id AND os.station_id = %s
        JOIN metro_schedule_stops ds
            ON s.schedule_id = ds.schedule_id AND ds.station_id = %s
        JOIN metro_stations orig ON orig.station_id = %s
        JOIN metro_stations dest ON dest.station_id = %s
        WHERE os.stop_order < ds.stop_order
        ORDER BY s.schedule_id;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id, origin_id, destination_id))
            return [dict(r) for r in cur.fetchall()]


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.

    Args:
        schedule_id:     e.g. "MS_SCH01"
        stops_travelled: number of stops between origin and destination
    """
    sql = """
        SELECT
            schedule_id,
            base_fare_usd,
            per_stop_rate_usd,
            ROUND(base_fare_usd + (per_stop_rate_usd * %s), 2) AS total_fare_usd
        FROM metro_schedules
        WHERE schedule_id = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (stops_travelled, schedule_id))
            row = cur.fetchone()
            return dict(row) if row else None


# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    """
    Return available (unbooked) seats for a national rail journey on a given date.

    Args:
        schedule_id:  e.g. "NR_SCH01"
        travel_date:  e.g. "2025-06-01"
        fare_class:   "standard" or "first"
    """
    sql = """
        SELECT
            seat.layout_id,
            seat.coach,
            seat.seat_id,
            seat.row,
            seat.seat_column AS column,
            coach.fare_class
        FROM national_rail_seat_layouts layout
        JOIN national_rail_coaches coach
            ON layout.layout_id = coach.layout_id
        JOIN national_rail_seats seat
            ON coach.layout_id = seat.layout_id AND coach.coach = seat.coach
        WHERE layout.schedule_id = %s
          AND LOWER(coach.fare_class) = LOWER(%s)
          AND (seat.layout_id, seat.coach, seat.seat_id) NOT IN (
              SELECT layout_id, coach, seat_id FROM bookings
              WHERE schedule_id = %s
                AND travel_date = %s::date
                AND status NOT IN ('cancelled', 'refunded')
          )
        ORDER BY seat.coach, seat.row, seat.seat_column
        LIMIT 30;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id, fare_class, schedule_id, travel_date))
            return [dict(r) for r in cur.fetchall()]


def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    """Select seats that are as close together as possible."""
    if not available_seats or count <= 0:
        return []
    if count >= len(available_seats):
        return [s["seat_id"] for s in available_seats[:count]]
    from collections import defaultdict
    rows: dict = defaultdict(list)
    for seat in available_seats:
        rows[seat["row"]].append(seat)
    for row_seats in sorted(rows.values(), key=lambda s: s[0]["row"]):
        if len(row_seats) >= count:
            return [s["seat_id"] for s in row_seats[:count]]
    sorted_seats = sorted(available_seats, key=lambda s: (s["row"], s["column"]))
    return [s["seat_id"] for s in sorted_seats[:count]]


# ── USER QUERIES (implemented by teammate A) ──────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """Return a user's profile by email."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT user_id, full_name, email, phone,
                       date_of_birth, registered_at, is_active
                FROM registered_users
                WHERE email = %s LIMIT 1
            """, (user_email,))
            row = cur.fetchone()
            return dict(row) if row else None


def query_user_bookings(user_email: str) -> dict:
    """Return a user's combined booking history (national rail + metro)."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT b.booking_id, b.travel_date, b.amount_usd, b.status,
                       orig.name AS origin_name, dest.name AS destination_name,
                       s.line, s.service_type, b.fare_class
                FROM bookings b
                JOIN registered_users u ON b.user_id = u.user_id
                JOIN national_rail_stations orig ON orig.station_id = b.origin_station_id
                JOIN national_rail_stations dest ON dest.station_id = b.destination_station_id
                JOIN national_rail_schedules s ON s.schedule_id = b.schedule_id
                WHERE u.email = %s
                ORDER BY b.travel_date DESC
            """, (user_email,))
            national_rows = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT m.trip_id, m.travel_date, m.amount_usd, m.status,
                       orig.name AS origin_name, dest.name AS destination_name
                FROM metro_travel_history m
                JOIN registered_users u ON m.user_id = u.user_id
                JOIN metro_stations orig ON orig.station_id = m.origin_station_id
                JOIN metro_stations dest ON dest.station_id = m.destination_station_id
                WHERE u.email = %s
                ORDER BY m.travel_date DESC
            """, (user_email,))
            metro_rows = [dict(r) for r in cur.fetchall()]

            return {"national_rail": national_rows, "metro": metro_rows}


def query_payment_info(booking_id: str) -> Optional[dict]:
    """Return payment record for a booking or metro trip."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT payment_id, booking_id, trip_id,
                       amount_usd, method, status, paid_at
                FROM payments
                WHERE booking_id = %s OR trip_id = %s
                LIMIT 1
            """, (booking_id, booking_id))
            row = cur.fetchone()
            return dict(row) if row else None


# ── TRANSACTIONAL OPERATIONS ──────────────────────────────────────────────────

def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
    """
    Create a national rail booking for a logged-in user.

    Returns:
        (True, booking_dict) on success
        (False, error_message) on failure
    """
    try:
        conn = psycopg2.connect(PG_DSN)
        conn.autocommit = False
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get stop orders
                cur.execute("""
                    SELECT stop_order FROM national_rail_schedule_stops
                    WHERE schedule_id = %s AND station_id = %s
                """, (schedule_id, origin_station_id))
                orig = cur.fetchone()
                cur.execute("""
                    SELECT stop_order FROM national_rail_schedule_stops
                    WHERE schedule_id = %s AND station_id = %s
                """, (schedule_id, destination_station_id))
                dest = cur.fetchone()
                if not orig or not dest:
                    return False, "Origin or destination not on this schedule."
                stops_travelled = dest["stop_order"] - orig["stop_order"]

                # Get fare
                cur.execute("""
                    SELECT base_fare_usd, per_stop_rate_usd
                    FROM national_rail_fare_classes
                    WHERE schedule_id = %s AND LOWER(fare_class) = LOWER(%s)
                """, (schedule_id, fare_class))
                fare_row = cur.fetchone()
                if not fare_row:
                    return False, f"Fare class '{fare_class}' not found."
                amount = round(float(fare_row["base_fare_usd"]) +
                               float(fare_row["per_stop_rate_usd"]) * stops_travelled, 2)

                # Get layout/coach for seat
                cur.execute("""
                    SELECT seat.layout_id, seat.coach
                    FROM national_rail_seats seat
                    JOIN national_rail_coaches coach
                        ON seat.layout_id = coach.layout_id AND seat.coach = coach.coach
                    JOIN national_rail_seat_layouts layout
                        ON coach.layout_id = layout.layout_id
                    WHERE layout.schedule_id = %s AND seat.seat_id = %s
                      AND LOWER(coach.fare_class) = LOWER(%s)
                """, (schedule_id, seat_id, fare_class))
                seat_row = cur.fetchone()
                if not seat_row:
                    return False, f"Seat '{seat_id}' not found for this class."

                # Check seat not already booked
                cur.execute("""
                    SELECT 1 FROM bookings
                    WHERE schedule_id = %s AND seat_id = %s
                      AND travel_date = %s::date
                      AND status NOT IN ('cancelled','refunded')
                """, (schedule_id, seat_id, travel_date))
                if cur.fetchone():
                    return False, f"Seat '{seat_id}' is already booked."

                # Get departure time
                cur.execute(
                    "SELECT first_train_time FROM national_rail_schedules WHERE schedule_id = %s",
                    (schedule_id,)
                )
                sched = cur.fetchone()
                departure_time = sched["first_train_time"] if sched else None

                # Insert booking
                booking_id = _gen_id("BK")
                cur.execute("""
                    INSERT INTO bookings (
                        booking_id, user_id, schedule_id, fare_class,
                        origin_station_id, destination_station_id,
                        layout_id, coach, seat_id,
                        travel_date, departure_time, ticket_type,
                        stops_travelled, amount_usd, status, booked_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::date,%s,%s,%s,%s,'confirmed',NOW())
                    RETURNING *
                """, (
                    booking_id, user_id, schedule_id, fare_class,
                    origin_station_id, destination_station_id,
                    seat_row["layout_id"], seat_row["coach"], seat_id,
                    travel_date, departure_time, ticket_type,
                    stops_travelled, amount
                ))
                booking = dict(cur.fetchone())

                # Insert payment
                payment_id = _gen_id("PM")
                cur.execute("""
                    INSERT INTO payments (payment_id, user_id, booking_id, amount_usd,
                                         method, status, paid_at)
                    VALUES (%s,%s,%s,%s,'card','completed',NOW())
                """, (payment_id, user_id, booking_id, amount))

            conn.commit()
            booking["payment_id"] = payment_id
            return True, booking
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()
    except Exception as e:
        return False, str(e)


def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancel a national rail booking. Calculates refund per policy.

    Returns:
        (True, result_dict) with refund_amount_usd
        (False, error_msg)
    """
    try:
        conn = psycopg2.connect(PG_DSN)
        conn.autocommit = False
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT b.*, s.service_type
                    FROM bookings b
                    JOIN national_rail_schedules s ON b.schedule_id = s.schedule_id
                    WHERE b.booking_id = %s AND b.user_id = %s
                """, (booking_id, user_id))
                booking = cur.fetchone()
                if not booking:
                    return False, "Booking not found or does not belong to this user."
                if booking["status"] in ("cancelled", "refunded"):
                    return False, f"Booking is already {booking['status']}."

                # Refund calculation
                travel_dt = datetime.combine(booking["travel_date"], booking["departure_time"])
                hours_until = (travel_dt - datetime.now()).total_seconds() / 3600
                service_type = (booking["service_type"] or "").lower()
                if service_type == "express":
                    pct = 1.0 if hours_until >= 48 else (0.5 if hours_until >= 24 else 0.0)
                else:
                    pct = 1.0 if hours_until >= 48 else (0.75 if hours_until >= 24 else (0.5 if hours_until >= 2 else 0.0))
                refund = round(float(booking["amount_usd"]) * pct, 2)

                cur.execute("""
                    UPDATE bookings SET status = 'cancelled'
                    WHERE booking_id = %s RETURNING *
                """, (booking_id,))
                updated = dict(cur.fetchone())

                pay_id = _gen_id("REF")
                cur.execute("""
                    INSERT INTO payments (payment_id, user_id, booking_id, amount_usd,
                                         method, status, paid_at)
                    VALUES (%s,%s,%s,%s,'refund','completed',NOW())
                """, (pay_id, user_id, booking_id, refund))

            conn.commit()
            updated["refund_amount_usd"] = refund
            updated["refund_percent"] = int(pct * 100)
            updated["refund_payment_id"] = pay_id
            return True, updated
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()
    except Exception as e:
        return False, str(e)


# ── AUTHENTICATION ────────────────────────────────────────────────────────────

def register_user(
    email: str,
    first_name: str,
    surname: str,
    year_of_birth: int,
    password: str,
    secret_question: str,
    secret_answer: str,
) -> tuple[bool, str]:
    """
    Register a new user. Returns (True, user_id) or (False, error_message).
    NOTE: passwords stored as plain text for teaching purposes.
    """
    try:
        conn = psycopg2.connect(PG_DSN)
        conn.autocommit = False
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT 1 FROM registered_users WHERE email = %s", (email,))
                if cur.fetchone():
                    return False, "Email is already registered."

                user_id = "RU" + str(uuid.uuid4())[:8].upper()
                cred_id = "CR" + str(uuid.uuid4())[:8].upper()
                full_name = f"{first_name} {surname}"
                dob = f"{year_of_birth}-01-01"

                cur.execute("""
                    INSERT INTO registered_users
                        (user_id, full_name, email, secret_question,
                         secret_answer_hash, date_of_birth, is_active)
                    VALUES (%s,%s,%s,%s,%s,%s::date,true)
                """, (user_id, full_name, email, secret_question,
                      secret_answer.lower().strip(), dob))

                cur.execute("""
                    INSERT INTO user_credentials (credential_id, user_id, password_hash)
                    VALUES (%s,%s,%s)
                """, (cred_id, user_id, password))

            conn.commit()
            return True, user_id
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()
    except Exception as e:
        return False, str(e)


def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials. Returns user dict on success or None on failure.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT u.user_id, u.full_name, u.email, u.phone,
                       u.date_of_birth, u.is_active, c.password_hash
                FROM registered_users u
                JOIN user_credentials c ON u.user_id = c.user_id
                WHERE u.email = %s AND u.is_active = true
            """, (email,))
            row = cur.fetchone()
            if not row:
                return None
            # Plain text comparison (teaching project)
            if row["password_hash"] != password:
                return None
            user = dict(row)
            user.pop("password_hash", None)
            # Parse first/last name
            parts = (user.get("full_name") or "").split(" ", 1)
            user["first_name"] = parts[0]
            user["surname"] = parts[1] if len(parts) > 1 else ""
            return user


def get_user_secret_question(email: str) -> Optional[str]:
    """Return the secret question for a registered email, or None if not found."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT secret_question FROM registered_users
                WHERE email = %s AND is_active = true
            """, (email,))
            row = cur.fetchone()
            return row["secret_question"] if row else None


def verify_secret_answer(email: str, answer: str) -> bool:
    """Return True if the answer matches the stored secret answer (case-insensitive)."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT secret_answer_hash FROM registered_users
                WHERE email = %s AND is_active = true
            """, (email,))
            row = cur.fetchone()
            if not row or not row["secret_answer_hash"]:
                return False
            return row["secret_answer_hash"] == answer.lower().strip()


def update_password(email: str, new_password: str) -> bool:
    """Update the password for a user. Returns True if updated."""
    try:
        conn = psycopg2.connect(PG_DSN)
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE user_credentials SET password_hash = %s
                    WHERE user_id = (
                        SELECT user_id FROM registered_users
                        WHERE email = %s AND is_active = true
                    )
                """, (new_password, email))
                updated = cur.rowcount
            conn.commit()
            return updated > 0
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()
    except Exception:
        return False


# ── VECTOR / RAG QUERIES — do not modify ─────────────────────────────────────

def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.
    """
    sql = """
        SELECT title, category, content,
               1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return [dict(row) for row in cur.fetchall()]


def store_policy_document(
    title: str,
    category: str,
    content: str,
    embedding: list[float],
    source_file: str = "",
) -> int:
    """
    Insert a policy document with its embedding. Used by seed_vectors.py.
    """
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            return cur.fetchone()[0]