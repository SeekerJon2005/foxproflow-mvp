
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import sqlite3
from collections import defaultdict
from config import DATABASE_PATH, MARKET_LOOKBACK_DAYS, MARKET_MIN_SAMPLES

def _percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals)-1) * p
    f = int(k)
    c = min(f+1, len(sorted_vals)-1)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[f] * (c-k)
    d1 = sorted_vals[c] * (k-f)
    return d0 + d1

def rebuild_market_stats(lookback_days: int = MARKET_LOOKBACK_DAYS) -> int:
    """Aggregate freights -> market_stats for last N days.
       Returns number of rows written."""
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # Load raw rows
    cur.execute("""
        SELECT loading_city, unloading_city, body_type, distance, revenue_rub, loading_date
        FROM freights
        WHERE revenue_rub IS NOT NULL AND distance > 0
    """)
    rows = cur.fetchall()
    conn.close()

    # Filter by date if possible (loading_date is TEXT YYYY-MM-DD)
    prepared = []
    for r in rows:
        try:
            if r['loading_date'] and len(r['loading_date']) >= 10:
                dt = datetime(int(r['loading_date'][:4]), int(r['loading_date'][5:7]), int(r['loading_date'][8:10]))
                if dt < cutoff:
                    continue
        except Exception:
            pass
        prepared.append(r)

    # Group and compute
    groups: Dict[Tuple[str, str, str, int], Dict[str, Any]] = defaultdict(lambda: {
        'rubkm': [], 'dists': [], 'count_by_day': defaultdict(int)
    })
    for r in prepared:
        orig = r['loading_city']; dest = r['unloading_city']; bt = (r['body_type'] or 'n/a').lower()
        try:
            if r['loading_date'] and len(r['loading_date']) >= 10:
                dt = datetime(int(r['loading_date'][:4]), int(r['loading_date'][5:7]), int(r['loading_date'][8:10]))
                dow = dt.weekday()
                key = (orig, dest, bt, dow)
            else:
                key = (orig, dest, bt, 7)  # 7 = any
            rubkm = float(r['revenue_rub']) / float(r['distance']) if r['distance'] else 0.0
            groups[key]['rubkm'].append(rubkm)
            groups[key]['dists'].append(float(r['distance']))
            if r['loading_date'] and len(r['loading_date']) >= 10:
                groups[key]['count_by_day'][r['loading_date']] += 1
        except Exception:
            continue

    # Prepare upserts
    from database import upsert_market_stats
    out_rows = []
    ts = datetime.utcnow().isoformat()
    for key, bag in groups.items():
        orig, dest, bt, dow = key
        vals = sorted(v for v in bag['rubkm'] if v > 0)
        if len(vals) < max(5, MARKET_MIN_SAMPLES//2):
            continue
        p20 = _percentile(vals, 0.20)
        p50 = _percentile(vals, 0.50)
        p80 = _percentile(vals, 0.80)
        avg_dist = sum(bag['dists'])/len(bag['dists']) if bag['dists'] else 0.0
        loads_per_day = 0.0
        if bag['count_by_day']:
            loads_per_day = sum(bag['count_by_day'].values()) / max(1, len(bag['count_by_day']))
        out_rows.append((orig, dest, bt, dow, len(vals), p20, p50, p80, loads_per_day, avg_dist, ts))
    upsert_market_stats(out_rows)
    return len(out_rows)
