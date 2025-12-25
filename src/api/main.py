# -*- coding: utf-8 -*-
# file: src/api/main.py
#
# FoxProFlow API main.py (hardened & DevFactory-first):
#  • CORS
#  • ForceFixedLengthMiddleware (optional) — снижает риск ResponseEnded в клиентах (PowerShell)
#  • static /static mount
#  • safe router includes + autodiscover (опционально)
#  • routing hard include + haversine fallback
#  • DevFactory Gateway fallback (DB-direct), если отсутствуют реальные роуты:
#       - GET  /api/devfactory/tasks
#       - GET  /api/devfactory/tasks/{id}
#       - POST /api/devfactory/tasks/intent
#  • OUTERMOST EarlyDiagMiddleware:
#       - /diag/* и /__diag/* всегда отвечают JSON, независимо от роутеров/legacy-catch-all
#
# DEV-M0 additions:
#  • Explicit include of commercial-loop endpoints (orders/catalog):
#       - POST /api/devfactory/orders
#       - GET  /api/devfactory/orders/{dev_order_id}
#       - GET  /api/devfactory/catalog
#       - POST /api/devfactory/catalog/{order_type}/estimate

from __future__ import annotations

import os
import sys
import json
import logging
import importlib
import pkgutil
import pathlib
import datetime as dt
import uuid
import decimal
from typing import Any, Dict, List, Optional, Tuple, Iterable, Set
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request, APIRouter, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from fastapi.openapi.utils import get_openapi
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

# =============================================================================
# PYTHONPATH: <repo>/src
# =============================================================================
SRC_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

APP_TITLE = os.getenv("APP_TITLE") or os.getenv("APP_NAME", "FoxProFlow API")
APP_VERSION = os.getenv("APP_VERSION", "0.2")

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

log = logging.getLogger("uvicorn")
_LOADED_ROUTERS: List[str] = []

# =============================================================================
# Flags
# =============================================================================
_DIAG_FIXED_LEN = os.getenv("FF_DIAG_FIXED_LENGTH", "1") == "1"
_DIAG_NO_GZIP = os.getenv("FF_DIAG_DISABLE_GZIP", "1") == "1"

_ENABLE_DEBUG_ROUTER = str(os.getenv("FF_ENABLE_DEBUG_ROUTER", "0")).lower() in ("1", "true", "yes", "on")
_ENABLE_AUTOPLAN_OPS = str(os.getenv("FF_ENABLE_AUTOPLAN_OPS", "0")).lower() in ("1", "true", "yes", "on")

# DevFactory gateway fallback switch (поддерживаем оба имени env)
_ENABLE_DF_GATEWAY_FALLBACK = str(
    os.getenv("FF_ENABLE_DF_GATEWAY_FALLBACK", os.getenv("FF_ENABLE_DF_INTENT_FALLBACK", "1"))
).lower() in ("1", "true", "yes", "on")

# =============================================================================
# CORS
# =============================================================================
if os.getenv("FF_CORS_ORIGINS"):
    _allow_origins = [o.strip() for o in os.getenv("FF_CORS_ORIGINS", "").split(",") if o.strip()]
else:
    _allow_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Optional gzip switch
# =============================================================================
try:
    from starlette.middleware.gzip import GZipMiddleware
except Exception:  # pragma: no cover
    GZipMiddleware = None  # type: ignore

if not _DIAG_NO_GZIP and GZipMiddleware is not None:
    # app.add_middleware(GZipMiddleware, minimum_size=1024)
    pass

# =============================================================================
# ForceFixedLengthMiddleware (для клиентов с ResponseEnded)
# =============================================================================
class ForceFixedLengthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        state: Dict[str, Any] = {"status": 200, "headers": [], "body": bytearray()}

        async def send_wrapper(message):
            msg_type = message.get("type")
            if msg_type == "http.response.start":
                state["status"] = message["status"]
                state["headers"] = list(message.get("headers", []))
            elif msg_type == "http.response.body":
                body = message.get("body", b"") or b""
                state["body"].extend(body)
                if not message.get("more_body", False):
                    headers = [(n, v) for (n, v) in state["headers"] if n.lower() != b"content-length"]
                    headers.append((b"content-length", str(len(state["body"])).encode("ascii")))
                    await send({"type": "http.response.start", "status": state["status"], "headers": headers})
                    await send({"type": "http.response.body", "body": bytes(state["body"]), "more_body": False})
            else:
                await send(message)

        await self.app(scope, receive, send_wrapper)


