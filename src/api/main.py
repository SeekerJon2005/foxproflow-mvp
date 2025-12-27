# -*- coding: utf-8 -*-
# file: src/api/main.py
#
# FoxProFlow API main.py (hardened & DevFactory-first)
# Goals:
#  - No 500-magic: errors must be explainable (T9 envelope)
#  - X-Correlation-ID on ALL responses (incl /diag/*)
#  - EarlyDiagMiddleware: /diag/* always JSON
#  - Safe router includes (no collisions), optional autodiscover
#  - DevOrders v1 alias -> v2 (optional mount)
#  - Routing fallback (haversine)
#  - DevFactory DB-direct fallback only if real routes absent (and strict contract)

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
import re
from typing import Any, Dict, List, Optional, Tuple, Iterable, Set, Literal
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request, APIRouter, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from fastapi.openapi.utils import get_openapi
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope, Receive, Send
from starlette.middleware.base import BaseHTTPMiddleware

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
_SKIPPED_ROUTERS: List[Dict[str, Any]] = []

# =============================================================================
# Flags
# =============================================================================
_DIAG_FIXED_LEN = os.getenv("FF_DIAG_FIXED_LENGTH", "1") == "1"
_DIAG_NO_GZIP = os.getenv("FF_DIAG_DISABLE_GZIP", "1") == "1"

_ENABLE_DEBUG_ROUTER = str(os.getenv("FF_ENABLE_DEBUG_ROUTER", "0")).lower() in ("1", "true", "yes", "on")
_ENABLE_AUTOPLAN_OPS = str(os.getenv("FF_ENABLE_AUTOPLAN_OPS", "0")).lower() in ("1", "true", "yes", "on")

_ENABLE_DF_GATEWAY_FALLBACK = str(
    os.getenv("FF_ENABLE_DF_GATEWAY_FALLBACK", os.getenv("FF_ENABLE_DF_INTENT_FALLBACK", "1"))
).lower() in ("1", "true", "yes", "on")

_ENABLE_DEVORDERS_LEGACY = str(os.getenv("FF_ENABLE_DEVORDERS_LEGACY", "0")).lower() in ("1", "true", "yes", "on")

_ENABLE_DEVORDERS_V1_ALIAS = str(os.getenv("FF_ENABLE_DEVORDERS_V1_ALIAS", "1")).lower() in ("1", "true", "yes", "on")
_DEVORDERS_V2_PREFIX = (os.getenv("FF_DEVORDERS_V2_PREFIX", "/devorders/v2") or "/devorders/v2").strip() or "/devorders/v2"
_OPENAPI_INCLUDE_DEVORDERS_V1_ALIAS = str(os.getenv("FF_OPENAPI_INCLUDE_DEVORDERS_V1_ALIAS", "1")).lower() in (
    "1",
    "true",
    "yes",
    "on",
)

_ENFORCE_NO_ROUTE_COLLISIONS = str(os.getenv("FF_ENFORCE_NO_ROUTE_COLLISIONS", "1")).lower() in (
    "1",
    "true",
    "yes",
    "on",
)

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
# Correlation ID helpers
# =============================================================================
_HDR_CANDIDATES = ("x-correlation-id", "x-request-id")
_MAX_CID_LEN = 128
_SAFE_CID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,127}$")


