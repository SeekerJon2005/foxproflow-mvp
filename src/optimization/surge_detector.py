
from typing import List
from datetime import datetime
from models import Freight
from database import get_guaranteed_rate, insert_rate_surge_event
from config import SURGE_THRESHOLD_MULTIPLIER

def check_and_log_surges(freights: List[Freight]) -> int:
    """Checks each freight vs guaranteed p20 and logs surge events when >= +30%.
       Returns number of surge events logged."""
    if not freights:
        return 0
    cnt = 0
    for f in freights:
        try:
            loading_city = f.loading_points[0] if f.loading_points else None
            unloading_city = f.unloading_points[0] if f.unloading_points else None
            if not loading_city or not unloading_city or not f.revenue_rub or not f.distance:
                continue
            rubkm = f.revenue_rub / f.distance if f.distance else 0.0
            # crude DOW: try from loading_date
            dow = 7
            if f.loading_date and len(f.loading_date) >= 10:
                y, m, d = int(f.loading_date[:4]), int(f.loading_date[5:7]), int(f.loading_date[8:10])
                import datetime as _dt
                dow = _dt.date(y, m, d).weekday()
            baseline = get_guaranteed_rate(loading_city, unloading_city, f.body_type or "n/a", dow)
            if not baseline or baseline <= 0:
                continue
            if rubkm >= SURGE_THRESHOLD_MULTIPLIER * baseline:
                uplift = rubkm / baseline
                insert_rate_surge_event(
                    ts=datetime.utcnow().isoformat(),
                    orig=loading_city,
                    dest=unloading_city,
                    body_type=f.body_type or "n/a",
                    freight_id=f.id,
                    rub_per_km=rubkm,
                    baseline=baseline,
                    uplift=uplift
                )
                cnt += 1
        except Exception:
            continue
    return cnt
