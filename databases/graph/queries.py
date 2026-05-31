"""
TransitFlow — Neo4j Graph Database Layer
=========================================
This module handles all queries to Neo4j.

GRAPH ROLE:
  - Model the dual transit network (city metro M1–M4 + national rail NR1–NR2)
  - Find fastest routes (Dijkstra by travel_time_min via APOC)
  - Find cheapest routes (Dijkstra by fare via APOC)
  - Find alternative routes avoiding a given station
  - Find cross-network interchange paths (metro → rail or rail → metro)
  - Show delay ripple: which stations are affected within N hops

STUDENT TASK
------------
Design your graph schema (node labels, relationship types, properties)
based on the data in train-mock-data/, seed it with skeleton/seed_neo4j.py,
then implement the query_ functions below.

Functions prefixed with `query_` are called by the agent (skeleton/agent.py).
"""

from __future__ import annotations

from typing import Optional

from neo4j import GraphDatabase

from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    """Return a Neo4j driver. Caller is responsible for closing."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a session, run Cypher, return data.

def example_count_nodes() -> int:
    """Example: count all nodes currently in the graph."""
    with _driver() as driver:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS total")
            return result.single()["total"]

# TODO: Implement the query_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── FASTEST ROUTE (Dijkstra by travel_time_min) ───────────────────────────────

def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """
    Find the fastest path between two stations, minimising total travel time.
    Uses apoc.algo.dijkstra (APOC required; enabled in docker-compose.yml).

    Args:
        origin_id:       e.g. "MS01" or "NR01"
        destination_id:  e.g. "MS09" or "NR05"
        network:         "metro", "rail", or "auto" (inferred from IDs)

    Returns:
        dict with keys: found, origin_id, destination_id,
                        total_time_min, path (list of station dicts), legs
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (start {station_id: $origin_id})
                MATCH (end {station_id: $destination_id})
                MATCH p = shortestPath((start)-[*..30]-(end))
                RETURN p
                """,
                origin_id=origin_id,
                destination_id=destination_id,
            )

            record = result.single()

            if record is None:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                }

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "path": str(record["p"]),
            }


# ── CHEAPEST ROUTE (Dijkstra by fare) ────────────────────────────────────────

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    """
    Find the cheapest path between two stations, minimising total estimated fare.

    Args:
        origin_id:       e.g. "NR01"
        destination_id:  e.g. "NR05"
        network:         "metro", "rail", or "auto"
        fare_class:      "standard" or "first" (national rail only)

    Returns:
        dict with found, total_fare_usd (approximate), stations, legs
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (a)-[r:METRO_LINK|RAIL_LINK|INTERCHANGE_TO]->(b)
                RETURN
                    a.station_id AS from_id,
                    a.name AS from_name,
                    a.lines AS from_lines,
                    b.station_id AS to_id,
                    b.name AS to_name,
                    b.lines AS to_lines,
                    type(r) AS relationship,
                    r.line AS line,
                    r.travel_time_min AS travel_time_min
                """
            )

            edges = {}
            station_info = {}

            for row in result:
                from_id = row["from_id"]
                to_id = row["to_id"]
                relationship = row["relationship"]

                station_info[from_id] = {
                    "station_id": from_id,
                    "name": row["from_name"],
                    "lines": row["from_lines"],
                }
                station_info[to_id] = {
                    "station_id": to_id,
                    "name": row["to_name"],
                    "lines": row["to_lines"],
                }

                if relationship == "METRO_LINK":
                    fare = 2
                elif relationship == "RAIL_LINK":
                    fare = 10 if fare_class == "first" else 5
                else:
                    fare = 0

                edges.setdefault(from_id, []).append({
                    "to": to_id,
                    "relationship": relationship,
                    "line": row["line"],
                    "travel_time_min": row["travel_time_min"],
                    "fare": fare,
                })

            if origin_id not in station_info or destination_id not in station_info:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                }

            import heapq

            pq = [(0, origin_id, [])]
            best = {origin_id: 0}

            while pq:
                cost, current, path = heapq.heappop(pq)

                if current == destination_id:
                    stations = [station_info[origin_id]]
                    legs = []
                    total_fare = 0

                    for leg in path:
                        from_station = station_info[leg["from"]]
                        to_station = station_info[leg["to"]]
                        total_fare += leg["fare"]
                        stations.append(to_station)

                        legs.append({
                            "from": from_station["station_id"],
                            "from_name": from_station["name"],
                            "to": to_station["station_id"],
                            "to_name": to_station["name"],
                            "relationship": leg["relationship"],
                            "line": leg["line"],
                            "travel_time_min": leg["travel_time_min"],
                            "estimated_fare_usd": leg["fare"],
                        })

                    return {
                        "found": True,
                        "origin_id": origin_id,
                        "destination_id": destination_id,
                        "fare_class": fare_class,
                        "total_fare_usd": total_fare,
                        "stations": stations,
                        "legs": legs,
                    }

                if cost > best.get(current, float("inf")):
                    continue

                for edge in edges.get(current, []):
                    next_id = edge["to"]
                    new_cost = cost + edge["fare"]

                    if new_cost < best.get(next_id, float("inf")):
                        best[next_id] = new_cost
                        heapq.heappush(
                            pq,
                            (
                                new_cost,
                                next_id,
                                path + [{
                                    "from": current,
                                    "to": next_id,
                                    "relationship": edge["relationship"],
                                    "line": edge["line"],
                                    "travel_time_min": edge["travel_time_min"],
                                    "fare": edge["fare"],
                                }],
                            ),
                        )

            return {
                "found": False,
                "origin_id": origin_id,
                "destination_id": destination_id,
            }



# ── ALTERNATIVE ROUTES (avoiding a station) ───────────────────────────────────

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3,
) -> list[list[dict]]:
    """
    Find paths between two stations that avoid a specific intermediate station.
    Useful for routing around a delayed or closed station.

    Args:
        origin_id:         e.g. "NR01"
        destination_id:    e.g. "NR05"
        avoid_station_id:  e.g. "NR03"
        network:           "metro", "rail", or "auto"
        max_routes:        max number of alternatives to return

    Returns:
        List of routes, each route is a list of leg dicts
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (start {station_id: $origin_id})
                MATCH (end {station_id: $destination_id})
                MATCH p = shortestPath((start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*..12]-(end))
                WHERE NONE(n IN nodes(p) WHERE n.station_id = $avoid_station_id)
                RETURN nodes(p) AS nodes, relationships(p) AS rels
                """,
                origin_id=origin_id,
                destination_id=destination_id,
                avoid_station_id=avoid_station_id,
            )

            record = result.single()

            if record is None:
                return []

            nodes = record["nodes"]
            rels = record["rels"]

            stations = []
            for node in nodes:
                stations.append({
                    "station_id": node.get("station_id"),
                    "name": node.get("name"),
                    "lines": node.get("lines"),
                })

            legs = []
            total_time = 0

            for i, rel in enumerate(rels):
                travel_time = rel.get("travel_time_min", 0) or 0
                total_time += travel_time

                legs.append({
                    "from": stations[i]["station_id"],
                    "from_name": stations[i]["name"],
                    "to": stations[i + 1]["station_id"],
                    "to_name": stations[i + 1]["name"],
                    "relationship": rel.type,
                    "line": rel.get("line"),
                    "travel_time_min": travel_time,
                    "total_time_min": total_time,
                })

            return [legs]


# ── CROSS-NETWORK INTERCHANGE PATH ───────────────────────────────────────────

def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    """
    Find a path between a metro station and a national rail station (or vice versa)
    crossing the network boundary via interchange relationships.

    Args:
        origin_id:       e.g. "MS03" (metro) or "NR05" (national rail)
        destination_id:  e.g. "NR05" (national rail) or "MS09" (metro)

    Returns:
        dict with found, stations list, interchange points, total_time_min
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (start {station_id: $origin_id})
                MATCH (end {station_id: $destination_id})
                MATCH p = shortestPath((start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*..30]-(end))
                RETURN nodes(p) AS nodes, relationships(p) AS rels
                """,
                origin_id=origin_id,
                destination_id=destination_id,
            )

            record = result.single()

            if record is None:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                }

            nodes = record["nodes"]
            rels = record["rels"]

            stations = []
            for node in nodes:
                stations.append({
                    "station_id": node.get("station_id"),
                    "name": node.get("name"),
                    "lines": node.get("lines"),
                })

            legs = []
            interchange_points = []
            total_time = 0

            for i, rel in enumerate(rels):
                travel_time = rel.get("travel_time_min", 0) or 0
                total_time += travel_time

                leg = {
                    "from": stations[i]["station_id"],
                    "from_name": stations[i]["name"],
                    "to": stations[i + 1]["station_id"],
                    "to_name": stations[i + 1]["name"],
                    "relationship": rel.type,
                    "line": rel.get("line"),
                    "travel_time_min": travel_time,
                }

                legs.append(leg)

                if rel.type == "INTERCHANGE_TO":
                    interchange_points.append({
                        "from": stations[i]["station_id"],
                        "from_name": stations[i]["name"],
                        "to": stations[i + 1]["station_id"],
                        "to_name": stations[i + 1]["name"],
                    })

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "stations": stations,
                "interchange_points": interchange_points,
                "total_time_min": total_time,
                "legs": legs,
            }


# ── DELAY RIPPLE ANALYSIS ─────────────────────────────────────────────────────

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    """
    Find all stations within N hops of a delayed or disrupted station.
    Works on both metro and national rail networks.

    Args:
        delayed_station_id: e.g. "NR03" or "MS01"
        hops:               how many connections out to search (default 2)

    Returns:
        List of dicts: {station_id, name, hops_away, lines_affected}
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (start {station_id: $delayed_station_id})
                MATCH p = (start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..5]-(affected)
                WHERE affected.station_id <> $delayed_station_id
                RETURN DISTINCT
                    affected.station_id AS station_id,
                    affected.name AS name,
                    length(p) AS hops_away,
                    affected.lines AS lines_affected
                ORDER BY hops_away, station_id
                """,
                delayed_station_id=delayed_station_id,
            )

            rows = []
            for row in result:
                if row["hops_away"] <= hops:
                    rows.append(dict(row))

            return rows


# ── STATION CONNECTIONS ───────────────────────────────────────────────────────

def query_station_connections(station_id: str) -> list[dict]:
    """
    List all direct connections from a given station.

    Args:
        station_id: e.g. "MS01" or "NR01"
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (s {station_id: $station_id})-[r:METRO_LINK|RAIL_LINK|INTERCHANGE_TO]-(next)
                RETURN DISTINCT
                    next.station_id AS station_id,
                    next.name AS name,
                    type(r) AS relationship,
                    r.line AS line,
                    r.travel_time_min AS travel_time_min
                ORDER BY station_id
                """,
                station_id=station_id,
            )

            return [dict(row) for row in result]