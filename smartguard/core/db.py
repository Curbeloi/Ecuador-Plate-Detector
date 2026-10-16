"""Base de datos SQLite: registro de vehículos, eventos de acceso y conteos.

Cada hilo abre su propia ``Database`` (sqlite3 no comparte conexiones entre hilos); el modo
WAL permite que la interfaz lea mientras el hilo de video escribe.
"""

import sqlite3
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path

from smartguard.vision.ecuador import canonical

AUTHORIZED, BLOCKED, UNKNOWN = "authorized", "blocked", "unknown"
DECISION_LABELS = {AUTHORIZED: "Autorizado", BLOCKED: "Bloqueado", UNKNOWN: "No registrado"}
FIREARM, BLADE = "firearm", "blade"
WEAPON_LABELS = {FIREARM: "Arma de fuego", BLADE: "Arma blanca"}
PENDING, CONFIRMED, FALSE_ALARM = "pending", "confirmed", "false_alarm"
REVIEW_LABELS = {PENDING: "Sin revisar", CONFIRMED: "Amenaza confirmada", FALSE_ALARM: "Falsa alarma"}

_SCHEMA = """
CREATE TABLE vehicles (
    id INTEGER PRIMARY KEY,
    plate TEXT NOT NULL UNIQUE,
    owner_name TEXT NOT NULL DEFAULT '',
    owner_id_number TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    brand TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '',
    year TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'authorized' CHECK (status IN ('authorized', 'blocked')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE plate_events (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    plate TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    confidence REAL NOT NULL,
    vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
    decision TEXT NOT NULL CHECK (decision IN ('authorized', 'blocked', 'unknown')),
    snapshot_path TEXT NOT NULL DEFAULT '',
    crop_path TEXT NOT NULL DEFAULT '',
    camera TEXT NOT NULL DEFAULT ''
);
CREATE INDEX plate_events_ts ON plate_events(ts);
CREATE INDEX plate_events_plate ON plate_events(plate);
CREATE TABLE count_events (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    camera TEXT NOT NULL,
    label TEXT NOT NULL,
    track_id INTEGER NOT NULL,
    direction TEXT NOT NULL,
    image_path TEXT NOT NULL DEFAULT ''
);
CREATE INDEX count_events_ts ON count_events(ts);
"""
_WEAPONS_SCHEMA = """
CREATE TABLE weapon_events (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    camera TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('firearm', 'blade')),
    confidence REAL NOT NULL,
    snapshot_path TEXT NOT NULL DEFAULT '',
    crop_path TEXT NOT NULL DEFAULT '',
    review TEXT NOT NULL DEFAULT 'pending' CHECK (review IN ('pending', 'confirmed', 'false_alarm')),
    reviewed_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX weapon_events_ts ON weapon_events(ts);
"""
_MIGRATIONS = [_SCHEMA, _WEAPONS_SCHEMA]
"""Cada elemento lleva la base de la versión ``i`` a la ``i + 1`` (``PRAGMA user_version``)."""


def now_ts() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


@dataclass
class Vehicle:
    plate: str
    owner_name: str = ""
    owner_id_number: str = ""
    unit: str = ""
    """Casa/departamento del propietario dentro del condominio."""
    phone: str = ""
    brand: str = ""
    model: str = ""
    color: str = ""
    year: str = ""
    status: str = AUTHORIZED
    notes: str = ""
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class PlateEvent:
    ts: str
    plate: str
    raw_text: str
    confidence: float
    decision: str
    vehicle_id: int | None = None
    snapshot_path: str = ""
    crop_path: str = ""
    camera: str = ""
    id: int | None = None


@dataclass
class WeaponEvent:
    ts: str
    camera: str
    kind: str
    confidence: float
    snapshot_path: str = ""
    crop_path: str = ""
    review: str = PENDING
    reviewed_at: str = ""
    id: int | None = None


_VEHICLE_FIELDS = [f.name for f in fields(Vehicle)]
_EVENT_FIELDS = [f.name for f in fields(PlateEvent)]
_WEAPON_FIELDS = [f.name for f in fields(WeaponEvent)]


