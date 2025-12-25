# -*- coding: utf-8 -*-
# file: src/api/routers/eri.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


def _connect_pg():
    """
    Локальный helper подключения к Postgres для ERI API.

    Используем ту же БД, что и основной организм:
        host=postgres, db=foxproflow, user=admin (через POSTGRES_*).
    """
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = "postgres"
    port = os.getenv("POSTGRES_PORT", "5432")
    db = "foxproflow"

    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    dsn = f"postgresql://{auth}{host}:{port}/{db}"

    try:
        import psycopg  # type: ignore

        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore

        return psycopg.connect(dsn)


router = APIRouter(
    prefix="/api/eri",
    tags=["eri"],
)


# === Модели для /context ===

class EriFlowMetaSummary(BaseModel):
    domains: Dict[str, int] = Field(
        default_factory=dict,
        description="Сколько сущностей FlowMeta в каждом домене.",
    )


class EriFlowWorldSpace(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class EriFlowWorldObject(BaseModel):
    id: int
    space_id: int
    code: str
    name: str
    kind: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class EriWorldTripLink(BaseModel):
    """
    Связь логистики и FlowWorld для ERI.

    entity_type: 'trip' | 'vehicle' | 'load' | 'other'
    entity_id:   числовой id логистической сущности
    space_code:  код пространства FlowWorld
    object_code: код объекта FlowWorld (может быть None)
    relation:    'origin' | 'destination' | 'parking' | 'base' | ...
    """
    id: int
    entity_type: str
    entity_id: int
    space_id: int
    space_code: str
    space_name: str
    object_id: Optional[int] = None
    object_code: Optional[str] = None
    object_name: Optional[str] = None
    relation: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class EriFlowWorldSummary(BaseModel):
    spaces: List[EriFlowWorldSpace] = Field(default_factory=list)
    objects: List[EriFlowWorldObject] = Field(default_factory=list)
    links: List[EriWorldTripLink] = Field(default_factory=list)


class EriDevFactoryStackStatus(BaseModel):
    stack: str
    status: str
    count: int


class EriDevFactorySummary(BaseModel):
    total_tasks: int
    stacks: List[EriDevFactoryStackStatus] = Field(default_factory=list)


class EriContext(BaseModel):
    """
    Первый агрегированный контекст для ERI v0.1.

    Включает:
      - FlowMeta summary (домен → количество сущностей),
      - FlowWorld (пространства, объекты и trip-links),
      - DevFactory summary (кол-во задач по стеку/статусу).
    """
    flowmeta: EriFlowMetaSummary
    flowworld: EriFlowWorldSummary
    devfactory: EriDevFactorySummary


# === /api/eri/context v0.1 ===

@router.get("/context", response_model=EriContext, summary="Агрегированный контекст организма для ERI v0.1")
def get_eri_context() -> EriContext:
    """
    Возвращает агрегированный контекст организма для ERI v0.1:

    - FlowMeta: сколько сущностей в каждом домене (flowmeta.entity),
    - FlowWorld: список пространств, объектов и связей world.trip_links,
    - DevFactory: сводка по задачам dev.dev_task (stack/status).
    """
    conn = _connect_pg()
    try:
        meta_summary = _load_flowmeta_summary(conn)
        world_summary = _load_flowworld_summary(conn)
        devfactory_summary = _load_devfactory_summary(conn)

        return EriContext(
            flowmeta=meta_summary,
            flowworld=world_summary,
            devfactory=devfactory_summary,
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _load_flowmeta_summary(conn) -> EriFlowMetaSummary:
    """
    FlowMeta summary:
      SELECT domain_code, count(*) FROM flowmeta.entity GROUP BY domain_code;
    """
    domains: Dict[str, int] = {}

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT domain_code, COUNT(*) AS cnt
                FROM flowmeta.entity
                GROUP BY domain_code
                ORDER BY domain_code
                """
            )
            rows = cur.fetchall()
            for r in rows:
                if isinstance(r, dict):
                    domains[str(r["domain_code"])] = int(r["cnt"])
                else:
                    domain_code, cnt = r
                    domains[str(domain_code)] = int(cnt)
    except Exception:
        domains = {}
    return EriFlowMetaSummary(domains=domains)


def _load_flowworld_summary(conn) -> EriFlowWorldSummary:
    """
    FlowWorld summary:
      - world.spaces
      - world.objects
      - world.trip_links
    """
    spaces: List[EriFlowWorldSpace] = []
    objects: List[EriFlowWorldObject] = []
    links: List[EriWorldTripLink] = []

    try:
        with conn.cursor() as cur:
            # spaces
            cur.execute(
                """
                SELECT id, code, name, description, meta
                FROM world.spaces
                ORDER BY id
                """
            )
            for r in cur.fetchall():
                if isinstance(r, dict):
                    spaces.append(
                        EriFlowWorldSpace(
                            id=r["id"],
                            code=r["code"],
                            name=r["name"],
                            description=r.get("description"),
                            meta=r.get("meta") or {},
                        )
                    )
                else:
                    sid, code, name, desc, meta = r
                    spaces.append(
                        EriFlowWorldSpace(
                            id=sid,
                            code=code,
                            name=name,
                            description=desc,
                            meta=meta or {},
                        )
                    )

            # objects
            cur.execute(
                """
                SELECT id, space_id, code, name, kind, meta
                FROM world.objects
                ORDER BY id
                """
            )
            for r in cur.fetchall():
                if isinstance(r, dict):
                    objects.append(
                        EriFlowWorldObject(
                            id=r["id"],
                            space_id=r["space_id"],
                            code=r["code"],
                            name=r["name"],
                            kind=r["kind"],
                            meta=r.get("meta") or {},
                        )
                    )
                else:
                    oid, sid, code, name, kind, meta = r
                    objects.append(
                        EriFlowWorldObject(
                            id=oid,
                            space_id=sid,
                            code=code,
                            name=name,
                            kind=kind,
                            meta=meta or {},
                        )
                    )

            # links (world.trip_links)
            cur.execute(
                """
                SELECT
                    tl.id,
                    tl.entity_type,
                    tl.entity_id,
                    tl.space_id,
                    ws.code AS space_code,
                    ws.name AS space_name,
                    tl.object_id,
                    wo.code AS object_code,
                    wo.name AS object_name,
                    tl.relation,
                    tl.meta
                FROM world.trip_links tl
                JOIN world.spaces  ws ON ws.id  = tl.space_id
                LEFT JOIN world.objects wo ON wo.id = tl.object_id
                ORDER BY tl.id
                """
            )
            for r in cur.fetchall():
                if isinstance(r, dict):
                    links.append(
                        EriWorldTripLink(
                            id=r["id"],
                            entity_type=r["entity_type"],
                            entity_id=r["entity_id"],
                            space_id=r["space_id"],
                            space_code=r["space_code"],
                            space_name=r["space_name"],
                            object_id=r.get("object_id"),
                            object_code=r.get("object_code"),
                            object_name=r.get("object_name"),
                            relation=r["relation"],
                            meta=r.get("meta") or {},
                        )
                    )
                else:
                    (
                        lid,
                        etype,
                        eid,
                        sid,
                        scode,
                        sname,
                        oid,
                        ocode,
                        oname,
                        rel,
                        meta,
                    ) = r
                    links.append(
                        EriWorldTripLink(
                            id=lid,
                            entity_type=etype,
                            entity_id=eid,
                            space_id=sid,
                            space_code=scode,
                            space_name=sname,
                            object_id=oid,
                            object_code=ocode,
                            object_name=oname,
                            relation=rel,
                            meta=meta or {},
                        )
                    )

    except Exception:
        spaces = []
        objects = []
        links = []

    return EriFlowWorldSummary(spaces=spaces, objects=objects, links=links)


def _load_devfactory_summary(conn) -> EriDevFactorySummary:
    """
    DevFactory summary:
      SELECT stack, status, COUNT(*) FROM dev.dev_task GROUP BY stack, status.
    """
    stacks: List[EriDevFactoryStackStatus] = []
    total_tasks = 0

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT stack, status, COUNT(*) AS cnt
                FROM dev.dev_task
                GROUP BY stack, status
                ORDER BY stack, status
                """
            )
            for r in cur.fetchall():
                if isinstance(r, dict):
                    stack = str(r["stack"])
                    status = str(r["status"])
                    cnt = int(r["cnt"])
                else:
                    stack, status, cnt = r
                    stack = str(stack)
                    status = str(status)
                    cnt = int(cnt)

                stacks.append(
                    EriDevFactoryStackStatus(
                        stack=stack,
                        status=status,
                        count=cnt,
                    )
                )
                total_tasks += cnt
    except Exception:
        stacks = []
        total_tasks = 0

    return EriDevFactorySummary(
        total_tasks=total_tasks,
        stacks=stacks,
    )


# === /api/eri/talk — заглушка v0.1 (для совместимости) ===

class EriTalkRequest(BaseModel):
    text: str = Field(..., description="Текст обращения к ERI.")
    mode: Optional[str] = Field(
        default=None,
        description="Режим ERI (детский/семейный/организм/социум). Пока не используется.",
    )


class EriTalkResponse(BaseModel):
    reply: str
    note: Optional[str] = None


@router.post("/talk", response_model=EriTalkResponse, summary="Диалоговый вход ERI (заглушка v0.1)")
def eri_talk(body: EriTalkRequest) -> EriTalkResponse:
    """
    Заглушка для диалогового входа ERI.

    В v0.1 просто эхо с короткой меткой. Реальный мозг ERI будет подставлен позже.
    """
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустой текст запроса.")

    return EriTalkResponse(
        reply=(
            "ERI v0.1 (stub): я получил от тебя запрос и вижу текущий контекст организма "
            "(FlowMeta, FlowWorld, DevFactory) через /api/eri/context."
        ),
        note="Это временная заглушка. Реальный ERI будет подключён после реализации ядра.",
    )
