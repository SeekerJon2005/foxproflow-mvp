# -*- coding: utf-8 -*-
# file: src/api/routers/devfactory_catalog.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

try:
    from api.security.flowsec_middleware import require_policies  # type: ignore
except Exception:
    require_policies = None  # type: ignore

from src.core.devfactory.catalog import get_catalog_item, list_catalog


_deps = []
if require_policies is not None:
    try:
        _deps = [Depends(require_policies("devfactory", ["view_tasks"]))]  # минимально, чтобы не плодить политики
    except Exception:
        _deps = []


router = APIRouter(prefix="/devfactory", tags=["devfactory"], dependencies=_deps)


class EstimateIn(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)


@router.get("/catalog", summary="DevFactory catalog (commercial loop)")
def get_catalog(
    q: Optional[str] = Query(None, description="Search substring in title/description"),
):
    items = [it.to_dict() for it in list_catalog()]
    if q:
        qq = q.strip().lower()
        items = [x for x in items if (qq in (x.get("title", "") or "").lower()) or (qq in (x.get("description", "") or "").lower())]
    return {"ok": True, "items": items}


@router.post("/catalog/{order_type}/estimate", summary="Estimate a DevFactory order (catalog-based)")
def estimate_order(order_type: str, body: EstimateIn):
    item = get_catalog_item(order_type)
    if not item:
        raise HTTPException(status_code=404, detail="Unknown order_type")
    # пока оценка фиксированная (каталог)
    return {"ok": True, "order_type": item.order_type, "estimate": item.estimate, "required_inputs": item.required_inputs}
