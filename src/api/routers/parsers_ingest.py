# -*- coding: utf-8 -*-
"""
Парсер-ингест: фрахты и транспорт.

Изменения (NDC):
- Нормализация полей source/source_uid (trim/str()).
- Счётчик dedup_dropped для прозрачности.
- Безопасная проверка целевой таблицы для trucks + запись info в STATUS.extra.
- Остальное — как в исходной версии: Pydantic v1/v2-совместимость, ORJSONResponse, явные commit()/rollback(),
  мягкие Celery-триггеры и идемпотентные DDL.
"""

from __future__ import annotations

import os
import re
import json
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import ORJSONResponse

# --- Pydantic v1/v2 совместимость ------------------------------------------------
import pydantic as _p
try:
    from pydantic import BaseModel, Field, field_validator as _fv_native  # v2
    _PV2 = True
    def _fv(*fields, mode: str = "before"):
        return _fv_native(*fields, mode=mode)
except Exception:
    from pydantic import BaseModel, Field, validator as _fv_legacy  # v1
    _PV2 = False
    def _fv(*fields, mode: str = "before"):
        # в v1 'pre=True' = v2 'mode="before"'
        return _fv_legacy(*fields, pre=(mode == "before"))

# --- SQLAlchemy (2.x API) ---------------------------------------------------------
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# --- Celery (мягко) ---------------------------------------------------------------
try:
    from src.worker.celery_app import celery
except Exception:
    celery = None  # type: ignore

router = APIRouter(prefix="/api/parsers/ingest", tags=["parsers"])

# ==============================================================================#
# JSON helpers                                                                  #
# ==============================================================================#

def _resp(payload: Dict[str, Any], status_code: int = 200) -> ORJSONResponse:
    """Единый способ ответа: фиксированная длина + закрытие соединения."""
    return ORJSONResponse(payload, status_code=status_code, headers={"Connection": "close"})

def _json_or_none(d: Optional[Dict[str, Any]]) -> Optional[str]:
    if d is None:
        return None
    try:
        return json.dumps(d, ensure_ascii=False)
    except Exception:
        return None

# ==============================================================================#
# DB wiring (лениво; диалект подбирается автоматически)                         #
# ==============================================================================#

get_db = None  # type: ignore
try:
    # Если в проекте есть готовый DI — используем его (не трогаем транзакции здесь)
    from src.api.deps import get_db as _project_get_db  # type: ignore
    get_db = _project_get_db  # type: ignore
except Exception:
    _ENGINE = None
    _SessionLocal = None

    def _build_db_url() -> str:
        url = os.getenv("DATABASE_URL")
        if url:
            return url  # SQLAlchemy сам подберёт драйвер
        user = os.getenv("POSTGRES_USER", "admin")
        pwd  = os.getenv("POSTGRES_PASSWORD", "admin")
        host = os.getenv("POSTGRES_HOST", "postgres")
        port = os.getenv("POSTGRES_PORT", "5432")
        db   = os.getenv("POSTGRES_DB", "foxproflow")
        try:
            import psycopg  # noqa: F401
            return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{db}"
        except Exception:
            return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"

    def _get_engine():
        global _ENGINE
        if _ENGINE is None:
            _ENGINE = create_engine(_build_db_url(), pool_pre_ping=True, future=True)
        return _ENGINE

    def get_db() -> Iterator[Session]:  # type: ignore
        """
        Fallback DI: не начинаем транзакцию заранее; коммитим после хендлера.
        Это совместимо с ручным commit()/rollback() внутри эндпоинтов.
        """
        global _SessionLocal
        if _SessionLocal is None:
            _SessionLocal = sessionmaker(bind=_get_engine(), autoflush=False, autocommit=False, future=True)
        db = _SessionLocal()
        try:
            yield db
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
        finally:
            db.close()

# ==============================================================================#
# Helpers                                                                       #
# ==============================================================================#

