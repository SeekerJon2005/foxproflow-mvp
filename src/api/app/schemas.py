from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class FreightEnriched(BaseModel):
    id: str
    hash: Optional[str] = None
    loading_city: str
    unloading_city: str
    distance: float
    cargo: str
    weight: float
    volume: float
    body_type: str
    loading_date: str
    revenue_rub: float
    profit_per_km: float
    loading_lat: Optional[float] = None
    loading_lon: Optional[float] = None
    unloading_lat: Optional[float] = None
    unloading_lon: Optional[float] = None
    loading_region: Optional[str] = None
    unloading_region: Optional[str] = None

    # ✅ поменяли str → datetime
    parsed_at: Optional[datetime] = None

    session_id: Optional[str] = None
    source: Optional[str] = None

    usd_rate: Optional[float] = None
    eur_rate: Optional[float] = None
    fuel_price_avg: Optional[float] = None
    loading_region_trucks: Optional[int] = None
    loading_region_requests: Optional[int] = None
    unloading_region_trucks: Optional[int] = None
    unloading_region_requests: Optional[int] = None

class FreightListResponse(BaseModel):
    items: list[FreightEnriched]
    total: int
    limit: int
    offset: int
