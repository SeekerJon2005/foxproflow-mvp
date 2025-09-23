
from __future__ import annotations
from typing import List, Optional, Iterable
from datetime import datetime
import sqlite3
from pathlib import Path

from src.core.trip_models import Trip, TripMetrics, Segment

def _db_path() -> str:
    try:
        from src.core.config import DB_PATH  # type: ignore
        return DB_PATH
    except Exception:
        return str(Path.cwd() / 'data' / 'app.db')

def _conn() -> sqlite3.Connection:
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn

def migrate() -> None:
    conn = _conn()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT NOT NULL,
            garage_city TEXT NOT NULL,
            start_dt TEXT NOT NULL,
            end_target_dt TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            freeze_until_dt TEXT,
            benefit_threshold_pct REAL NOT NULL DEFAULT 7.5,
            replan_max_per_day INTEGER NOT NULL DEFAULT 6,
            actual_km REAL NOT NULL DEFAULT 0,
            actual_hours REAL NOT NULL DEFAULT 0,
            actual_revenue REAL NOT NULL DEFAULT 0,
            plan_km REAL NOT NULL DEFAULT 0,
            plan_hours REAL NOT NULL DEFAULT 0,
            plan_revenue REAL NOT NULL DEFAULT 0,
            plan_revenue_per_day REAL NOT NULL DEFAULT 0,
            last_replan_at TEXT,
            updated_at TEXT
        );
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS trip_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            loading_city TEXT NOT NULL,
            unloading_city TEXT NOT NULL,
            loading_dt TEXT,
            unloading_dt TEXT,
            empty_km_before REAL NOT NULL DEFAULT 0,
            distance_km REAL NOT NULL DEFAULT 0,
            revenue REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'planned', -- planned|booked|in_transit|done|canceled
            locked INTEGER NOT NULL DEFAULT 0,      -- 1=locked
            note TEXT,
            FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
        );
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trip_segments_trip_seq ON trip_segments(trip_id, seq);')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS replan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            accepted INTEGER NOT NULL,
            delta_revenue_per_day REAL NOT NULL,
            reason TEXT,
            FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
        );
    ''')

    conn.commit()
    conn.close()

def create_trip(vehicle_id: str, garage_city: str, start_dt: str, end_target_dt: Optional[str] = None,
                benefit_threshold_pct: float = 7.5, replan_max_per_day: int = 6) -> int:
    migrate()
    conn = _conn()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO trips(vehicle_id, garage_city, start_dt, end_target_dt,
                          benefit_threshold_pct, replan_max_per_day, updated_at)
        VALUES(?,?,?,?,?,?,?)
    ''', (vehicle_id, garage_city, start_dt, end_target_dt, benefit_threshold_pct, replan_max_per_day, datetime.utcnow().isoformat(timespec="seconds")))
    trip_id = cur.lastrowid
    conn.commit()
    conn.close()
    return trip_id

def get_trip(trip_id: int) -> Optional[Trip]:
    migrate()
    conn = _conn()
    cur = conn.cursor()
    row = cur.execute('''
        SELECT id, vehicle_id, garage_city, start_dt, end_target_dt, status, freeze_until_dt,
               benefit_threshold_pct, replan_max_per_day,
               actual_km, actual_hours, actual_revenue,
               plan_km, plan_hours, plan_revenue, plan_revenue_per_day,
               last_replan_at
        FROM trips WHERE id=?
    ''', (trip_id,)).fetchone()
    conn.close()
    if not row:
        return None
    (tid, vehicle_id, garage_city, start_dt, end_target_dt, status, freeze_until_dt,
     benefit_threshold_pct, replan_max_per_day,
     a_km, a_h, a_rev, p_km, p_h, p_rev, p_rpd, last_replan_at) = row
    return Trip(
        id=tid, vehicle_id=vehicle_id, garage_city=garage_city,
        start_dt=start_dt, end_target_dt=end_target_dt, status=status, freeze_until_dt=freeze_until_dt,
        benefit_threshold_pct=benefit_threshold_pct, replan_max_per_day=replan_max_per_day,
        metrics_actual=TripMetrics(a_km, a_h, a_rev),
        metrics_plan=TripMetrics(p_km, p_h, p_rev),
        plan_revenue_per_day=p_rpd, last_replan_at=last_replan_at
    )

def update_trip_actual(trip_id: int, km: float, hours: float, revenue: float) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute('''
        UPDATE trips
           SET actual_km=?, actual_hours=?, actual_revenue=?, updated_at=?
         WHERE id=?
    ''', (km, hours, revenue, datetime.utcnow().isoformat(timespec="seconds"), trip_id))
    conn.commit()
    conn.close()

def replace_plan(trip_id: int, segments: List[Segment], plan_metrics: TripMetrics) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM trip_segments WHERE trip_id=? AND status IN ("planned")', (trip_id,))
    for s in segments:
        cur.execute('''
            INSERT INTO trip_segments(trip_id, seq, loading_city, unloading_city, loading_dt, unloading_dt,
                                      empty_km_before, distance_km, revenue, status, locked, note)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (trip_id, s.seq, s.loading_city, s.unloading_city, s.loading_dt, s.unloading_dt,
              s.empty_km_before, s.distance_km, s.revenue, s.status, s.locked, s.note))
    cur.execute('''
        UPDATE trips
           SET plan_km=?, plan_hours=?, plan_revenue=?, plan_revenue_per_day=?, last_replan_at=?, updated_at=?
         WHERE id=?
    ''', (plan_metrics.km, plan_metrics.hours, plan_metrics.revenue, plan_metrics.revenue_per_day,
          datetime.utcnow().isoformat(timespec="seconds"), datetime.utcnow().isoformat(timespec="seconds"), trip_id))
    conn.commit()
    conn.close()

def list_locked_segments(trip_id: int) -> List[Segment]:
    conn = _conn()
    cur = conn.cursor()
    rows = cur.execute('''
        SELECT seq, loading_city, unloading_city, loading_dt, unloading_dt,
               empty_km_before, distance_km, revenue, status, locked, note
        FROM trip_segments
        WHERE trip_id=? AND locked=1 AND status IN ("planned","booked","in_transit")
        ORDER BY seq ASC
    ''', (trip_id,)).fetchall()
    conn.close()
    result: List[Segment] = []
    for (seq, lc, uc, ldt, udt, ekm, dkm, rev, status, locked, note) in rows:
        result.append(Segment(trip_id=trip_id, seq=seq, loading_city=lc, unloading_city=uc,
                              loading_dt=ldt, unloading_dt=udt, empty_km_before=ekm,
                              distance_km=dkm, revenue=rev, status=status, locked=locked, note=note))
    return result

def log_replan(trip_id: int, accepted: bool, delta_revenue_per_day: float, reason: str = "") -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO replan_log(trip_id, ts, accepted, delta_revenue_per_day, reason)
        VALUES(?,?,?,?,?)
    ''', (trip_id, datetime.utcnow().isoformat(timespec="seconds"), 1 if accepted else 0, delta_revenue_per_day, reason))
    conn.commit()
    conn.close()