def _ensure_core_schema(db: Session) -> None:
    """Создаёт недостающие базовые таблицы (идемпотентно)."""
    db.execute(text("""
    CREATE TABLE IF NOT EXISTS public.freights(
      id            bigserial PRIMARY KEY,
      source        text NOT NULL,
      source_uid    text UNIQUE NOT NULL,
      loading_region   text,
      unloading_region text,
      loading_date     timestamptz,
      unloading_date   timestamptz,
      distance      numeric,
      revenue_rub   numeric,
      body_type     text,
      weight        numeric,
      payload       jsonb,
      parsed_at     timestamptz DEFAULT now()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS ux_freights_source_uid ON public.freights(source_uid);
    """))

    db.execute(text("""
    CREATE TABLE IF NOT EXISTS public.parsers_status(
      source    text NOT NULL,
      kind      text NOT NULL,
      last_seen timestamptz,
      received  integer,
      inserted  integer,
      updated   integer,
      extra     jsonb,
      PRIMARY KEY(source, kind)
    );
    """))

    db.execute(text("""
    CREATE TABLE IF NOT EXISTS public.trucks_parsed(
      id              bigserial PRIMARY KEY,
      source          text NOT NULL,
      source_uid      text UNIQUE NOT NULL,
      region          text,
      available_from  timestamptz,
      body_type       text,
      capacity_weight numeric,
      plate           text,
      phone           text,
      payload         jsonb,
      parsed_at       timestamptz DEFAULT now()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS ux_trucks_parsed_source_uid ON public.trucks_parsed(source_uid);
    """))

def _trucks_target_table(db: Session) -> Tuple[str, str]:
    """
    Если в public.trucks есть и 'source', и 'source_uid' — пишем в неё, иначе trucks_parsed.
    Возвращаем кортеж (table_name, kind_for_status).
    """
    cnt = db.execute(text("""
      SELECT COUNT(*) FROM information_schema.columns
      WHERE table_schema='public' AND table_name='trucks'
        AND column_name IN ('source','source_uid')
    """)).scalar()
    if cnt and int(cnt) >= 2:
        return "public.trucks", "trucks"
    return "public.trucks_parsed", "trucks_parsed"

def _dedup_by_source_uid(items: List["BaseModel"]) -> Tuple[List["BaseModel"], int]:
    seen: set[str] = set()
    out: List["BaseModel"] = []
    dropped = 0
    for it in items:
        uid = getattr(it, "source_uid", None)
        if uid is None:
            dropped += 1
            continue
        suid = str(uid).strip()
        if not suid or suid in seen:
            dropped += 1
            continue
        seen.add(suid)
        # перезапишем очищенный uid, если был не-str/с пробелами
        try:
            setattr(it, "source_uid", suid)
        except Exception:
            pass
        out.append(it)
    return out, dropped

