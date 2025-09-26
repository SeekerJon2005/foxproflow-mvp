from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

class FreightEnriched(BaseModel):
    id: Optional[str] = None
    loading_city: str
    unloading_city: str
    loading_dt: Optional[datetime] = None
    distance_km: Optional[float] = None
    revenue_rub: Optional[float] = None
    rub_per_km: Optional[float] = None
    rub_per_hour: Optional[float] = None
    source: Optional[str] = "ati"

class FreightListResponse(BaseModel):
    total: int = 0
    items: List[FreightEnriched] = Field(default_factory=list)
