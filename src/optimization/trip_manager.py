
from __future__ import annotations
from typing import List, Optional, Any
from datetime import datetime, timedelta

from src.core.trip_models import Trip, TripMetrics, Segment
from src.data_layer.trip_repo import (migrate, get_trip, replace_plan, list_locked_segments, log_replan)
from src.data_layer.gps_feed import get_current_city
try:
    from src.core.config import FREEZE_MINUTES, REPLAN_BENEFIT_THRESHOLD_PCT
except Exception:
    FREEZE_MINUTES = 90
    REPLAN_BENEFIT_THRESHOLD_PCT = 7.5

def _normalize_route_obj(route: Any) -> TripMetrics:
    # Defensive extraction from unknown route objects
    total_rev = float(getattr(route, 'total_revenue', getattr(route, 'revenue', 0.0)) or 0.0)
    total_km  = float(getattr(route, 'total_distance', getattr(route, 'distance_km', 0.0)) or 0.0)
    hours     = float(getattr(route, 'estimated_time_hours', getattr(route, 'estimated_time', 0.0)) or 0.0)
    if hours <= 0 and hasattr(route, 'revenue_per_hour'):
        rph = float(getattr(route, 'revenue_per_hour') or 0.0)
        hours = (total_rev / rph) if rph > 0 else 0.0
    return TripMetrics(km=total_km, hours=hours, revenue=total_rev)

def _select_best(routes: List[Any]) -> Optional[Any]:
    if not routes:
        return None
    def key(r: Any):
        m = _normalize_route_obj(r)
        return (m.revenue_per_day, getattr(r, 'revenue_per_hour', 0.0), m.km)
    return sorted(routes, key=key, reverse=True)[0]

def replan_trip(trip_id: int, now: Optional[str] = None) -> Optional[TripMetrics]:
    migrate()
    trip = get_trip(trip_id)
    if not trip:
        raise ValueError(f"Trip {trip_id} not found")

    # current city from GPS (fallback на гараж)
    current_city = get_current_city(trip.vehicle_id) or trip.garage_city
    start_time_iso = now or datetime.utcnow().isoformat(timespec="seconds")

    # import builder lazily
    try:
        from src.optimization.legacy.route_builder_time import build_routes
    except Exception as e:
        raise RuntimeError(f"Cannot import builder: {e}")

    locked = list_locked_segments(trip_id)

    # NOTE: depending on builder API, pass parameters accordingly
    try:
        routes = build_routes(
            start_city=current_city,
            end_city=trip.garage_city,   # use as anchor for forecast
            start_time=start_time_iso,
            max_depth=7,
            max_routes=10,
            locked_segments=[(s.loading_city, s.unloading_city) for s in locked]
        )
    except TypeError:
        # fallback: older signature without locked_segments
        routes = build_routes(
            start_city=current_city,
            end_city=trip.garage_city,
            start_time=start_time_iso,
            max_depth=7,
            max_routes=10
        )

    best = _select_best(routes)
    if not best:
        log_replan(trip_id, accepted=False, delta_revenue_per_day=0.0, reason="no_routes")
        return None

    new_plan = _normalize_route_obj(best)

    # сравнение с текущим планом
    delta_rpd = new_plan.revenue_per_day - trip.plan_revenue_per_day
    threshold = trip.benefit_threshold_pct if trip.benefit_threshold_pct else REPLAN_BENEFIT_THRESHOLD_PCT
    accept = (delta_rpd >= (trip.plan_revenue_per_day * (threshold/100.0))) or (trip.plan_revenue_per_day == 0)

    # простой «каркас» сегментов: если builder отдаёт сегменты, используем; иначе — placeholder
    segs: List[Segment] = []
    if hasattr(best, 'segments'):
        for i, seg in enumerate(getattr(best, 'segments')):
            try:
                segs.append(Segment(
                    trip_id=trip_id,
                    seq=i+1,
                    loading_city=str(getattr(seg, 'from_city', getattr(seg, 'loading_city', ''))),
                    unloading_city=str(getattr(seg, 'to_city', getattr(seg, 'unloading_city', ''))),
                    loading_dt=getattr(seg, 'loading_dt', None),
                    unloading_dt=getattr(seg, 'unloading_dt', None),
                    empty_km_before=float(getattr(seg, 'empty_km_before', 0.0) or 0.0),
                    distance_km=float(getattr(seg, 'distance_km', getattr(seg, 'km', 0.0)) or 0.0),
                    revenue=float(getattr(seg, 'revenue', 0.0) or 0.0),
                    status='planned',
                    locked=0,
                    note='auto-plan'
                ))
            except Exception:
                continue

    if accept:
        replace_plan(trip_id, segs, new_plan)
    log_replan(trip_id, accepted=accept, delta_revenue_per_day=delta_rpd, reason="auto")
    return new_plan if accept else None