if _DIAG_FIXED_LEN:
    app.add_middleware(ForceFixedLengthMiddleware)

# =============================================================================
# Static mount (/static)
# =============================================================================
STATIC_DIR_CANDIDATES = [
    SRC_DIR / "static",
    pathlib.Path(__file__).resolve().parent / "static",
]

STATIC_DIR: Optional[pathlib.Path] = None
for _dir in STATIC_DIR_CANDIDATES:
    if _dir.exists():
        STATIC_DIR = _dir
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
        log.info("Static mounted from %s -> /static", STATIC_DIR)
        break

if STATIC_DIR is None:
    log.info("Static not mounted (no directory found). Candidates=%s", STATIC_DIR_CANDIDATES)

# =============================================================================
# JSON utils
# =============================================================================
def _to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None

    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except Exception:
            return obj.decode("utf-8", "replace")

    if isinstance(obj, (dt.datetime, dt.date, dt.time)):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)

    if isinstance(obj, pathlib.Path):
        return str(obj)

    if isinstance(obj, uuid.UUID):
        return str(obj)

    if isinstance(obj, decimal.Decimal):
        try:
            return float(obj)
        except Exception:
            return str(obj)

    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(v) for v in obj]

    return str(obj)


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(_to_jsonable(payload), ensure_ascii=False).encode("utf-8")


def _json_resp(payload: Any, *, status_code: int = 200) -> Response:
    raw = _json_bytes(payload)
    return Response(
        content=raw,
        status_code=status_code,
        media_type="application/json",
        headers={"cache-control": "no-store", "content-encoding": "identity"},
    )


def _route_exists(path: str, methods: Optional[Iterable[str]] = None) -> bool:
    mset: Optional[Set[str]] = set(m.upper() for m in methods) if methods else None
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path == path:
            if mset is None:
                return True
            if mset.issubset(set(r.methods or [])):
                return True
    return False

