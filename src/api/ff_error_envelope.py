from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from fastapi.responses import JSONResponse
from starlette.requests import Request

ErrorKind = Literal["validation", "dependency", "runtime", "policy"]


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def kind_from_status(status_code: int) -> ErrorKind:
    # policy / access-control / throttling
    if status_code in (401, 403, 429):
        return "policy"
    # client-side request issues (incl. not found in вашем контракте)
    if status_code in (400, 404, 405, 409, 410, 422):
        return "validation"
    # downstream dependencies (db/redis/osrm/etc.)
    if status_code in (408, 424, 502, 503, 504):
        return "dependency"
    # server-side crash
    if 500 <= status_code <= 599:
        return "runtime"
    # safe default
    return "runtime"


def default_code(status_code: int) -> str:
    # validation
    if status_code == 422:
        return "validation.request"
    if status_code == 404:
        return "validation.not_found"
    if status_code in (400, 405, 409, 410):
        return f"validation.http_{status_code}"

    # policy
    if status_code == 403:
        return "policy.forbidden"
    if status_code == 401:
        return "policy.unauthorized"
    if status_code == 429:
        return "policy.rate_limited"

    # dependency
    if status_code in (502, 503, 504, 424, 408):
        return "dependency.unavailable"

    # runtime
    if 500 <= status_code <= 599:
        return "runtime.unhandled"

    return f"http.{status_code}"


def get_correlation_id(request: Request) -> str:
    """
    Возвращает correlation_id для ответа.
    Предпочтение:
      1) request.state.correlation_id (если middleware выставил)
      2) inbound headers (X-Correlation-Id / X-Request-Id / X-Trace-Id)
      3) contextvar из middleware (best-effort)
      4) fallback uuid4 (чтобы correlation_id никогда не был null)
    """
    cid = getattr(request.state, "correlation_id", None)
    if cid:
        return str(cid)

    cid = (
        request.headers.get("X-Correlation-Id")
        or request.headers.get("X-Request-Id")
        or request.headers.get("X-Trace-Id")
    )
    if cid:
        return str(cid).strip() or str(uuid.uuid4())

    # best-effort: если request.state ещё не выставлен, но контекст уже есть
    try:
        from src.api.middleware.correlation_id import get_correlation_id as _ctx_get  # type: ignore
        ctx = _ctx_get()
        if ctx:
            return str(ctx)
    except Exception:
        pass

    return str(uuid.uuid4())


def _normalize_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Гарантируем, что details — dict, и не разваливаем JSON serialization.
    """
    if details is None:
        return {}
    if isinstance(details, dict):
        return details
    return {"value": str(details)}


def _request_meta(request: Request) -> Dict[str, Any]:
    """
    Минимальная, безопасная мета-информация (без querystring и без заголовков).
    """
    try:
        path = request.url.path
    except Exception:
        path = "unknown"
    return {
        "method": getattr(request, "method", "UNKNOWN"),
        "path": path,
    }


def build_error_payload(
    *,
    request: Request,
    status_code: int,
    message: str,
    kind: Optional[ErrorKind] = None,
    code: Optional[str] = None,
    detail: Optional[str] = None,
    errors: Optional[list[dict[str, Any]]] = None,
    details: Optional[Dict[str, Any]] = None,
    include_request_meta: bool = True,
) -> Dict[str, Any]:
    """
    Единый error envelope v1 (аддитивно к текущим полям API):
      - сохраняем backward-compatible поля: detail, errors, status_code
      - добавляем коммерчески полезные: ok, error.kind, correlation_id, ts
    """
    k = kind or kind_from_status(status_code)
    c = code or default_code(status_code)
    cid = get_correlation_id(request)

    payload: Dict[str, Any] = {
        "ok": False,
        "status_code": int(status_code),
        # backward compatible keys (у вас уже есть)
        "detail": detail or message,
        "ts": _now_iso_utc(),
        "correlation_id": cid,
        "error": {
            "kind": k,
            "code": c,
            "message": message,
            "details": _normalize_details(details),
        },
    }

    if include_request_meta:
        payload["request"] = _request_meta(request)

    if errors is not None:
        # errors — отдельным ключом (как у вас сейчас), плюс продублируем в error.details
        payload["errors"] = errors
        merged = dict(payload["error"]["details"])
        merged["errors"] = errors
        payload["error"]["details"] = merged

    return payload


def json_error(
    *,
    request: Request,
    status_code: int,
    message: str,
    kind: Optional[ErrorKind] = None,
    code: Optional[str] = None,
    detail: Optional[str] = None,
    errors: Optional[list[dict[str, Any]]] = None,
    details: Optional[Dict[str, Any]] = None,
    include_request_meta: bool = True,
) -> JSONResponse:
    payload = build_error_payload(
        request=request,
        status_code=status_code,
        message=message,
        kind=kind,
        code=code,
        detail=detail,
        errors=errors,
        details=details,
        include_request_meta=include_request_meta,
    )
    return JSONResponse(status_code=int(status_code), content=payload)
