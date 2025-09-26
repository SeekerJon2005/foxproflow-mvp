from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

class FreightEnriched(BaseModel):
    id: Optional[str] = None
    hash: Optional[str] = None
    loading_city: Optional[str] = None
    unloading_city: Optional[str] = None
    distance: Optional[float] = None
    cargo: Optional[str] = None
    weight: Optional[float] = None
    volume: Optional[float] = None
    body_type: Optional[str] = None
    loading_date: Optional[datetime] = None
    revenue_rub: Optional[float] = None
    profit_per_km: Optional[float] = None
    loading_lat: Optional[float] = None
    loading_lon: Optional[float] = None
    unloading_lat: Optional[float] = None
    unloading_lon: Optional[float] = None
    loading_region: Optional[str] = None
    unloading_region: Optional[str] = None

    parsed_at: Optional[datetime] = None
    session_id: Optional[int] = None
    source: Optional[str] = None

    usd_rate: Optional[float] = None
    eur_rate: Optional[float] = None
    fuel_price_avg: Optional[float] = None
    loading_region_trucks: Optional[int] = None
    loading_region_requests: Optional[int] = None
    unloading_region_trucks: Optional[int] = None
    unloading_region_requests: Optional[int] = None

class FreightListResponse(BaseModel):
    items: List[FreightEnriched]
    total: int
    limit: int
    offset: int