# =============================================================================
# Exception handlers (единый JSON-стиль)
# =============================================================================
@app.exception_handler(HTTPException)
async def _on_http_exc(request: Request, exc: HTTPException):
    return _json_resp({"detail": exc.detail, "status_code": exc.status_code}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def _on_valid_exc(request: Request, exc: RequestValidationError):
    return _json_resp({"detail": "validation error", "errors": exc.errors(), "status_code": 422}, status_code=422)


@app.exception_handler(Exception)
async def _on_unhandled(request: Request, exc: Exception):
    log.exception("Unhandled exception: %r", exc)
    return _json_resp({"detail": "internal error", "error": repr(exc), "status_code": 500}, status_code=500)

# =============================================================================
# Router include helpers
# =============================================================================
def _safe_include(modname: str, *, prefix: Optional[str] = None):
    candidates: List[str] = []
    if "." in modname:
        candidates.append(modname)
    else:
        candidates.extend([f"api.routers.{modname}", f"src.api.routers.{modname}", modname])

    last_ex: Optional[Exception] = None
    for cand in candidates:
        if cand in _LOADED_ROUTERS:
            return
        try:
            mod = importlib.import_module(cand)
            router = getattr(mod, "router", None)
            if router:
                if prefix:
                    app.include_router(router, prefix=prefix)
                else:
                    app.include_router(router)
                _LOADED_ROUTERS.append(cand)
                log.info("Router included: %s%s", cand, f" (prefix={prefix})" if prefix else "")
            return
        except Exception as ex:
            last_ex = ex

    if last_ex is not None:
        log.warning("Skip router %s: %r", modname, last_ex)


def _include_guess(short: str):
    _safe_include(f"api.routers.{short}")


def _include_explicit(full: str, *, prefix: Optional[str] = None):
    _safe_include(full, prefix=prefix)

# =============================================================================
# Base routers (soft)
# =============================================================================
for name in (
    "health_ex",
    "health",
    "telemetry",
    "trips",
    "trips_recent",
    "trips_confirm",
    "fleet",
    "pipeline_summary",
    "autoplan",
    "flowlang",
    "parsers_ingest",
    "routing",
):
    _include_guess(name)

if _ENABLE_DEBUG_ROUTER:
    _include_guess("debug")

# =============================================================================
# Explicit routers (/api/*)
# =============================================================================
_include_explicit("api.routers.driver", prefix="/api")
_include_explicit("api.routers.sales", prefix="/api")
_include_explicit("api.routers.crm", prefix="/api")
_include_explicit("api.routers.onboarding", prefix="/api")

# DevFactory “full” router может быть нестабилен — ок
try:
    _include_explicit("api.routers.devfactory", prefix="/api")
except Exception:
    pass

# DEV-M0: commercial loop routers (orders/catalog) — жёстко включаем, не конфликтует с gateway fallback
_include_explicit("api.routers.devfactory_orders", prefix="/api")
_include_explicit("api.routers.devfactory_catalog", prefix="/api")

_include_explicit("api.routers.devfactory_kpi", prefix="/api")
_include_explicit("api.routers.devorders", prefix="/api")

_include_explicit("api.routers.flowmeta")
_include_explicit("api.routers.eri")

# ВАЖНО: ERI Snapshot Store держим на /api/eri/*
try:
    if not _route_exists("/api/eri/snapshot", methods=["POST"]):
        _include_explicit("api.routers.eri_store", prefix="/api")
except Exception:
    pass

# ERI Attention Signal API -> /api/eri/attention_signal*
# (поддерживаем оба варианта prefix в роутере: '/eri' или '/api/eri')
try:
    if not _route_exists("/api/eri/attention_signal", methods=["POST"]):
        _m = importlib.import_module("api.routers.eri_attention")
        _r = getattr(_m, "router", None)
        if _r:
            _rp = getattr(_r, "prefix", "") or ""
            if isinstance(_rp, str) and _rp.startswith("/api"):
                app.include_router(_r)
            else:
                app.include_router(_r, prefix="/api")
            _LOADED_ROUTERS.append("api.routers.eri_attention")
            log.info("Router included (explicit): api.routers.eri_attention -> /api/eri/attention_signal*")
except Exception as ex:  # pragma: no cover
    log.warning("Skip explicit api.routers.eri_attention: %r", ex)

_include_explicit("api.routers.flowmind")
_include_explicit("api.routers.flowworld")

_include_explicit("api.routers.flowplans", prefix="/api")
_include_explicit("api.routers.logistics_kpi")
_include_explicit("api.routers.dispatcher_alerts", prefix="/api")
_include_explicit("api.routers.dispatcher_monitor", prefix="/api")

if _ENABLE_AUTOPLAN_OPS:
    _include_guess("autoplan_ops")

# ENV: точечные включения
_extra = (os.getenv("FF_INCLUDE_ROUTERS") or "").strip()
if _extra:
    for mod in [m.strip() for m in _extra.split(",") if m.strip()]:
        _safe_include(mod)

# Autodiscover (опционально)
if os.getenv("FF_AUTODISCOVER_ROUTERS", "1") == "1":
    try:
        pkg = importlib.import_module("api.routers")
        for _finder, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
            if ispkg:
                continue
            if (modname == "autoplan_ops") and (not _ENABLE_AUTOPLAN_OPS):
                continue
            if (modname == "debug") and (not _ENABLE_DEBUG_ROUTER):
                continue
            full = f"api.routers.{modname}"
            if full in _LOADED_ROUTERS:
                continue
            _safe_include(full)
    except Exception as ex:
        log.warning("Auto-discovery failed: %r", ex)

# =============================================================================
# routing hard include + fallback
# =============================================================================
def _hard_include_routing() -> bool:
    try:
        m = importlib.import_module("api.routers.routing")
        rr = getattr(m, "router", None)
        if rr:
            app.include_router(rr)
            _LOADED_ROUTERS.append("api.routers.routing(hard)")
            return True
    except Exception as ex:
        log.warning("Hard include failed for api.routers.routing: %r", ex)
    return False


if not _route_exists("/api/routing/route"):
    _hard_include_routing()


def _ensure_routing_fallback() -> None:
    if _route_exists("/api/routing/route"):
        return
    if os.getenv("FF_ROUTING_FALLBACK", "1") != "1":
        return

    fb = APIRouter(prefix="/api/routing", tags=["routing"])

    def _hav_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        from math import radians, sin, cos, asin, sqrt
        (lat1, lon1), (lat2, lon2) = a, b
        radius = 6371.0088
        p1, p2 = radians(lat1), radians(lat2)
        dphi, dl = radians(lat2 - lat1), radians(lon2 - lon1)
        h = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
        return 2 * radius * asin(sqrt(h))

    def _hav_path_km(coords: List[Tuple[float, float]]) -> float:
        s = 0.0
        for i in range(1, len(coords)):
            s += _hav_km(coords[i - 1], coords[i])
        return s

    @fb.post("/route")
    async def route_post(payload: Dict[str, Any]):  # type: ignore[override]
        pts = payload.get("points") or payload.get("coords") or payload.get("coordinates")
        if not pts or len(pts) < 2:
            raise HTTPException(status_code=400, detail="at least 2 points required")

        coords: List[Tuple[float, float]] = []
        for p in pts:
            if isinstance(p, dict):
                lat = p.get("lat") or p.get("latitude")
                lon = p.get("lon") or p.get("lng") or p.get("longitude")
            else:
                lat, lon = p
            coords.append((float(lat), float(lon)))

        d = _hav_path_km(coords)
        return {"distance_m": d * 1000.0, "duration_s": (d / 60.0) * 3600.0, "polyline": None, "backend": "haversine"}

    @fb.get("/health")
    async def routing_health():  # type: ignore[override]
        return {"ok": True, "has_route": True, "backend": "haversine"}

    app.include_router(fb)


_ensure_routing_fallback()

# =============================================================================
# DevFactory gateway fallback (DB-direct) — ставим только если реальных роутов нет
# =============================================================================
_DF_DEPS: List[Any] = []
try:
    from api.security.flowsec_middleware import require_policies  # type: ignore
    _DF_DEPS = [Depends(require_policies("devfactory", ["view_tasks"]))]
except Exception:
    _DF_DEPS = []

_DEV_TASK_COLS_CACHE: Optional[Set[str]] = None


def _pg_connect():
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres") or "postgres"
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow") or "foxproflow"

    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    dsn = f"postgresql://{auth}{host}:{port}/{db}"

    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(dsn)


def _dev_task_cols(conn) -> Set[str]:
    global _DEV_TASK_COLS_CACHE
    if _DEV_TASK_COLS_CACHE is not None:
        return _DEV_TASK_COLS_CACHE
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='dev' AND table_name='dev_task'
            """
        )
        _DEV_TASK_COLS_CACHE = {r[0] for r in (cur.fetchall() or [])}
    return _DEV_TASK_COLS_CACHE


def _select_task_cols(cols: Set[str], *, include_specs: bool, include_result: bool) -> List[str]:
    base = [
        "id",
        "public_id",
        "stack",
        "status",
        "title",
        "autofix_enabled",
        "autofix_status",
        "created_at",
        "flowmind_plan_id",
        "flowmind_plan_domain",
    ]
    if include_specs:
        base += ["input_spec"]
    if include_result:
        base += ["result_spec", "error", "links"]

    out = [c for c in base if c in cols]
    if "id" not in out and "id" in cols:
        out = ["id"] + out
    return out


def _guess_stack(payload: Dict[str, Any]) -> str:
    v = payload.get("stack")
    if isinstance(v, str) and v.strip():
        return v.strip()

    raw_text = str(payload.get("raw_text") or "")
    rt = raw_text.lower()

    # Эвристика по тексту (полезно, когда клиент не передаёт stack)
    if any(k in rt for k in ("sql", "postgres", "ddl", "schema", "migration", "index", "psql")):
        return "sql-postgres"
    if any(k in rt for k in ("pwsh", "powershell", ".ps1", "invoke-restmethod", "curl ", "ff_api_base_url")):
        return "pwsh"
    if any(k in rt for k in ("fastapi", "uvicorn", "pydantic", "celery", "python", ".py", "api-роутер", "router", "endpoint")):
        return "python_backend"
    if any(k in rt for k in ("typescript", "react", "tsx", "node", "frontend", "ui", "vite", "next")):
        return "typescript"

    return "generic"


def _guess_title(project_ref: str, raw_text: str) -> str:
    first = (raw_text or "").splitlines()[0].strip()
    if project_ref and first:
        return f"[{project_ref}] {first}"
    return first or (f"[{project_ref}] DevTask (intent)" if project_ref else "DevTask (intent)")


def _insert_dev_task(conn, *, stack: str, title: str, input_spec: Dict[str, Any]) -> Dict[str, Any]:
    cols = _dev_task_cols(conn)

    fields: List[str] = []
    placeholders: List[str] = []
    values: List[Any] = []

    def add(col: str, placeholder: str, value: Any):
        if col in cols:
            fields.append(col)
            placeholders.append(placeholder)
            values.append(value)

    add("stack", "%s", stack)
    add("title", "%s", title)
    add("status", "%s", "new")
    add("input_spec", "%s::jsonb", json.dumps(input_spec, ensure_ascii=False))

    # optional
    add("result_spec", "%s::jsonb", "{}")
    add("source", "%s", "devfactory.intent.fallback")
    add("autofix_enabled", "%s", False)
    add("autofix_status", "%s", "disabled")

    if "public_id" in cols:
        add("public_id", "%s", str(uuid.uuid4()))

    if not fields:
        raise RuntimeError("dev.dev_task: no insertable columns discovered")

    prefer_return = [
        "id",
        "public_id",
        "stack",
        "status",
        "title",
        "autofix_enabled",
        "autofix_status",
        "created_at",
        "flowmind_plan_id",
        "flowmind_plan_domain",
    ]
    returning = [c for c in prefer_return if c in cols]
    if "id" not in returning:
        returning = ["id"]

    sql = f"INSERT INTO dev.dev_task ({', '.join(fields)}) VALUES ({', '.join(placeholders)}) RETURNING {', '.join(returning)}"
    with conn.cursor() as cur:
        cur.execute(sql, tuple(values))
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Insert into dev.dev_task returned no row")
        out = {returning[i]: row[i] for i in range(len(returning))}
    conn.commit()
    return out


def _ensure_df_gateway_routes() -> None:
    if not _ENABLE_DF_GATEWAY_FALLBACK:
        return

    mounted_any = False

    # GET /api/devfactory/tasks
    if not _route_exists("/api/devfactory/tasks", methods=["GET"]):

        async def df_list_tasks(request: Request):
            q = request.query_params
            try:
                limit = int((q.get("limit") or "50").strip())
            except Exception:
                limit = 50
            limit = max(1, min(500, limit))

            status = (q.get("status") or "").strip() or None
            stack = (q.get("stack") or "").strip() or None

            try:
                include_specs = int((q.get("include_specs") or "0").strip())
            except Exception:
                include_specs = 0
            try:
                include_result = int((q.get("include_result") or "0").strip())
            except Exception:
                include_result = 0

            conn = _pg_connect()
            try:
                cols = _dev_task_cols(conn)
                select_cols = _select_task_cols(cols, include_specs=bool(include_specs), include_result=bool(include_result))

                where = []
                params: List[Any] = []
                if status and ("status" in cols):
                    where.append("status = %s")
                    params.append(status)
                if stack and ("stack" in cols):
                    where.append("stack = %s")
                    params.append(stack)

                where_sql = ("WHERE " + " AND ".join(where)) if where else ""
                order_col = "created_at" if "created_at" in cols else "id"

                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT {", ".join(select_cols)}
                        FROM dev.dev_task
                        {where_sql}
                        ORDER BY {order_col} DESC
                        LIMIT %s
                        """,
                        (*params, int(limit)),
                    )
                    rows = cur.fetchall() or []

                out: List[Dict[str, Any]] = []
                for r in rows:
                    out.append({select_cols[i]: r[i] for i in range(len(select_cols))})

                return _json_resp(out)

            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        app.add_api_route(
            "/api/devfactory/tasks",
            df_list_tasks,
            methods=["GET"],
            tags=["devfactory_gateway"],
            dependencies=_DF_DEPS,
            summary="(fallback) list DevTasks (DB-direct)",
        )
        mounted_any = True

    # GET /api/devfactory/tasks/{id}
    if not any(isinstance(r, APIRoute) and r.path == "/api/devfactory/tasks/{task_id}" for r in app.routes):

        async def df_get_task(task_id: int):
            conn = _pg_connect()
            try:
                cols = _dev_task_cols(conn)
                select_cols = _select_task_cols(cols, include_specs=True, include_result=True)

                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT {", ".join(select_cols)}
                        FROM dev.dev_task
                        WHERE id = %s
                        """,
                        (int(task_id),),
                    )
                    row = cur.fetchone()

                if not row:
                    raise HTTPException(status_code=404, detail="DevTask not found")

                out = {select_cols[i]: row[i] for i in range(len(select_cols))}
                return _json_resp(out)

            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        app.add_api_route(
            "/api/devfactory/tasks/{task_id}",
            df_get_task,
            methods=["GET"],
            tags=["devfactory_gateway"],
            dependencies=_DF_DEPS,
            summary="(fallback) get DevTask by id (DB-direct)",
        )
        mounted_any = True

    # POST /api/devfactory/tasks/intent
    if not _route_exists("/api/devfactory/tasks/intent", methods=["POST"]):

        async def df_intent(payload: Dict[str, Any]):  # type: ignore[override]
            project_ref = (payload.get("project_ref") or "").strip()
            language = (payload.get("language") or "ru").strip() or "ru"
            channel = (payload.get("channel") or "text").strip() or "text"
            raw_text = payload.get("raw_text")

            if not project_ref:
                raise HTTPException(status_code=422, detail="project_ref is required")
            if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
                raise HTTPException(status_code=422, detail="raw_text is required")

            stack = _guess_stack(payload)
            title = _guess_title(project_ref, raw_text)

            input_spec = {
                "intent": payload.get("intent"),
                "raw_text": raw_text,
                "intent_context": {"project_ref": project_ref, "language": language, "channel": channel},
            }

            conn = _pg_connect()
            try:
                out = _insert_dev_task(conn, stack=stack, title=title, input_spec=input_spec)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            resp = {
                "id": out.get("id"),
                "public_id": out.get("public_id"),
                "status": out.get("status", "new"),
                "stack": out.get("stack", stack),
                "title": out.get("title", title),
                "created_at": out.get("created_at"),
            }
            return _json_resp(resp)

        app.add_api_route(
            "/api/devfactory/tasks/intent",
            df_intent,
            methods=["POST"],
            tags=["devfactory_gateway"],
            dependencies=_DF_DEPS,
            summary="(fallback) create DevTask from raw_text (DB-direct)",
        )
        mounted_any = True

    if mounted_any:
        log.info("DF gateway fallback mounted: /api/devfactory/tasks + /tasks/{id} + /tasks/intent")


_ensure_df_gateway_routes()

# =============================================================================
# OUTERMOST: EarlyDiagMiddleware (железно отвечает JSON)
# =============================================================================
class EarlyDiagMiddleware:
    _PATHS = {
        "/diag/ping",
        "/diag/config",
        "/diag/routers",
        "/diag/routes",
        "/__diag/ping",
        "/__diag/config",
        "/__diag/routers",
        "/__diag/routes",
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if path not in self._PATHS:
            await self.app(scope, receive, send)
            return

        try:
            qs = parse_qs((scope.get("query_string", b"") or b"").decode("utf-8", "ignore"))

            if path.endswith("/ping"):
                payload = {"ok": True, "owner": "early_diag_mw", "path": path, "ts_utc": dt.datetime.utcnow().isoformat()}

            elif path.endswith("/routers"):
                payload = {"ok": True, "owner": "early_diag_mw", "routers": list(_LOADED_ROUTERS), "ts_utc": dt.datetime.utcnow().isoformat()}

            elif path.endswith("/routes"):
                contains = (qs.get("contains", [""])[0] or "").strip()
                contains_l = contains.lower() if contains else ""

                try:
                    limit_raw = (qs.get("limit", ["400"])[0] or "400").strip()
                    limit = int(limit_raw)
                except Exception:
                    limit = 400
                limit = max(1, min(5000, limit))

                routes: List[Dict[str, Any]] = []
                for r in app.routes:
                    if not isinstance(r, APIRoute):
                        continue
                    p = r.path or ""
                    if contains_l and (contains_l not in p.lower()):
                        continue
                    routes.append({"path": p, "methods": sorted(r.methods or []), "name": r.name})
                    if len(routes) >= limit:
                        break

                payload = {"ok": True, "owner": "early_diag_mw", "contains": contains or None, "limit": limit, "routes": routes, "ts_utc": dt.datetime.utcnow().isoformat()}

            else:
                payload = {
                    "ok": True,
                    "owner": "early_diag_mw",
                    "app": {"title": APP_TITLE, "version": APP_VERSION},
                    "diag": {"fixed_length_middleware": _DIAG_FIXED_LEN, "disable_gzip": _DIAG_NO_GZIP},
                    "cors": {"allow_origins": _allow_origins},
                    "static": {
                        "mounted": STATIC_DIR is not None,
                        "dir": str(STATIC_DIR) if STATIC_DIR is not None else None,
                        "candidates": [str(p) for p in STATIC_DIR_CANDIDATES],
                    },
                    "flags": {
                        "FF_AUTODISCOVER_ROUTERS": os.getenv("FF_AUTODISCOVER_ROUTERS", "1"),
                        "FF_ENABLE_AUTOPLAN_OPS": os.getenv("FF_ENABLE_AUTOPLAN_OPS", "0"),
                        "FF_ENABLE_DEBUG_ROUTER": os.getenv("FF_ENABLE_DEBUG_ROUTER", "0"),
                        "FF_INCLUDE_ROUTERS": os.getenv("FF_INCLUDE_ROUTERS", ""),
                        "FF_ROUTING_FALLBACK": os.getenv("FF_ROUTING_FALLBACK", "1"),
                        "FF_ENABLE_DF_GATEWAY_FALLBACK": os.getenv("FF_ENABLE_DF_GATEWAY_FALLBACK", os.getenv("FF_ENABLE_DF_INTENT_FALLBACK", "1")),
                    },
                    "routes_present": {
                        "df_tasks_get": _route_exists("/api/devfactory/tasks", methods=["GET"]),
                        "df_intent_post": _route_exists("/api/devfactory/tasks/intent", methods=["POST"]),
                        # DEV-M0 коммерческий контур
                        "df_orders_post": _route_exists("/api/devfactory/orders", methods=["POST"]),
                        "df_order_get": _route_exists("/api/devfactory/orders/{dev_order_id}", methods=["GET"]),
                        "df_catalog_get": _route_exists("/api/devfactory/catalog", methods=["GET"]),
                        "eri_snapshot_post": _route_exists("/api/eri/snapshot", methods=["POST"]),
                        "routing_route_post": _route_exists("/api/routing/route", methods=["POST"]),
                    },
                    "notes": [
                        "Prefer IPv4 base http://127.0.0.1:8080 on Windows (localhost may resolve to ::1).",
                        "If you run `docker compose exec api python -c ...`, import as `from src.api.main import app` (not api.main).",
                    ],
                    "ts_utc": dt.datetime.utcnow().isoformat(),
                }

            resp = _json_resp(payload, status_code=200)
            await resp(scope, receive, send)
            return

        except Exception as ex:
            err = {"ok": False, "owner": "early_diag_mw", "path": path, "error": repr(ex), "ts_utc": dt.datetime.utcnow().isoformat()}
            resp = _json_resp(err, status_code=500)
            await resp(scope, receive, send)
            return


# ВАЖНО: добавляем ПОСЛЕДНИМ — чтобы EarlyDiag был outermost
app.add_middleware(EarlyDiagMiddleware)

# =============================================================================
# OpenAPI
# =============================================================================
def custom_openapi():
    if getattr(app, "openapi_schema", None):
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=APP_TITLE,
        version=APP_VERSION,
        description="FoxProFlow API",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return openapi_schema


app.openapi = custom_openapi  # type: ignore[assignment]
