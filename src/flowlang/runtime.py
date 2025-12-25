# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import time
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import yaml


log = logging.getLogger(__name__)


@dataclass
class CursorCfg:
    path: Optional[str] = None   # JSONPath-подобный путь: $.next
    param: Optional[str] = None  # имя параметра для курсора (например, "cursor")


@dataclass
class EntryPoint:
    name: str
    method: str
    url: str
    params: Dict[str, Any]
    cursor: CursorCfg


@dataclass
class FlowSpec:
    version: str
    source: str
    auth: Dict[str, Any]
    rate: Dict[str, Any]
    fetch: Dict[str, Any]
    parse: Dict[str, Any]
    persist: Dict[str, Any]
    post: Dict[str, Any]


def _pg_dsn() -> str:
    """
    Собираем DSN к Postgres из env. Совместимо с текущим docker-compose/.env.
    """
    dsn = os.getenv("DATABASE_URL", "").strip()
    if dsn:
        return dsn
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "admin")
    password = os.getenv("POSTGRES_PASSWORD", "admin")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _pg():
    return psycopg2.connect(_pg_dsn())


def _rate_sleep(qps: float, burst: int) -> None:
    """
    Простейший limiter: ограничение QPS (burst пока не используем, но оставляем в сигнатуре).
    """
    if qps <= 0:
        return
    time.sleep(max(0.0, 1.0 / qps))


def _json_get(obj: Any, path: str) -> Any:
    """
    Мини-JSONPath "$.a.b.c" для простых кейсов. Нужного нам уровня хватает.
    """
    if not path or not path.startswith("$."):
        return None
    cur = obj
    for part in path[2:].split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _headers_from_auth(auth: Dict[str, Any]) -> Dict[str, str]:
    """
    Формирует HTTP-заголовки авторизации по описанию в flow-файле.
    Сейчас поддерживаем только kind=token.
    """
    kind = auth.get("kind") or "token"
    if kind == "token":
        token_envs = auth.get("env") or ["API_TOKEN"]
        token = os.getenv(token_envs[0], "")
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}
    # при необходимости можно добавить oauth2/cookie-flow
    return {}


def _upsert_source(conn, code: str) -> int:
    """
    Регистрируем/обновляем источник в integrations.sources и возвращаем его id.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO integrations.sources(code, kind, active)
            VALUES (%s, 'api', true)
            ON CONFLICT (code) DO UPDATE SET updated_at = now()
            RETURNING id
            """,
            (code,),
        )
        return cur.fetchone()[0]


def _insert_raw_event(
    conn,
    source_id: int,
    kind: str,
    external_id: Optional[str],
    payload: Dict[str, Any],
) -> int:
    """
    Сохраняем сырой event (полный JSON ответа) в ingest.raw_events.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest.raw_events(source_id, kind, external_id, payload)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (source_id, kind, external_id, json.dumps(payload, ensure_ascii=False)),
        )
        return cur.fetchone()[0]


def _insert_freight_raw(
    conn,
    src: str,
    external_id: str,
    origin_text: Optional[str],
    dest_text: Optional[str],
    price_rub: Optional[float],
    payload: Dict[str, Any],
) -> None:
    """
    Пишем «плоское сырьё» груза в market.freights_raw
    с UPSERT по (source, external_id).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO market.freights_raw(source, external_id, origin_text, dest_text, price_rub, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (source, external_id) DO UPDATE
              SET origin_text = COALESCE(EXCLUDED.origin_text, market.freights_raw.origin_text),
                  dest_text   = COALESCE(EXCLUDED.dest_text,   market.freights_raw.dest_text),
                  price_rub   = COALESCE(EXCLUDED.price_rub,   market.freights_raw.price_rub),
                  payload     = EXCLUDED.payload
            """,
            (src, external_id, origin_text, dest_text, price_rub, json.dumps(payload, ensure_ascii=False)),
        )


def run_flow(flow_path: str, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Выполняет один FlowLang-коннектор:
      - читает YAML-описание из flow_path,
      - ходит в внешний API (REST),
      - пишет данные в ingest.raw_events и market.freights_raw.

    :param flow_path: путь до .flow.yaml внутри контейнера (/app/flow/...)
    :param limit: жёсткий лимит по количеству элементов (для smoke/отладки)
    :return: словарь с итоговой статистикой {"ok": True/False, "source": ..., "total": ...}
    """
    with open(flow_path, "r", encoding="utf-8") as f:
        raw_spec = yaml.safe_load(f)

    spec = FlowSpec(**raw_spec)

    qps = float(spec.rate.get("qps", 1.0))
    burst = int(spec.rate.get("burst", 5))

    eps: List[EntryPoint] = []
    for ep in spec.fetch.get("entrypoints") or []:
        eps.append(
            EntryPoint(
                name=ep["name"],
                method=ep.get("method", "GET").upper(),
                url=ep["url"],
                params=ep.get("params") or {},
                cursor=CursorCfg(**(ep.get("cursor") or {})),
            )
        )

    headers = _headers_from_auth(spec.auth)
    total = 0
    conn = _pg()

    log.info("run_flow: source=%s flow=%s qps=%s burst=%s", spec.source, flow_path, qps, burst)

    try:
        src_id = _upsert_source(conn, spec.source)
        log.debug("run_flow: source_id=%s", src_id)

        for ep in eps:
            next_url = ep.url
            next_params = dict(ep.params)
            while next_url:
                _rate_sleep(qps, burst)
                log.debug("run_flow[%s]: request %s %s params=%s", spec.source, ep.method, next_url, next_params)
                resp = requests.request(ep.method, next_url, headers=headers, params=next_params, timeout=20)
                resp.raise_for_status()
                data = resp.json()

                items: Iterable[Any] = data
                sel = (spec.parse or {}).get("selector")
                if sel:
                    maybe = _json_get(data, sel)
                    if isinstance(maybe, list):
                        items = maybe
                    else:
                        items = []

                for row in items:
                    mapped: Dict[str, Any] = {}
                    for k, path in (spec.parse.get("map") or {}).items():
                        if isinstance(path, str) and path.startswith("$."):
                            mapped[k] = _json_get(row, path)
                        else:
                            mapped[k] = row.get(k)

                    external_id = str(mapped.get("external_id") or row.get("id") or "")
                    if not external_id:
                        # без внешнего id груз нам неинтересен
                        continue

                    origin_text = mapped.get("origin_text")
                    dest_text = mapped.get("dest_text")
                    price_rub = mapped.get("price_rub")

                    _insert_raw_event(conn, src_id, spec.fetch.get("kind", "api"), external_id, row)
                    _insert_freight_raw(conn, spec.source, external_id, origin_text, dest_text, price_rub, row)

                    total += 1
                    if limit and total >= limit:
                        break

                conn.commit()
                log.debug("run_flow[%s]: page done, total=%s", spec.source, total)
                if limit and total >= limit:
                    break

                # курсор/пагинация
                if ep.cursor and ep.cursor.path:
                    nxt = _json_get(data, ep.cursor.path)
                    if nxt:
                        next_params = dict(ep.params)
                        if ep.cursor.param:
                            next_params[ep.cursor.param] = nxt
                        next_url = ep.url
                    else:
                        next_url = None
                else:
                    next_url = None

        log.info("run_flow: source=%s done total=%s", spec.source, total)
        return {"ok": True, "source": spec.source, "total": total}
    except Exception as e:
        log.exception("run_flow: source=%s failed: %s", getattr(spec, "source", "unknown"), e)
        return {"ok": False, "source": getattr(spec, "source", "unknown"), "error": str(e), "total": total}
    finally:
        conn.close()
