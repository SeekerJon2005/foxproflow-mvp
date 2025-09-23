
import sqlite3
import logging
import traceback
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from config import DATABASE_PATH

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('Database')
logger.setLevel(logging.DEBUG)

def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cursor.fetchall()]
    return column in cols

def init_database():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        # Core table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS freights (
            id TEXT PRIMARY KEY,
            loading_city TEXT NOT NULL,
            unloading_city TEXT NOT NULL,
            distance REAL NOT NULL,
            cargo TEXT NOT NULL,
            weight REAL NOT NULL,
            volume REAL NOT NULL,
            body_type TEXT NOT NULL,
            loading_date TEXT NOT NULL,
            loading_dt TEXT,              -- NEW: ISO datetime for time-aware planning
            revenue_rub REAL NOT NULL,
            profit_per_km REAL NOT NULL,
            loading_lat REAL,
            loading_lon REAL,
            unloading_lat REAL,
            unloading_lon REAL,
            loading_region TEXT,
            unloading_region TEXT
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS distances (
            city1 TEXT NOT NULL,
            city2 TEXT NOT NULL,
            distance REAL NOT NULL,
            PRIMARY KEY (city1, city2)
        )
        ''')
        # Add missing columns if DB created by older code
        if not _column_exists(cursor, "freights", "loading_dt"):
            cursor.execute("ALTER TABLE freights ADD COLUMN loading_dt TEXT")
        # Indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_loading_city ON freights(loading_city)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_unloading_city ON freights(unloading_city)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_body_type ON freights(body_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_loading_dt ON freights(loading_dt)')
        # Market analytics
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_stats (
            orig_city TEXT NOT NULL,
            dest_city TEXT NOT NULL,
            body_type TEXT NOT NULL,
            day_of_week INTEGER NOT NULL,
            samples INTEGER NOT NULL,
            p20_rubkm REAL NOT NULL,
            p50_rubkm REAL NOT NULL,
            p80_rubkm REAL NOT NULL,
            loads_per_day REAL NOT NULL,
            avg_distance REAL NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (orig_city, dest_city, body_type, day_of_week)
        )
        ''')
        # Surge events
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS rate_surge_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            orig_city TEXT NOT NULL,
            dest_city TEXT NOT NULL,
            body_type TEXT NOT NULL,
            freight_id TEXT,
            rub_per_km REAL NOT NULL,
            baseline_rub_per_km REAL NOT NULL,
            uplift REAL NOT NULL
        )
        ''')
        conn.commit()
        logger.info("База данных инициализирована")
    except sqlite3.Error as e:
        logger.error(f"Ошибка инициализации базы данных: {str(e)}")
        logger.debug(traceback.format_exc())
    finally:
        if conn:
            conn.close()

def insert_freights_batch(freights: List[Any]):
    if not freights:
        logger.warning("Попытка вставки пустого списка грузов")
        return
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        data = []
        for freight in freights:
            loading_city = freight.loading_points[0] if freight.loading_points else ""
            unloading_city = freight.unloading_points[0] if freight.unloading_points else ""
            body_type = (freight.body_type or "n/a").lower()
            profit_per_km = (freight.revenue_rub or 0.0) / freight.distance if freight.distance > 0 else 0.0
            data.append((
                freight.id,
                loading_city,
                unloading_city,
                freight.distance,
                freight.cargo,
                freight.weight,
                freight.volume,
                body_type,
                freight.loading_date,
                getattr(freight, "loading_dt", None),
                freight.revenue_rub or 0.0,
                profit_per_km,
                freight.loading_lat,
                freight.loading_lon,
                freight.unloading_lat,
                freight.unloading_lon,
                freight.loading_region,
                freight.unloading_region
            ))
        cursor.executemany('''
        INSERT OR REPLACE INTO freights 
        (id, loading_city, unloading_city, distance, cargo, weight, volume, body_type, loading_date, loading_dt, 
         revenue_rub, profit_per_km, loading_lat, loading_lon, unloading_lat, unloading_lon, loading_region, unloading_region)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', data)
        conn.commit()
        logger.info(f"Вставлено {len(freights)} грузов в базу данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {str(e)}")
        if freights:
            logger.debug(f"Пример данных: {freights[0].dict() if hasattr(freights[0],'dict') else str(freights[0])}")
        logger.debug(traceback.format_exc())
    finally:
        if conn:
            conn.close()

