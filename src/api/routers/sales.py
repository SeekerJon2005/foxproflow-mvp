# -*- coding: utf-8 -*-
# file: src/api/routers/sales.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, validator

from src.worker.tasks_salesfox import (
    salesfox_start_session,
    salesfox_handle_message,
    salesfox_generate_proposal,
)

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sales",
    tags=["sales"],
)

# Допустимые каналы общения (должны совпадать с CHECK в crm.sales_sessions.channel)
ALLOWED_CHANNELS = {"web_chat", "email", "partner_portal", "manual"}
DEFAULT_CHANNEL = "web_chat"


# === Pydantic-модели ================================================


class SalesStartRequest(BaseModel):
    source: str = Field("web", description="Источник лида: web/partner/manual/...")
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = "RU"
    region: Optional[str] = None
    fleet_size: Optional[int] = Field(
        default=None, description="Оценка размера парка (для предложения)."
    )
    channel: Optional[str] = Field(
        default=DEFAULT_CHANNEL,
        description=(
            "Канал коммуникации: web_chat/email/partner_portal/manual. "
            "Если передан неизвестный канал — будет использован web_chat."
        ),
    )

    class Config:
        json_schema_extra = {
            "example": {
                "source": "web",
                "company_name": "ООО Рога и Тягачи",
                "contact_name": "Иван Петров",
                "email": "ivan@example.com",
                "phone": "+79991234567",
                "country": "RU",
                "region": "RU-MOW",
                "fleet_size": 15,
                "channel": "web_chat",
            }
        }

    @validator("channel", pre=True, always=True)
    def normalize_channel(cls, v: Optional[str]) -> str:
        """
        Нормализация канала: приводим к whitelisted списку,
        чтобы не нарушать CHECK(channel IN (...)) в БД.
        """
        if not v:
            return DEFAULT_CHANNEL
        v = str(v).strip()
        return v if v in ALLOWED_CHANNELS else DEFAULT_CHANNEL


class SalesStartResponse(BaseModel):
    ok: bool = True
    lead_id: int
    session_id: int


class SalesMessageRequest(BaseModel):
    session_id: int
    message: str = Field(..., description="Сообщение от лида/клиента.")


class SalesMessageResponse(BaseModel):
    ok: bool = True
    session_id: int
    reply: str


class SalesProposalResponse(BaseModel):
    ok: bool = True
    session_id: int
    proposal: Dict[str, Any]


# === Endpoints ======================================================


@router.post("/start", response_model=SalesStartResponse)
def api_sales_start(req: SalesStartRequest) -> SalesStartResponse:
    """
    Старт сессии SalesFox: создаёт crm.leads + crm.sales_sessions.
    """
    try:
        # req.dict() уже содержит нормализованный channel
        res = salesfox_start_session(req.dict())
    except Exception as exc:
        log.exception("api_sales_start failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"salesfox.start_session failed: {exc!r}",
        )
    return SalesStartResponse(
        ok=bool(res.get("ok", True)),
        lead_id=int(res["lead_id"]),
        session_id=int(res["session_id"]),
    )


@router.post("/message", response_model=SalesMessageResponse)
def api_sales_message(req: SalesMessageRequest) -> SalesMessageResponse:
    """
    Сообщение в существующую сессию SalesFox (v0: отвечает заглушкой).
    """
    try:
        res = salesfox_handle_message(req.session_id, req.message)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        log.exception("api_sales_message failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"salesfox.handle_message failed: {exc!r}",
        )

    return SalesMessageResponse(
        ok=bool(res.get("ok", True)),
        session_id=int(res["session_id"]),
        reply=str(res.get("reply", "")),
    )


@router.get("/proposal/{session_id}", response_model=SalesProposalResponse)
def api_sales_proposal(session_id: int) -> SalesProposalResponse:
    """
    Получить сгенерированное коммерческое предложение по сессии.
    """
    try:
        res = salesfox_generate_proposal(session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        log.exception("api_sales_proposal failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"salesfox.generate_proposal failed: {exc!r}",
        )

    return SalesProposalResponse(
        ok=bool(res.get("ok", True)),
        session_id=int(res["session_id"]),
        proposal=dict(res.get("proposal") or {}),
    )