def _sanitize_cid(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    v = str(val).strip()
    if not v or len(v) > _MAX_CID_LEN:
        return None
    if "\n" in v or "\r" in v:
        return None
    if not _SAFE_CID_RE.match(v):
        return None
    return v


def _new_cid() -> str:
    return uuid.uuid4().hex


def _ensure_scope_state(scope: Scope) -> Dict[str, Any]:
    st = scope.get("state")
    if not isinstance(st, dict):
        st = {}
        scope["state"] = st
    return st


def _ensure_scope_correlation_id(scope: Scope) -> str:
    st = _ensure_scope_state(scope)

    existing = st.get("correlation_id")
    if isinstance(existing, str) and existing:
        return existing

    try:
        for (n, v) in (scope.get("headers") or []):
            if not isinstance(n, (bytes, bytearray)):
                continue
            name = n.decode("latin-1").lower()
            if name in _HDR_CANDIDATES:
                raw = v.decode("utf-8", "ignore") if isinstance(v, (bytes, bytearray)) else str(v)
                s = _sanitize_cid(raw)
                if s:
                    st["correlation_id"] = s
                    return s
    except Exception:
        pass

    cid = _new_cid()
    st["correlation_id"] = cid
    return cid


def _get_request_correlation_id(request: Request) -> str:
    cid = getattr(request.state, "correlation_id", None)
    if isinstance(cid, str) and cid:
        return cid

    for h in _HDR_CANDIDATES:
        s = _sanitize_cid(request.headers.get(h))
        if s:
            request.state.correlation_id = s
            return s

    cid = _new_cid()
    request.state.correlation_id = cid
    return cid


def _ensure_corr_header(resp: Response, cid: str) -> None:
    try:
        if "X-Correlation-ID" not in resp.headers:
            resp.headers["X-Correlation-ID"] = cid
    except Exception:
        pass


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = _get_request_correlation_id(request)
        resp: Response = await call_next(request)
        _ensure_corr_header(resp, cid)
        return resp

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


def _json_resp(payload: Any, *, status_code: int = 200, correlation_id: Optional[str] = None) -> Response:
    raw = _json_bytes(payload)
    headers = {"cache-control": "no-store", "content-encoding": "identity"}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    return Response(content=raw, status_code=status_code, media_type="application/json", headers=headers)


def _route_exists(path: str, methods: Optional[Iterable[str]] = None) -> bool:
    mset: Optional[Set[str]] = set(m.upper() for m in methods) if methods else None
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path == path:
            if mset is None:
                return True
            if mset.issubset(set(r.methods or [])):
                return True
    return False


def _existing_route_keys() -> Set[Tuple[str, str]]:
    keys: Set[Tuple[str, str]] = set()
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        p = r.path or ""
        for m in (r.methods or []):
            keys.add((p, str(m)))
    return keys


def _join_prefix(prefix: Optional[str], path: str) -> str:
    if not prefix:
        return path
    pfx = str(prefix)
    if not pfx.startswith("/"):
        pfx = "/" + pfx
    if pfx.endswith("/"):
        pfx = pfx[:-1]
    if not path.startswith("/"):
        path = "/" + path
    if path.startswith(pfx + "/"):
        return path
    return pfx + path

# =============================================================================
# T9 Error UX (unified envelope)
# =============================================================================
ErrorKind = Literal["policy", "dependency", "validation", "conflict", "internal"]


def _utc_ts() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _kind_from_status(code: int) -> ErrorKind:
    if code in (401, 403):
        return "policy"
    if code in (409, 412):
        return "conflict"
    if code in (400, 404, 405, 422):
        return "validation"
    if code in (429, 503, 504):
        return "dependency"
    if code >= 500:
        return "internal"
    return "validation"


def _t9_payload(
    *,
    kind: ErrorKind,
    message_ru: str,
    why_ru: str,
    next_step_ru: str,
    status_code: int,
    correlation_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    err: Dict[str, Any] = {"kind": kind, "message_ru": message_ru, "why_ru": why_ru, "next_step_ru": next_step_ru}
    if details:
        err["details"] = details
    return {"ok": False, "error": err, "correlation_id": correlation_id, "ts": _utc_ts(), "status_code": status_code}


@app.exception_handler(RequestValidationError)
async def _t9_validation_handler(request: Request, exc: RequestValidationError):
    cid = _get_request_correlation_id(request)
    payload = _t9_payload(
        kind="validation",
        message_ru="Неверные данные запроса.",
        why_ru="Запрос не соответствует контракту API (типы/поля/формат).",
        next_step_ru="Исправь поля согласно контракту и повтори запрос. Подробности см. в error.details.errors.",
        status_code=422,
        correlation_id=cid,
        details={"errors": exc.errors()},
    )
    return _json_resp(payload, status_code=422, correlation_id=cid)


@app.exception_handler(HTTPException)
async def _t9_http_handler(request: Request, exc: HTTPException):
    cid = _get_request_correlation_id(request)

    # pass-through for already-enveloped details (например FlowSec)
    if isinstance(exc.detail, dict) and exc.detail.get("ok") is False and "error" in exc.detail:
        det = dict(exc.detail)
        det.setdefault("correlation_id", cid)
        det.setdefault("status_code", exc.status_code)
        det.setdefault("ts", _utc_ts())
        return _json_resp(det, status_code=exc.status_code, correlation_id=cid)

    msg = exc.detail if isinstance(exc.detail, str) else (str(exc.detail) if exc.detail is not None else "HTTP-ошибка.")
    kind = _kind_from_status(exc.status_code)

    payload = _t9_payload(
        kind=kind,
        message_ru=msg or "Ошибка запроса.",
        why_ru="HTTP-ошибка на уровне API.",
        next_step_ru="Проверь параметры запроса и права доступа; при повторе — смотри логи по correlation_id.",
        status_code=exc.status_code,
        correlation_id=cid,
    )
    return _json_resp(payload, status_code=exc.status_code, correlation_id=cid)


@app.exception_handler(Exception)
async def _t9_unhandled_handler(request: Request, exc: Exception):
    cid = _get_request_correlation_id(request)
    log.exception("Unhandled exception; correlation_id=%s", cid)
    payload = _t9_payload(
        kind="internal",
        message_ru="Внутренняя ошибка сервера.",
        why_ru="Необработанное исключение внутри сервиса.",
        next_step_ru="Повтори запрос. Если воспроизводится — открой логи API/worker и ищи correlation_id.",
        status_code=500,
        correlation_id=cid,
    )
    return _json_resp(payload, status_code=500, correlation_id=cid)

# =============================================================================
# Router include helpers
# =============================================================================
def _candidates_for(modname: str) -> List[str]:
    mod = (modname or "").strip()
    if not mod:
        return []
    out: List[str] = []

    if mod.startswith("api.routers."):
        out.append(mod)
        out.append("src." + mod)
        return out

    if mod.startswith("src.api.routers."):
        out.append(mod)
        out.append(mod[len("src.") :])
        return out

    if "." in mod:
        out.append(mod)
        if mod.startswith("api."):
            out.append("src." + mod)
        return out

    out.extend([f"api.routers.{mod}", f"src.api.routers.{mod}", mod])
    return out


def _safe_include(modname: str, *, prefix: Optional[str] = None):
    candidates = _candidates_for(modname)
    if not candidates:
        return

    last_ex: Optional[Exception] = None
    for cand in candidates:
        if cand in _LOADED_ROUTERS:
            return
        try:
            mod = importlib.import_module(cand)
            router = getattr(mod, "router", None)
            if not router:
                return

            eff_prefix = prefix
            try:
                rp = getattr(router, "prefix", "") or ""
                if isinstance(rp, str) and rp.startswith("/api") and (prefix == "/api"):
                    eff_prefix = None
            except Exception:
                eff_prefix = prefix

            if _ENFORCE_NO_ROUTE_COLLISIONS:
                existing = _existing_route_keys()
                collisions: List[Dict[str, Any]] = []
                for rr in getattr(router, "routes", []) or []:
                    if not isinstance(rr, APIRoute):
                        continue
                    full_path = _join_prefix(eff_prefix, rr.path)
                    for m in (rr.methods or []):
                        key = (full_path, str(m))
                        if key in existing:
                            collisions.append({"path": full_path, "method": str(m), "name": rr.name, "router": cand})
                if collisions:
                    _SKIPPED_ROUTERS.append({"router": cand, "reason": "route_collision", "prefix": eff_prefix, "collisions": collisions})
                    log.warning("Skip router %s due to route collisions: %s", cand, collisions[:6])
                    return

            if eff_prefix:
                app.include_router(router, prefix=eff_prefix)
            else:
                app.include_router(router)

            _LOADED_ROUTERS.append(cand)
            log.info("Router included: %s%s", cand, f" (prefix={eff_prefix})" if eff_prefix else "")
            return

        except Exception as ex:
            last_ex = ex

    if last_ex is not None:
        _SKIPPED_ROUTERS.append({"router": str(modname), "reason": "import_error", "prefix": prefix, "error": repr(last_ex), "candidates": candidates})
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

try:
    _include_explicit("api.routers.devfactory", prefix="/api")
except Exception:
    pass

_include_explicit("api.routers.devfactory_kpi", prefix="/api")
_include_explicit("api.routers.dev_orders")

if _ENABLE_DEVORDERS_LEGACY:
    _include_explicit("api.routers.devorders", prefix="/api")

_include_explicit("api.routers.flowmeta")
_include_explicit("api.routers.eri")

try:
    if not _route_exists("/api/eri/snapshot", methods=["POST"]):
        _include_explicit("api.routers.eri_store", prefix="/api")
except Exception:
    pass

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

_extra = (os.getenv("FF_INCLUDE_ROUTERS") or "").strip()
if _extra:
    for mod in [m.strip() for m in _extra.split(",") if m.strip()]:
        _safe_include(mod)

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
            if modname == "devorders":
                continue
            full = f"api.routers.{modname}"
            if full in _LOADED_ROUTERS:
                continue
            _safe_include(full)
    except Exception as ex:
        log.warning("Auto-discovery failed: %r", ex)

# =============================================================================
# DevOrders v1 alias -> v2 (transparent proxy, no redirects)
# =============================================================================
class DevOrdersV1AliasApp:
    def __init__(self, target_asgi: Any, *, target_prefix: str) -> None:
        self._target = target_asgi
        tp = (target_prefix or "").strip() or "/devorders/v2"
        self._target_prefix = tp.rstrip("/")

    @staticmethod
    def _norm_path(p: str) -> str:
        if not p:
            return "/"
        if not p.startswith("/"):
            return "/" + p
        return p

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._target(scope, receive, send)
            return

        sub = self._norm_path(str(scope.get("path") or "/"))
        if sub == "/":
            new_path = self._target_prefix
        else:
            new_path = self._target_prefix + sub

        new_scope = dict(scope)
        new_scope["path"] = new_path
        try:
            new_scope["raw_path"] = new_path.encode("utf-8")
        except Exception:
            pass

        await self._target(new_scope, receive, send)


def _mount_devorders_v1_alias() -> None:
    if not _ENABLE_DEVORDERS_V1_ALIAS:
        return

    for r in app.routes:
        if isinstance(r, APIRoute) and (r.path == "/api/devorders" or r.path.startswith("/api/devorders/")):
            log.warning("DevOrders v1 alias NOT mounted: real APIRoutes exist under /api/devorders")
            return

    app.mount(
        "/api/devorders",
        DevOrdersV1AliasApp(app.router, target_prefix=_DEVORDERS_V2_PREFIX),
        name="devorders_v1_alias",
    )
    log.info("DevOrders v1 alias mounted: /api/devorders* -> %s*", _DEVORDERS_V2_PREFIX)


_mount_devorders_v1_alias()

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
# DevFactory DB-direct fallback (only if real routes absent)
# =============================================================================
_DF_DEPS_READ: List[Any] = []
_DF_DEPS_WRITE: List[Any] = []

try:
    from src.api.security.flowsec_middleware import require_policies  # type: ignore
    _DF_DEPS_READ = [Depends(require_policies("devfactory", ["view_tasks"]))]
except Exception:
    _DF_DEPS_READ = []

try:
    from src.api.security.flowsec_middleware import require_devfactory_task_write  # type: ignore
    _DF_DEPS_WRITE = [Depends(require_devfactory_task_write)]
except Exception:
    try:
        from src.api.security.flowsec_middleware import require_policies  # type: ignore
        _DF_DEPS_WRITE = [Depends(require_policies("devfactory", ["manage_tasks"]))]
    except Exception:
        _DF_DEPS_WRITE = _DF_DEPS_READ[:]

_DEV_TASK_COLS_CACHE: Optional[Set[str]] = None


def _db_connect_timeout_s() -> int:
    raw = (os.getenv("FF_DB_CONNECT_TIMEOUT_S") or os.getenv("POSTGRES_CONNECT_TIMEOUT") or "5").strip()
    try:
        v = int(raw)
    except Exception:
        v = 5
    return max(1, min(60, v))


def _pg_connect():
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres") or "postgres"
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow") or "foxproflow"

    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    dsn = f"postgresql://{auth}{host}:{port}/{db}"
    timeout_s = _db_connect_timeout_s()

    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn, connect_timeout=timeout_s)
    except Exception:
        try:
            import psycopg2 as psycopg  # type: ignore
            return psycopg.connect(dsn, connect_timeout=timeout_s)
        except Exception as ex:
            raise HTTPException(
                status_code=503,
                detail=_t9_payload(
                    kind="dependency",
                    message_ru="Postgres недоступен.",
                    why_ru="Не удалось подключиться к Postgres для DevFactory fallback.",
                    next_step_ru="Проверь Postgres и переменные POSTGRES_*, затем повтори.",
                    status_code=503,
                    correlation_id="",
                    details={"error": repr(ex), "host": host, "port": port, "db": db},
                ),
            )


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
        "created_at",
        "updated_at",
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
    if any(k in rt for k in ("sql", "postgres", "ddl", "schema", "migration", "index", "psql")):
        return "sql-postgres"
    if any(k in rt for k in ("pwsh", "powershell", ".ps1", "invoke-restmethod", "curl ", "ff_api_base_url")):
        return "pwsh"
    if any(k in rt for k in ("fastapi", "uvicorn", "pydantic", "celery", "python", ".py", "router", "endpoint")):
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

    if "public_id" in cols:
        add("public_id", "%s", str(uuid.uuid4()))

    if not fields:
        raise RuntimeError("dev.dev_task: no insertable columns discovered")

    returning = [c for c in ("id", "public_id", "stack", "status", "title", "created_at") if c in cols]
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


def _t9_422_extra(request: Request, key: str, value: Any) -> HTTPException:
    cid = _get_request_correlation_id(request)
    detail = _t9_payload(
        kind="validation",
        message_ru="Неверные данные запроса.",
        why_ru="Передано лишнее поле, не предусмотренное контрактом.",
        next_step_ru="Удали лишние поля и повтори запрос.",
        status_code=422,
        correlation_id=cid,
        details={"errors": [{"type": "extra_forbidden", "loc": ["body", key], "msg": "Extra inputs are not permitted", "input": value}]},
    )
    return HTTPException(status_code=422, detail=detail)


def _ensure_df_gateway_routes() -> None:
    if not _ENABLE_DF_GATEWAY_FALLBACK:
        return

    if not _route_exists("/api/devfactory/tasks", methods=["GET"]):

        async def df_list_tasks(request: Request):
            q = request.query_params
            try:
                limit = int((q.get("limit") or "50").strip())
            except Exception:
                limit = 50
            limit = max(1, min(500, limit))

            conn = _pg_connect()
            try:
                cols = _dev_task_cols(conn)
                select_cols = _select_task_cols(cols, include_specs=False, include_result=False)

                order_col = "created_at" if "created_at" in cols else "id"
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT {", ".join(select_cols)}
                        FROM dev.dev_task
                        ORDER BY {order_col} DESC
                        LIMIT %s
                        """,
                        (int(limit),),
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
            dependencies=_DF_DEPS_READ,
            summary="(fallback) list DevTasks (DB-direct)",
        )

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
            dependencies=_DF_DEPS_READ,
            summary="(fallback) get DevTask by id (DB-direct)",
        )

    if not _route_exists("/api/devfactory/tasks/intent", methods=["POST"]):

        async def df_intent(request: Request, payload: Dict[str, Any]):  # type: ignore[override]
            allowed = {"project_ref", "raw_text", "language", "channel", "stack"}
            for k in list(payload.keys()):
                if k not in allowed:
                    raise _t9_422_extra(request, k, payload.get(k))

            project_ref = (payload.get("project_ref") or "").strip()
            language = (payload.get("language") or "ru").strip() or "ru"
            channel = (payload.get("channel") or "text").strip() or "text"
            raw_text = payload.get("raw_text")

            if not project_ref:
                raise HTTPException(status_code=422, detail=_t9_payload(
                    kind="validation",
                    message_ru="Не указан project_ref.",
                    why_ru="Для intent требуется project_ref.",
                    next_step_ru="Передай project_ref в теле запроса.",
                    status_code=422,
                    correlation_id=_get_request_correlation_id(request),
                ))
            if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
                raise HTTPException(status_code=422, detail=_t9_payload(
                    kind="validation",
                    message_ru="Не указан raw_text.",
                    why_ru="Для intent требуется raw_text (строка).",
                    next_step_ru="Передай raw_text в теле запроса.",
                    status_code=422,
                    correlation_id=_get_request_correlation_id(request),
                ))

            stack = _guess_stack(payload)
            title = _guess_title(project_ref, raw_text)

            input_spec = {
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
            dependencies=_DF_DEPS_WRITE,
            summary="(fallback) create DevTask from raw_text (DB-direct)",
        )

    log.info("DF gateway fallback checked (mounted only if routes missing).")


_ensure_df_gateway_routes()

# =============================================================================
# EarlyDiagMiddleware (железно отвечает JSON)
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

        cid = _ensure_scope_correlation_id(scope)

        try:
            qs = parse_qs((scope.get("query_string", b"") or b"").decode("utf-8", "ignore"))

            if path.endswith("/ping"):
                payload = {"ok": True, "owner": "early_diag_mw", "path": path, "ts_utc": dt.datetime.utcnow().isoformat(), "correlation_id": cid}

            elif path.endswith("/routers"):
                payload = {
                    "ok": True,
                    "owner": "early_diag_mw",
                    "routers_loaded": list(_LOADED_ROUTERS),
                    "routers_skipped": list(_SKIPPED_ROUTERS),
                    "ts_utc": dt.datetime.utcnow().isoformat(),
                    "correlation_id": cid,
                }

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
                    if isinstance(r, APIRoute):
                        p = r.path or ""
                        if contains_l and (contains_l not in p.lower()):
                            continue
                        routes.append({"path": p, "methods": sorted(r.methods or []), "name": r.name, "kind": "APIRoute"})
                        if len(routes) >= limit:
                            break
                        continue

                    p2 = getattr(r, "path", None)
                    if isinstance(p2, str) and p2:
                        if contains_l and (contains_l not in p2.lower()):
                            continue
                        routes.append({"path": p2, "methods": ["*"], "name": getattr(r, "name", r.__class__.__name__), "kind": r.__class__.__name__})
                        if len(routes) >= limit:
                            break

                payload = {
                    "ok": True,
                    "owner": "early_diag_mw",
                    "contains": contains or None,
                    "limit": limit,
                    "routes": routes,
                    "ts_utc": dt.datetime.utcnow().isoformat(),
                    "correlation_id": cid,
                }

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
                        "FF_ENABLE_DEVORDERS_LEGACY": os.getenv("FF_ENABLE_DEVORDERS_LEGACY", "0"),
                        "FF_ENABLE_DEVORDERS_V1_ALIAS": os.getenv("FF_ENABLE_DEVORDERS_V1_ALIAS", "1"),
                        "FF_DEVORDERS_V2_PREFIX": os.getenv("FF_DEVORDERS_V2_PREFIX", "/devorders/v2"),
                        "FF_OPENAPI_INCLUDE_DEVORDERS_V1_ALIAS": os.getenv("FF_OPENAPI_INCLUDE_DEVORDERS_V1_ALIAS", "1"),
                        "FF_ENFORCE_NO_ROUTE_COLLISIONS": os.getenv("FF_ENFORCE_NO_ROUTE_COLLISIONS", "1"),
                    },
                    "notes": [
                        "Prefer IPv4 base http://127.0.0.1:8080 on Windows (localhost may resolve to ::1).",
                        "X-Correlation-ID is always present on responses.",
                        "Errors use T9 envelope: ok=false + error.kind/message/why/next_step + correlation_id.",
                    ],
                    "ts_utc": dt.datetime.utcnow().isoformat(),
                    "correlation_id": cid,
                }

            resp = _json_resp(payload, status_code=200, correlation_id=cid)
            await resp(scope, receive, send)
            return

        except Exception as ex:
            err = {"ok": False, "owner": "early_diag_mw", "path": path, "error": repr(ex), "ts_utc": dt.datetime.utcnow().isoformat(), "correlation_id": cid}
            resp = _json_resp(err, status_code=500, correlation_id=cid)
            await resp(scope, receive, send)
            return


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

    # Inject alias paths into OpenAPI (docs-only): /api/devorders/* mirrors /devorders/v2/*
    try:
        if _OPENAPI_INCLUDE_DEVORDERS_V1_ALIAS:
            v2p = _DEVORDERS_V2_PREFIX.rstrip("/")
            alias_pfx = "/api/devorders"
            paths = openapi_schema.get("paths") or {}
            for p, ops in list(paths.items()):
                if p == v2p or p.startswith(v2p + "/"):
                    ap = alias_pfx + p[len(v2p):]
                    if ap not in paths:
                        paths[ap] = ops
            openapi_schema["paths"] = paths
    except Exception as ex:  # pragma: no cover
        log.warning("OpenAPI devorders alias injection skipped: %r", ex)

    app.openapi_schema = openapi_schema
    return openapi_schema


app.openapi = custom_openapi  # type: ignore[assignment]

# =============================================================================
# IMPORTANT: install CorrelationIdMiddleware LAST (outermost), so it wraps EarlyDiag.
# =============================================================================
app.add_middleware(CorrelationIdMiddleware)
