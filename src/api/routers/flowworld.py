# -*- coding: utf-8 -*-
# file: src/api/routers/flowworld.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

import os

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field


def _connect_pg():
    """
    Локальный helper подключения к Postgres для FlowWorld API.

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
    prefix="/api/flowworld",
    tags=["flowworld"],
)


class WorldSpace(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class WorldObject(BaseModel):
    id: int
    space_id: int
    code: str
    name: str
    kind: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class WorldState(BaseModel):
    spaces: List[WorldSpace]
    objects: List[WorldObject]


class TripLink(BaseModel):
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


@router.get("/state", response_model=WorldState, summary="Срез мира FlowWorld (MVP)")
def get_world_state(
    space_code: Optional[str] = Query(
        None,
        description="Если указан, отдаём только указанное пространство и его объекты.",
    )
) -> WorldState:
    """
    Возвращает базовый срез мира FlowWorld:

      - список пространств (world.spaces),
      - список объектов (world.objects).

    Если указан space_code, фильтрует по нему.
    """
    conn = _connect_pg()
    try:
        spaces: List[WorldSpace] = []
        objects: List[WorldObject] = []

        with conn.cursor() as cur:
            if space_code:
                cur.execute(
                    """
                    SELECT id, code, name, description, meta
                    FROM world.spaces
                    WHERE code = %s
                    ORDER BY id
                    """,
                    (space_code,),
                )
            else:
                cur.execute(
                    """
                    SELECT id, code, name, description, meta
                    FROM world.spaces
                    ORDER BY id
                    """
                )
            rows = cur.fetchall()
            for r in rows:
                if isinstance(r, dict):
                    spaces.append(
                        WorldSpace(
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
                        WorldSpace(
                            id=sid,
                            code=code,
                            name=name,
                            description=desc,
                            meta=meta or {},
                        )
                    )

            if spaces:
                if space_code:
                    cur.execute(
                        """
                        SELECT id, space_id, code, name, kind, lat, lon, meta
                        FROM world.objects
                        WHERE space_id = %s
                        ORDER BY id
                        """,
                        (spaces[0].id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, space_id, code, name, kind, lat, lon, meta
                        FROM world.objects
                        WHERE space_id = ANY(%s)
                        ORDER BY id
                        """,
                        ([s.id for s in spaces],),
                    )
                rows = cur.fetchall()
                for r in rows:
                    if isinstance(r, dict):
                        objects.append(
                            WorldObject(
                                id=r["id"],
                                space_id=r["space_id"],
                                code=r["code"],
                                name=r["name"],
                                kind=r["kind"],
                                lat=r.get("lat"),
                                lon=r.get("lon"),
                                meta=r.get("meta") or {},
                            )
                        )
                    else:
                        oid, sid, code, name, kind, lat, lon, meta = r
                        objects.append(
                            WorldObject(
                                id=oid,
                                space_id=sid,
                                code=code,
                                name=name,
                                kind=kind,
                                lat=lat,
                                lon=lon,
                                meta=meta or {},
                            )
                        )

        return WorldState(spaces=spaces, objects=objects)
    finally:
        try:
            conn.close()
        except Exception:
            pass


@router.get("/spaces", response_model=List[WorldSpace], summary="Список пространств FlowWorld")
def list_spaces() -> List[WorldSpace]:
    """
    Возвращает список всех пространств FlowWorld (world.spaces).
    """
    conn = _connect_pg()
    try:
        spaces: List[WorldSpace] = []
        with conn.cursor() as cur:
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
                        WorldSpace(
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
                        WorldSpace(
                            id=sid,
                            code=code,
                            name=name,
                            description=desc,
                            meta=meta or {},
                        )
                    )
        return spaces
    finally:
        try:
            conn.close()
        except Exception:
            pass


@router.get(
    "/spaces/{code}",
    response_model=WorldSpace,
    summary="Информация о пространстве FlowWorld по коду",
)
def get_space_by_code(code: str) -> WorldSpace:
    """
    Возвращает одно пространство по коду.
    """
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, code, name, description, meta
                FROM world.spaces
                WHERE code = %s
                """,
                (code,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Space not found")
            if isinstance(row, dict):
                return WorldSpace(
                    id=row["id"],
                    code=row["code"],
                    name=row["name"],
                    description=row.get("description"),
                    meta=row.get("meta") or {},
                )
            sid, scode, name, desc, meta = row
            return WorldSpace(
                id=sid,
                code=scode,
                name=name,
                description=desc,
                meta=meta or {},
            )
    finally:
        try:
            conn.close()
        except Exception:
            pass


@router.get(
    "/trip-links",
    response_model=List[TripLink],
    summary="Связи FlowWorld ↔ логистика (world.trip_links)",
)
def list_trip_links(
    entity_type: Optional[str] = Query(
        None,
        description="Тип сущности логистики ('trip', 'vehicle', 'load', 'other'). Если не задан — все типы.",
    ),
    entity_id: Optional[int] = Query(
        None,
        description="ID логистической сущности. Если не задан — все связки данного типа.",
    ),
    space_code: Optional[str] = Query(
        None,
        description="Код пространства FlowWorld (фильтр по space_code).",
    ),
) -> List[TripLink]:
    """
    Возвращает список связей между логистическими объектами (рейс/ТС/груз)
    и пространствами/объектами FlowWorld по таблице world.trip_links.

    Пока это чистый read-only API; создание/обновление связей будем
    делать через отдельные задачи DevFactory / административный UI.
    """
    conn = _connect_pg()
    try:
        links: List[TripLink] = []

        where: List[str] = []
        params: List[Any] = []

        if entity_type:
            where.append("tl.entity_type = %s")
            params.append(entity_type)
        if entity_id is not None:
            where.append("tl.entity_id = %s")
            params.append(entity_id)
        if space_code:
            where.append("ws.code = %s")
            params.append(space_code)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        sql = f"""
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
            {where_sql}
            ORDER BY tl.id
        """

        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            for r in rows:
                if isinstance(r, dict):
                    links.append(
                        TripLink(
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
                        TripLink(
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

        return links
    finally:
        try:
            conn.close()
        except Exception:
            pass
