from __future__ import annotations

import contextvars
import re
import sys
import uuid
from typing import Optional

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# -----------------------------------------------------------------------------
# Module aliasing (важно для FoxProFlow):
# иногда код импортирует этот файл как `api.middleware.correlation_id`,
# а иногда как `src.api.middleware.correlation_id`.
# Если оставить как есть, Python может загрузить модуль ДВАЖДЫ (две копии),
# и contextvar будет разный. Чтобы этого не было — ставим alias в sys.modules.
# -----------------------------------------------------------------------------
if __name__.startswith("api."):
    sys.modules.setdefault("src.api.middleware.correlation_id", sys.modules[__name__])
elif __name__.startswith("src.api."):
    sys.modules.setdefault("api.middleware.correlation_id", sys.modules[__name__])

# -----------------------------------------------------------------------------
# Correlation ID storage (contextvar)
# -----------------------------------------------------------------------------
_correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id",
    default=None,
)

# Разрешаем только “вменяемые” символы, чтобы не подцепить мусор/инъекции в логи/заголовки.
_SAFE_CID_RE = re.compile(r"^[A-Za-z0-9._\-:@]+$")

DEFAULT_HEADER = "X-Correlation-Id"
LEGACY_HEADER = "X-FF-Correlation-Id"


def get_correlation_id() -> Optional[str]:
    """
    Correlation ID из contextvars (если установлен).
    Основной источник истины для HTTP — request.state.correlation_id (middleware кладёт туда всегда).
    """
    return _correlation_id_var.get()


def _new_cid() -> str:
    return str(uuid.uuid4())


def _normalize_cid(value: Optional[str], *, max_len: int) -> str:
    """
    Нормализация входящего correlation id:
      - trim
      - ограничение длины
      - safe charset
      - отбрасываем "none/null/undefined"
      - если плохо — генерим uuid4
    """
    if not value:
        return _new_cid()

    v = str(value).strip()
    if not v:
        return _new_cid()

    low = v.lower()
    if low in ("none", "null", "undefined"):
        return _new_cid()

    if len(v) > max_len:
        v = v[:max_len]

    if not _SAFE_CID_RE.match(v):
        return _new_cid()

    return v


def _find_header_value(scope: Scope, name: bytes) -> Optional[str]:
    """
    Ищет заголовок в scope['headers'] (list[tuple[bytes, bytes]]).
    Заголовки там уже в lower-case.
    """
    headers = scope.get("headers") or []
    for k, v in headers:
        if k == name:
            try:
                return v.decode("latin-1").strip()
            except Exception:
                return None
    return None


class CorrelationIdMiddleware:
    """
    ASGI middleware (без BaseHTTPMiddleware — надёжнее для streaming/exception flow).

    Поведение:
      - читает inbound correlation id из:
          X-Correlation-Id, затем X-FF-Correlation-Id, затем X-Request-Id/X-Trace-Id/X-Amzn-Trace-Id
      - если нет/плохой — генерит uuid4
      - сохраняет:
          scope['state']['correlation_id'] и contextvar
      - добавляет заголовок X-Correlation-Id в ответ (и опционально X-FF-Correlation-Id для совместимости)
    """

    def __init__(
        self,
        app: ASGIApp,
        header_name: str = DEFAULT_HEADER,
        legacy_header_name: Optional[str] = LEGACY_HEADER,
        max_len: int = 128,
    ) -> None:
        self.app = app
        self.header_name = header_name
        self.legacy_header_name = legacy_header_name
        self.max_len = max(16, int(max_len))

        self._header_name_bytes = header_name.lower().encode("latin-1")
        self._legacy_header_bytes = (
            legacy_header_name.lower().encode("latin-1") if legacy_header_name else None
        )

        # порядок важен: сначала канонический, затем legacy, затем “общие” заголовки
        self._accept_headers = [
            self._header_name_bytes,
        ]
        if self._legacy_header_bytes:
            self._accept_headers.append(self._legacy_header_bytes)

        self._accept_headers.extend(
            [
                b"x-request-id",
                b"x-trace-id",
                b"x-amzn-trace-id",
            ]
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        presented: Optional[str] = None
        for h in self._accept_headers:
            presented = _find_header_value(scope, h)
            if presented:
                break

        cid = _normalize_cid(presented, max_len=self.max_len)

        # (1) request.state.correlation_id доступен как Request.state.correlation_id
        state = scope.setdefault("state", {})
        state["correlation_id"] = cid

        # (2) contextvar для внутренних слоёв
        token = _correlation_id_var.set(cid)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])

                # Удаляем дубли (если кто-то уже выставил заголовок)
                def _filter_out(name_b: Optional[bytes]) -> None:
                    nonlocal headers
                    if not name_b:
                        return
                    headers = [(k, v) for (k, v) in headers if k != name_b]

                _filter_out(self._header_name_bytes)
                _filter_out(self._legacy_header_bytes)

                headers.append((self._header_name_bytes, cid.encode("latin-1")))
                if self._legacy_header_bytes:
                    headers.append((self._legacy_header_bytes, cid.encode("latin-1")))

                message["headers"] = headers

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _correlation_id_var.reset(token)
