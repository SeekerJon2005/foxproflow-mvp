
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class TripMetrics:
    km: float = 0.0
    hours: float = 0.0
    revenue: float = 0.0

    @property
    def revenue_per_hour(self) -> float:
        return self.revenue / self.hours if self.hours > 0 else 0.0

    @property
    def revenue_per_day(self) -> float:
        return self.revenue_per_hour * 24.0

@dataclass
class Segment:
    trip_id: Optional[int]
    seq: int
    loading_city: str
    unloading_city: str
    loading_dt: Optional[str] = None   # ISO-8601 string
    unloading_dt: Optional[str] = None # ISO-8601 string
    empty_km_before: float = 0.0
    distance_km: float = 0.0
    revenue: float = 0.0
    status: str = "planned"  # planned|booked|in_transit|done|canceled
    locked: int = 0          # 1=locked, 0=unlocked
    note: str = ""

@dataclass
class Trip:
    id: Optional[int]
    vehicle_id: str
    garage_city: str
    start_dt: str             # ISO-8601
    end_target_dt: Optional[str] = None
    status: str = "active"    # active|paused|done|canceled
    freeze_until_dt: Optional[str] = None
    benefit_threshold_pct: float = 7.5
    replan_max_per_day: int = 6

    metrics_actual: TripMetrics = field(default_factory=TripMetrics)
    metrics_plan: TripMetrics = field(default_factory=TripMetrics)

    plan_revenue_per_day: float = 0.0
    last_replan_at: Optional[str] = None