def upsert_market_stats(rows: List[Tuple]):
    """rows: (orig, dest, body_type, day_of_week, samples, p20, p50, p80, loads_per_day, avg_distance, updated_at)"""
    if not rows:
        return
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.executemany('''
        INSERT INTO market_stats
        (orig_city, dest_city, body_type, day_of_week, samples, p20_rubkm, p50_rubkm, p80_rubkm, loads_per_day, avg_distance, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(orig_city, dest_city, body_type, day_of_week) DO UPDATE SET
            samples=excluded.samples,
            p20_rubkm=excluded.p20_rubkm,
            p50_rubkm=excluded.p50_rubkm,
            p80_rubkm=excluded.p80_rubkm,
            loads_per_day=excluded.loads_per_day,
            avg_distance=excluded.avg_distance,
            updated_at=excluded.updated_at
        ''', rows)
        conn.commit()
        logger.info(f"Обновлено записей market_stats: {len(rows)}")
    except Exception as e:
        logger.error(f"Ошибка upsert market_stats: {e}")
        logger.debug(traceback.format_exc())
    finally:
        if conn: conn.close()

def get_guaranteed_rate(orig: str, dest: str, body_type: str, day_of_week: int) -> Optional[float]:
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        bt = (body_type or "n/a").lower()
        for dow in (day_of_week, 7):  # try exact DOW, then 7=any
            cursor.execute('''
                SELECT p20_rubkm FROM market_stats 
                WHERE orig_city=? AND dest_city=? AND body_type=? AND day_of_week=?
            ''', (orig, dest, bt, dow))
            row = cursor.fetchone()
            if row and row[0] is not None:
                return float(row[0])
        # fallback: any dest from orig by body type
        cursor.execute('''
            SELECT p20_rubkm FROM market_stats 
            WHERE orig_city=? AND body_type=? ORDER BY samples DESC LIMIT 1
        ''', (orig, bt))
        row = cursor.fetchone()
        if row:
            return float(row[0])
        return None
    except Exception as e:
        logger.error(f"Ошибка get_guaranteed_rate: {e}")
        logger.debug(traceback.format_exc())
        return None
    finally:
        if conn: conn.close()

def insert_rate_surge_event(ts: str, orig: str, dest: str, body_type: str, freight_id: Optional[str],
                            rub_per_km: float, baseline: float, uplift: float):
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rate_surge_events (ts, orig_city, dest_city, body_type, freight_id, rub_per_km, baseline_rub_per_km, uplift)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ts, orig, dest, (body_type or "n/a").lower(), freight_id, rub_per_km, baseline, uplift))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка записи всплеска ставки: {e}")
        logger.debug(traceback.format_exc())
    finally:
        if conn: conn.close()

def fetch_recent_surge_events(limit: int = 20) -> List[Dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute('''SELECT * FROM rate_surge_events ORDER BY ts DESC LIMIT ?''', (limit,))
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка чтения surge_events: {e}")
        return []
    finally:
        if conn: conn.close()

def load_suitable_freights(max_weight, max_volume, trailer_type):
    logger.info(
        f"Загрузка подходящих грузов: max_weight={max_weight}, max_volume={max_volume}, trailer_type={trailer_type}")
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        patterns = {
            'тент': ['%тент%', '%закр%'],
            'термос': ['%терм%', '%изотерм%', '%закр%'],
            'реф': ['%реф%', '%рефрижератор%']
        }
        if (trailer_type or '').lower() in patterns:
            search_patterns = patterns[trailer_type.lower()]
        else:
            search_patterns = [f'%{(trailer_type or "").lower()}%']
        query = '''
        SELECT * FROM freights 
        WHERE weight <= ? AND volume <= ? 
        AND loading_lat IS NOT NULL
        AND loading_lon IS NOT NULL
        AND unloading_lat IS NOT NULL
        AND unloading_lon IS NOT NULL
        AND (''' + " OR ".join(["body_type LIKE ?"] * len(search_patterns)) + ")"
        params = [max_weight, max_volume] + search_patterns
        cursor.execute(query, tuple(params))
        freights = []
        batch_size = 5000
        while True:
            batch = cursor.fetchmany(batch_size)
            if not batch:
                break
            for row in batch:
                freights.append(dict(row))
        logger.info(f"Всего подходящих грузов: {len(freights)}")
        return freights
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {str(e)}")
        logger.debug(traceback.format_exc())
        return []
    finally:
        if conn:
            conn.close()

def get_database_stats():
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        stats = {}
        cursor.execute("SELECT COUNT(*) FROM freights")
        stats['total_freights'] = cursor.fetchone()[0]
        cursor.execute("SELECT body_type, COUNT(*) FROM freights GROUP BY body_type ORDER BY COUNT(*) DESC LIMIT 10")
        stats['body_types'] = cursor.fetchall()
        cursor.execute("SELECT MIN(weight), MAX(weight), AVG(weight) FROM freights")
        stats['weight_stats'] = cursor.fetchone()
        return stats
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения статистики: {str(e)}")
        logger.debug(traceback.format_exc())
        return {}
    finally:
        if conn:
            conn.close()