class Database:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def _migrate(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        for i, script in enumerate(_MIGRATIONS[version:], start=version + 1):
            with self.conn:
                self.conn.executescript(script)
                self.conn.execute(f"PRAGMA user_version = {i}")

    def close(self) -> None:
        self.conn.close()

    # --- Vehículos -------------------------------------------------------------------------

    def save_vehicle(self, vehicle: Vehicle) -> Vehicle:
        """Inserta o actualiza (según ``vehicle.id``). La placa se guarda en forma canónica."""
        vehicle.plate = canonical(vehicle.plate)
        vehicle.updated_at = now_ts()
        values = {k: getattr(vehicle, k) for k in _VEHICLE_FIELDS if k not in ("id", "created_at")}
        with self.conn:
            if vehicle.id is None:
                vehicle.created_at = vehicle.updated_at
                values["created_at"] = vehicle.created_at
                cursor = self.conn.execute(
                    f"INSERT INTO vehicles ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
                    list(values.values()),
                )
                vehicle.id = cursor.lastrowid
            else:
                self.conn.execute(
                    f"UPDATE vehicles SET {', '.join(f'{k} = ?' for k in values)} WHERE id = ?",
                    [*values.values(), vehicle.id],
                )
        return vehicle

    def delete_vehicle(self, vehicle_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))

    def find_vehicle(self, plate: str) -> Vehicle | None:
        row = self.conn.execute("SELECT * FROM vehicles WHERE plate = ?", (canonical(plate),)).fetchone()
        return Vehicle(**dict(row)) if row else None

    def list_vehicles(self, search: str = "") -> list[Vehicle]:
        like = f"%{search.strip()}%"
        plate_like = f"%{canonical(search)}%"
        rows = self.conn.execute(
            """SELECT * FROM vehicles
               WHERE plate LIKE ? OR owner_name LIKE ? OR owner_id_number LIKE ? OR unit LIKE ?
               ORDER BY plate""",
            (plate_like, like, like, like),
        )
        return [Vehicle(**dict(row)) for row in rows]

    # --- Eventos de acceso -----------------------------------------------------------------

    def add_plate_event(self, event: PlateEvent) -> PlateEvent:
        values = {k: getattr(event, k) for k in _EVENT_FIELDS if k != "id"}
        with self.conn:
            cursor = self.conn.execute(
                f"INSERT INTO plate_events ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
                list(values.values()),
            )
        event.id = cursor.lastrowid
        return event

    def plate_events(
        self, search: str = "", start: str | None = None, end: str | None = None, limit: int | None = 200
    ) -> list[PlateEvent]:
        """Eventos más recientes primero. ``start``/``end`` son fechas ISO (``end`` exclusivo)."""
        query = "SELECT * FROM plate_events WHERE plate LIKE ?"
        params: list = [f"%{canonical(search)}%"]
        if start:
            query += " AND ts >= ?"
            params.append(start)
        if end:
            query += " AND ts < ?"
            params.append(end)
        query += " ORDER BY ts DESC, id DESC"
        if limit:
            query += f" LIMIT {int(limit)}"
        return [PlateEvent(**dict(row)) for row in self.conn.execute(query, params)]

    # --- Alertas de armas ------------------------------------------------------------------

    def add_weapon_event(self, event: WeaponEvent) -> WeaponEvent:
        values = {k: getattr(event, k) for k in _WEAPON_FIELDS if k != "id"}
        with self.conn:
            cursor = self.conn.execute(
                f"INSERT INTO weapon_events ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
                list(values.values()),
            )
        event.id = cursor.lastrowid
        return event

    def set_weapon_review(self, event_id: int, review: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE weapon_events SET review = ?, reviewed_at = ? WHERE id = ?", (review, now_ts(), event_id)
            )

    def weapon_events(
        self, start: str | None = None, end: str | None = None, review: str = "", limit: int | None = 500
    ) -> list[WeaponEvent]:
        query, params = "SELECT * FROM weapon_events WHERE 1 = 1", []
        for clause, value in (("ts >= ?", start), ("ts < ?", end), ("review = ?", review)):
            if value:
                query += f" AND {clause}"
                params.append(value)
        query += " ORDER BY ts DESC, id DESC"
        if limit:
            query += f" LIMIT {int(limit)}"
        return [WeaponEvent(**dict(row)) for row in self.conn.execute(query, params)]

    # --- Conteos ---------------------------------------------------------------------------

    def add_count_event(self, camera: str, label: str, track_id: int, direction: str) -> int:
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO count_events (ts, camera, label, track_id, direction) VALUES (?, ?, ?, ?, ?)",
                (now_ts(), camera, label, track_id, direction),
            )
        return cursor.lastrowid

    def set_count_image(self, event_id: int, image_path: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE count_events SET image_path = ? WHERE id = ?", (image_path, event_id))

    def count_events(self, start: str, end: str, label: str = "") -> list[sqlite3.Row]:
        query = "SELECT id, ts, camera, label, track_id, direction, image_path FROM count_events" \
                " WHERE ts >= ? AND ts < ?"
        params = [start, end]
        if label:
            query += " AND label = ?"
            params.append(label)
        return self.conn.execute(query + " ORDER BY ts DESC", params).fetchall()

    # --- Estadísticas ----------------------------------------------------------------------

    def decisions_per_day(self, start: str, end: str) -> dict[str, dict[str, int]]:
        """``{"2026-10-16": {"authorized": 3, "unknown": 1}, ...}``"""
        result: dict[str, dict[str, int]] = {}
        rows = self.conn.execute(
            """SELECT substr(ts, 1, 10) AS day, decision, COUNT(*) AS n FROM plate_events
               WHERE ts >= ? AND ts < ? GROUP BY day, decision""",
            (start, end),
        )
        for row in rows:
            result.setdefault(row["day"], {})[row["decision"]] = row["n"]
        return result

    def counts_per_day(self, start: str, end: str) -> dict[str, dict[str, int]]:
        """``{"2026-10-16": {"auto": 120, "persona": 45}, ...}``"""
        result: dict[str, dict[str, int]] = {}
        rows = self.conn.execute(
            """SELECT substr(ts, 1, 10) AS day, label, COUNT(*) AS n FROM count_events
               WHERE ts >= ? AND ts < ? GROUP BY day, label""",
            (start, end),
        )
        for row in rows:
            result.setdefault(row["day"], {})[row["label"]] = row["n"]
        return result

    def counts_per_hour(self, start: str, end: str) -> dict[int, int]:
        rows = self.conn.execute(
            """SELECT CAST(substr(ts, 12, 2) AS INTEGER) AS hour, COUNT(*) AS n FROM count_events
               WHERE ts >= ? AND ts < ? GROUP BY hour""",
            (start, end),
        )
        return {row["hour"]: row["n"] for row in rows}

    def counts_per_label(self, start: str, end: str) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT label, COUNT(*) AS n FROM count_events WHERE ts >= ? AND ts < ? GROUP BY label",
            (start, end),
        )
        return {row["label"]: row["n"] for row in rows}
