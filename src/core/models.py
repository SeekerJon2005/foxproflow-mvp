
from pydantic import BaseModel
from typing import List, Dict, Optional

class City(BaseModel):
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    region: Optional[str] = None

class Freight(BaseModel):
    id: str
    loading_points: List[str]
    unloading_points: List[str]
    distance: float
    cargo: str
    weight: float
    volume: float
    prices: Dict[str, float] = {}
    loading_date: str                      # original date string as in source
    loading_dt: Optional[str] = None       # ISO-8601 'YYYY-MM-DDTHH:MM:SS' (UTC or naive local)
    body_type: Optional[str] = "n/a"
    loading_method: Optional[str] = "n/a"
    possible_reload: Optional[str] = "n/a"
    details: Optional[List[str]] = []
    revenue_rub: Optional[float] = None
    loading_lat: Optional[float] = None
    loading_lon: Optional[float] = None
    unloading_lat: Optional[float] = None
    unloading_lon: Optional[float] = None
    loading_region: Optional[str] = None
    unloading_region: Optional[str] = None

class RouteSegment(BaseModel):
    freight: Freight
    empty_run_before: float
    segment_time: float
    arrive_time: Optional[str] = None
    depart_time: Optional[str] = None

class Route(BaseModel):
    segments: List[RouteSegment]
    total_distance: float
    total_revenue: float
    total_profit: float
    profit_per_hour: float
    estimated_time: float
    total_time_days: float
    empty_run_after: float = 0.0

    @property
    def revenue_per_km(self) -> float:
        return self.total_revenue / self.total_distance if self.total_distance > 0 else 0.0
