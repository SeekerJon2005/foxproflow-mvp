from __future__ import annotations

import os
import asyncio
import json
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


# --- Pydantic-модели FlowMeta -----------------------------------------------


class FlowMetaEntity(BaseModel):
    """
    Сущность FlowMeta внутри домена.
    """

    entity_code: str
    title: Optional[str] = None
    description: Optional[str] = None


class FlowMetaDomain(BaseModel):
    """
    Домен FlowMeta.
    """

    code: str
    title: str
    tier: Optional[str] = None
    importance: Optional[str] = None


class FlowMetaDomainWithEntities(FlowMetaDomain):
    """
    Домен FlowMeta с вложенным списком сущностей.
    """

    entities: List[FlowMetaEntity] = []


# --- Вспомогательные функции парсинга JSON ----------------------------------


def _normalize_raw_json(raw: Any) -> Any:
    """
    Приводит сырое значение из БД к python-структуре (list[dict]).

    fn_get_domain_entities_json() в Postgres возвращает jsonb:
    драйвер БД может отдать:
      • уже декодированный объект (list/dict),
      • строку JSON,
      • None.
    """
    if raw is None:
        return []

    if isinstance(raw, str):
        # строка JSON → декодируем
        return json.loads(raw)

    # уже list/dict — используем как есть
    return raw


def parse_flowmeta_domains_with_entities(raw: Any) -> List[FlowMetaDomainWithEntities]:
    """
    Преобразует результат функции flowmeta.fn_get_domain_entities_json()
    в список моделей FlowMetaDomainWithEntities.
    """
    data = _normalize_raw_json(raw)

    if not isinstance(data, list):
        raise ValueError(
            "FlowMeta JSON должен быть массивом объектов доменов (list[dict])."
        )

    result: List[FlowMetaDomainWithEntities] = []

    for item in data:
        if not isinstance(item, dict):
            continue

        entities_raw = item.get("entities") or []
        entities: List[FlowMetaEntity] = []

        if isinstance(entities_raw, list):
            for e in entities_raw:
                if not isinstance(e, dict):
                    continue
                entities.append(
                    FlowMetaEntity(
                        entity_code=str(e.get("entity_code")),
                        title=e.get("title"),
                        description=e.get("description"),
                    )
                )

        domain = FlowMetaDomainWithEntities(
            code=str(item.get("code")),
            title=str(item.get("title") or ""),
            tier=item.get("tier"),
            importance=item.get("importance"),
            entities=entities,
        )
        result.append(domain)

    return result


# --- Доступ к Postgres (как в /health/extended) -----------------------------


def _build_dsn() -> str:
    """
    Собираем DSN к Postgres по тем же правилам, что и в health/extended.
    """
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn

    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")

    if pwd:
        return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
    return f"postgresql://{user}@{host}:{port}/{db}"


def _query_flowmeta_sync() -> Any:
    """
    Синхронный запрос:

        SELECT flowmeta.fn_get_domain_entities_json();

    Пытаемся через psycopg3, если нет — падаем на psycopg2.
    Возвращаем сырое значение первого столбца (json/jsonb или text).
    """
    dsn = _build_dsn()

    # Сначала пробуем psycopg3
    try:
        import psycopg  # type: ignore

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT flowmeta.fn_get_domain_entities_json()")
                row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        # Затем psycopg2
        try:
            import psycopg2  # type: ignore

            conn = psycopg2.connect(dsn)
            try:
                cur = conn.cursor()
                cur.execute("SELECT flowmeta.fn_get_domain_entities_json()")
                row = cur.fetchone()
            finally:
                conn.close()
            return row[0] if row else None
        except Exception as ex2:
            raise RuntimeError(
                f"Failed to query FlowMeta via psycopg/psycopg2: {ex2!r}"
            ) from ex2


async def _load_flowmeta_raw() -> Any:
    """
    Асинхронная обёртка над синхронным запросом:
    уводим блокирующую работу в thread pool, чтобы не стопорить event loop.
    """
    return await asyncio.to_thread(_query_flowmeta_sync)


# --- FastAPI router ---------------------------------------------------------


router = APIRouter(
    prefix="/api/flowmeta",
    tags=["flowmeta"],
)


@router.get(
    "/domains-with-entities",
    response_model=List[FlowMetaDomainWithEntities],
    summary="Список доменов FlowMeta с вложенными сущностями",
)
async def get_flowmeta_domains_with_entities():
    """
    Загружает домены и сущности FlowMeta из Postgres через функцию
    flowmeta.fn_get_domain_entities_json() и возвращает структурированный JSON.
    """
    try:
        raw = await _load_flowmeta_raw()
        domains = parse_flowmeta_domains_with_entities(raw)
        return domains
    except HTTPException:
        # если где-то выше уже сформирован HTTPException — пропускаем как есть
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch FlowMeta domains/entities.",
        ) from exc
