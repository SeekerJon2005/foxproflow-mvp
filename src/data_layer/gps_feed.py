
from __future__ import annotations
from typing import Optional, Tuple
from datetime import datetime
import sqlite3
from pathlib import Path

# DB path discovery (SQLite) — fallback if config is unavailable.
def _db_path() -> str:
    try:
        from src.core.config import DB_PATH  # type: ignore
        return DB_PATH  # e.g. 'data/app.db'
    except Exception:
        return str(Path.cwd() / 'data' / 'app.db')

def _conn() -> sqlite3.Connection:
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn

def migrate_gps() -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS gps_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT NOT NULL,
            ts TEXT NOT NULL,
            lat REAL,
            lon REAL,
            city TEXT,
            speed_kmh REAL
        );
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_gps_vehicle_ts ON gps_positions(vehicle_id, ts DESC);')
    conn.commit()
    conn.close()

def set_current_position(vehicle_id: str, city: str, lat: float = None, lon: float = None,
                         speed_kmh: float = None, ts: Optional[str] = None) -> None:
    migrate_gps()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO gps_positions(vehicle_id, ts, lat, lon, city, speed_kmh) VALUES(?,?,?,?,?,?)',
        (vehicle_id, ts or datetime.utcnow().isoformat(timespec="seconds"), lat, lon, city, speed_kmh)
    )
    conn.commit()
    conn.close()

def get_current_city(vehicle_id: str) -> Optional[str]:
    migrate_gps()
    conn = _conn()
    cur = conn.cursor()
    row = cur.execute(
        'SELECT city FROM gps_positions WHERE vehicle_id = ? ORDER BY ts DESC LIMIT 1', (vehicle_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None