def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v)
    s = s.replace("\u00A0", "").replace(" ", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except Exception:
        return None

# ==============================================================================#
# Pydantic models (совместимы с v1/v2)                                          #
# ==============================================================================#

class FreightIn(BaseModel):
    source: str
    source_uid: str

    loading_region: Optional[str] = None
    unloading_region: Optional[str] = None
    loading_date: Optional[datetime] = None
    unloading_date: Optional[datetime] = None

    distance: Optional[float] = None
    revenue_rub: Optional[float] = None

    price: Optional[float] = Field(None, description="Синоним revenue_rub")
    distance_km: Optional[float] = Field(None, description="Синоним distance")

    body_type: Optional[str] = None
    weight: Optional[float] = None
    payload: Optional[Dict[str, Any]] = None

    @_fv("source", "source_uid", mode="before")
    def _v_basic_ids(cls, v):
        return str(v).strip() if v is not None else v

    @_fv("loading_region", "unloading_region", mode="before")
    def _v_region(cls, v):
        return v.strip() if isinstance(v, str) else v

    @_fv("revenue_rub", "price", "distance", "distance_km", "weight", mode="before")
    def _v_float(cls, v):
        return _to_float(v)

    def normalized(self) -> Dict[str, Any]:
        rev = self.revenue_rub if self.revenue_rub is not None else self.price
        dist = self.distance if self.distance is not None else self.distance_km
        return {
            "source": self.source,
            "source_uid": self.source_uid,
            "loading_region": self.loading_region,
            "unloading_region": self.unloading_region,
            "loading_date": self.loading_date,
            "unloading_date": self.unloading_date,
            "distance": dist,
            "revenue_rub": rev,
            "body_type": self.body_type,
            "weight": self.weight,
            "payload": self.payload,
        }

class TruckIn(BaseModel):
    source: str
    source_uid: str

    region: Optional[str] = None
    available_from: Optional[datetime] = None
    body_type: Optional[str] = None
    capacity_weight: Optional[float] = None
    plate: Optional[str] = None
    phone: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None

    @_fv("source", "source_uid", mode="before")
    def _v_basic_ids(cls, v):
        return str(v).strip() if v is not None else v

    @_fv("region", mode="before")
    def _v_region(cls, v):
        return v.strip() if isinstance(v, str) else v

    @_fv("capacity_weight", mode="before")
    def _v_float(cls, v):
        return _to_float(v)

# ==============================================================================#
# SQL                                                                           #
# ==============================================================================#

UPSERT_FREIGHTS_SQL = text("""
INSERT INTO public.freights(
  source, source_uid,
  loading_region, unloading_region,
  loading_date, unloading_date,
  distance, revenue_rub,
  body_type, weight, payload
) VALUES (
  :source, :source_uid,
  :loading_region, :unloading_region,
  :loading_date, :unloading_date,
  :distance, :revenue_rub,
  :body_type, :weight, CAST(:payload AS jsonb)
)
ON CONFLICT (source_uid) DO UPDATE SET
  loading_region   = EXCLUDED.loading_region,
  unloading_region = EXCLUDED.unloading_region,
  loading_date     = EXCLUDED.loading_date,
  unloading_date   = EXCLUDED.unloading_date,
  distance         = EXCLUDED.distance,
  revenue_rub      = EXCLUDED.revenue_rub,
  body_type        = EXCLUDED.body_type,
  weight           = EXCLUDED.weight,
  payload          = EXCLUDED.payload,
  parsed_at        = now()
RETURNING (xmax = 0) AS inserted;
""")

def build_upsert_trucks_sql(target_table: str):
    return text(f"""
INSERT INTO {target_table}(
  source, source_uid,
  region, available_from,
  body_type, capacity_weight,
  plate, phone, payload
) VALUES (
  :source, :source_uid,
  :region, CAST(:available_from AS timestamptz),
  :body_type, CAST(:capacity_weight AS numeric),
  :plate, :phone, CAST(:payload AS jsonb)
)
ON CONFLICT (source_uid) DO UPDATE SET
  region          = EXCLUDED.region,
  available_from  = EXCLUDED.available_from,
  body_type       = EXCLUDED.body_type,
  capacity_weight = EXCLUDED.capacity_weight,
  plate           = EXCLUDED.plate,
  phone           = EXCLUDED.phone,
  payload         = EXCLUDED.payload,
  parsed_at       = now()
RETURNING (xmax = 0) AS inserted;
""")

STATUS_UPSERT_SQL = text("""
INSERT INTO public.parsers_status(source, kind, last_seen, received, inserted, updated, extra)
VALUES (:source, :kind, now(), :received, :inserted, :updated, CAST(:extra AS jsonb))
ON CONFLICT (source, kind) DO UPDATE SET
  last_seen = EXCLUDED.last_seen,
  received  = EXCLUDED.received,
  inserted  = EXCLUDED.inserted,
  updated   = EXCLUDED.updated,
  extra     = EXCLUDED.extra;
""")

# ==============================================================================#
# Endpoints                                                                      #
# ==============================================================================#

@router.post("/freights", summary="Batch ingest: freight cards")
def ingest_freights(items: List[FreightIn], db: Session = Depends(get_db)):  # type: ignore
    if not items:
        return _resp({"ok": False, "error": "Empty payload"}, status_code=400)

    try:
        _ensure_core_schema(db)
        items, dropped = _dedup_by_source_uid(items)

        recv = len(items)
        used_price_alias = 0
        used_distance_alias = 0
        missing_core = 0
        inserted = 0
        updated = 0

        for it in items:
            norm = it.normalized()
            if it.revenue_rub is None and it.price is not None:
                used_price_alias += 1
            if it.distance is None and it.distance_km is not None:
                used_distance_alias += 1
            if norm["revenue_rub"] is None or norm["distance"] is None:
                missing_core += 1

            row = db.execute(UPSERT_FREIGHTS_SQL, {
                "source": norm["source"],
                "source_uid": norm["source_uid"],
                "loading_region": norm["loading_region"],
                "unloading_region": norm["unloading_region"],
                "loading_date": norm["loading_date"],
                "unloading_date": norm["unloading_date"],
                "distance": norm["distance"],
                "revenue_rub": norm["revenue_rub"],
                "body_type": norm["body_type"],
                "weight": norm["weight"],
                "payload": _json_or_none(norm["payload"]),
            }).first()
            if row and bool(row[0]): inserted += 1
            else: updated += 1

        db.execute(STATUS_UPSERT_SQL, {
            "source": items[0].source,
            "kind": "freights",
            "received": recv,
            "inserted": inserted,
            "updated": updated,
            "extra": json.dumps({
                "used_price_alias": used_price_alias,
                "used_distance_alias": used_distance_alias,
                "missing_core": missing_core,
                "dedup_dropped": dropped
            }, ensure_ascii=False),
        })

        db.commit()

        # Пост-обновления через Celery (мягко, без влияния на HTTP-ответ)
        if celery and os.getenv("ENABLE_INGEST_POST_REFRESH", "1") == "1":
            try:
                if os.getenv("ENABLE_FE_MV_REFRESH", "1") == "1":
                    celery.send_task("mv.refresh.freights_enriched")
                if os.getenv("ENABLE_MARKET_RATES_REFRESH", "0") == "1":
                    celery.send_task("mv.refresh.market_rates")
                if os.getenv("ENABLE_FORECAST_REFRESH", "1") == "1":
                    celery.send_task("forecast.refresh")
            except Exception:
                pass

        return _resp({
            "ok": True,
            "received": recv,
            "inserted": inserted,
            "updated": updated,
            "extra": {
                "used_price_alias": used_price_alias,
                "used_distance_alias": used_distance_alias,
                "missing_core": missing_core,
                "dedup_dropped": dropped
            },
        })

    except Exception as e:
        try:
            db.rollback()
        finally:
            return _resp({"ok": False, "error": repr(e)}, status_code=500)

@router.post("/trucks", summary="Batch ingest: trucks (market)")
def ingest_trucks(items: List[TruckIn], db: Session = Depends(get_db)):  # type: ignore
    if not items:
        return _resp({"ok": False, "error": "Empty payload"}, status_code=400)

    try:
        _ensure_core_schema(db)
        items, dropped = _dedup_by_source_uid(items)

        recv = len(items)
        inserted = 0
        updated = 0

        target, kind = _trucks_target_table(db)
        UPSERT_TRUCKS_SQL = build_upsert_trucks_sql(target)

        for it in items:
            row = db.execute(UPSERT_TRUCKS_SQL, {
                "source": it.source,
                "source_uid": it.source_uid,
                "region": it.region,
                "available_from": it.available_from,
                "body_type": it.body_type,
                "capacity_weight": it.capacity_weight,
                "plate": it.plate,
                "phone": it.phone,
                "payload": _json_or_none(it.payload),
            }).first()
            if row and bool(row[0]): inserted += 1
            else: updated += 1

        db.execute(STATUS_UPSERT_SQL, {
            "source": items[0].source,
            "kind": kind,
            "received": recv,
            "inserted": inserted,
            "updated": updated,
            "extra": json.dumps({"target_table": target, "dedup_dropped": dropped}, ensure_ascii=False),
        })

        db.commit()

        if celery and os.getenv("ENABLE_TRUCKS_POST_REFRESH", "0") == "1":
            try:
                celery.send_task("mv.refresh.vehicle_availability")
            except Exception:
                pass

        return _resp({"ok": True, "received": recv, "inserted": inserted, "updated": updated,
                      "extra": {"target_table": target, "dedup_dropped": dropped}})

    except Exception as e:
        try:
            db.rollback()
        finally:
            return _resp({"ok": False, "error": repr(e)}, status_code=500)
