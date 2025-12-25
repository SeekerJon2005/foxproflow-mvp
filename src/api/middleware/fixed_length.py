# src/api/middleware/fixed_length.py
from __future__ import annotations

import typing as t
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, StreamingResponse

# Принудительно переводит ответ в fixed-length:
# - снимает Transfer-Encoding
# - проставляет Content-Length
# - закрывает соединение (Connection: close)
# Включается по фиче-флагу из main.py (FF_DIAG_FIXED_LENGTH=1).

class ForceFixedLengthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)

        # Уже обычный Response с content_length — просто добиваем заголовки
        if not isinstance(resp, StreamingResponse) or isinstance(resp, Response):
            # Если контент-ленгт не задан — материализуем .body
            body = await resp.body() if hasattr(resp, "body") else b""
            headers = dict(resp.headers)
            headers.pop("transfer-encoding", None)
            headers["Content-Length"] = str(len(body))
            headers.setdefault("Connection", "close")
            # Воссоздаём ответ (избавляемся от потенциальной chunked-семантики)
            return Response(
                content=body,
                status_code=resp.status_code,
                headers=headers,
                media_type=getattr(resp, "media_type", None),
                background=getattr(resp, "background", None),
            )

        # Случай StreamingResponse: считываем поток и формируем обычный Response
        body_chunks: t.List[bytes] = []
        async for chunk in resp.body_iterator:
            if isinstance(chunk, str):
                chunk = chunk.encode(resp.charset or "utf-8")
            body_chunks.append(chunk)
        body = b"".join(body_chunks)

        headers = dict(resp.headers)
        headers.pop("transfer-encoding", None)
        headers["Content-Length"] = str(len(body))
        headers.setdefault("Connection", "close")

        return Response(
            content=body,
            status_code=resp.status_code,
            headers=headers,
            media_type=getattr(resp, "media_type", None),
            background=getattr(resp, "background", None),
        )
