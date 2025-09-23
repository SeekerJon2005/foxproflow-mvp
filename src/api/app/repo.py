from typing import Optional, Tuple, List, Any
from .db import fetch_all, fetch_one

BASE_SELECT = """
SELECT
  id, hash, loading_city, unloading_city, distance, cargo, weight, volume,
  body_type, loading_date, revenue_rub, profit_per_km,
  loading_lat, loading_lon, unloading_lat, unloading_lon,
  loading_region, unloading_region, parsed_at, session_id, source,
  usd_rate, eur_rate, fuel_price_avg,
  loading_region_trucks, loading_region_requests,
  unloading_region_trucks, unloading_region_requests
FROM freights_enriched
"""

def build_filters(
    origin: Optional[str], destination: Optional[str],
    date_from: Optional[str], date_to: Optional[str],
    body_type: Optional[str],
    min_weight: Optional[float], max_weight: Optional[float],
    min_volume: Optional[float], max_volume: Optional[float]
) -> Tuple[str, list]:
    where = ["1=1"]
    params: List[Any] = []

    if origin:
        where.append("loading_city ILIKE %s")
        params.append(f"%{origin}%")
    if destination:
        where.append("unloading_city ILIKE %s")
        params.append(f"%{destination}%")
    if date_from:
        where.append("loading_date >= %s")
        params.append(date_from)
    if date_to:
        where.append("loading_date <= %s")
        params.append(date_to)
    if body_type:
        where.append("body_type ILIKE %s")
        params.append(f"%{body_type}%")
    if min_weight is not None:
        where.append("weight >= %s")
        params.append(min_weight)
    if max_weight is not None:
        where.append("weight <= %s")
        params.append(max_weight)
    if min_volume is not None:
        where.append("volume >= %s")
        params.append(min_volume)
    if max_volume is not None:
        where.append("volume <= %s")
        params.append(max_volume)

    return " WHERE " + " AND ".join(where), params

def list_freights(
    origin: Optional[str], destination: Optional[str],
    date_from: Optional[str], date_to: Optional[str],
    body_type: Optional[str],
    min_weight: Optional[float], max_weight: Optional[float],
    min_volume: Optional[float], max_volume: Optional[float],
    limit: int, offset: int, order_by: str
):
    where_sql, params = build_filters(
        origin, destination, date_from, date_to, body_type,
        min_weight, max_weight, min_volume, max_volume
    )

    allowed_sort = {
        "parsed_at": "parsed_at DESC NULLS LAST",
        "loading_date": "loading_date DESC",
        "revenue": "revenue_rub DESC",
        "profit_per_km": "profit_per_km DESC"
    }
    order_sql = " ORDER BY " + allowed_sort.get(order_by, "parsed_at DESC NULLS LAST")

    count_sql = "SELECT COUNT(*) AS cnt FROM freights_enriched" + where_sql
    total = fetch_one(count_sql, tuple(params))["cnt"]

    paging_sql = f"{BASE_SELECT}{where_sql}{order_sql} LIMIT %s OFFSET %s"
    rows = fetch_all(paging_sql, tuple(params + [limit, offset]))
    return rows, total

def get_freight_by_id(fid: str):
    sql = BASE_SELECT + " WHERE id = %s LIMIT 1"
    return fetch_one(sql, (fid,))
