# src/api/main.py
from fastapi import FastAPI, Query, HTTPException
from typing import Optional

# поправленные импорты
from .app.schemas import FreightEnriched, FreightListResponse
from .app.repo import list_freights, get_freight_by_id

app = FastAPI(title="FoxProFlow API", version="0.1")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/freights", response_model=FreightListResponse)
async def freights(
    origin: Optional[str] = Query(None, description="Город погрузки"),
    destination: Optional[str] = Query(None, description="Город выгрузки"),
    date_from: Optional[str] = Query(None, description=">= YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="<= YYYY-MM-DD"),
    body_type: Optional[str] = None,
    min_weight: Optional[float] = None,
    max_weight: Optional[float] = None,
    min_volume: Optional[float] = None,
    max_volume: Optional[float] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    order_by: str = Query("parsed_at", description="parsed_at|loading_date|revenue|profit_per_km"),
):
    rows, total = await list_freights(
        origin, destination, date_from, date_to, body_type,
        min_weight, max_weight, min_volume, max_volume,
        limit, offset, order_by
    )
    items = [FreightEnriched(**r) for r in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}

@app.get("/freights/{fid}", response_model=FreightEnriched)
async def freight_by_id(fid: str):
    row = await get_freight_by_id(fid)
    if not row:
        raise HTTPException(404, "not found")
    return FreightEnriched(**row)
