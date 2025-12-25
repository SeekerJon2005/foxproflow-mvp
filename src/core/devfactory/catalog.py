# -*- coding: utf-8 -*-
# file: src/core/devfactory/catalog.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CatalogItem(BaseModel):
    order_type: str
    title: str
    description: str
    required_inputs: List[str] = Field(default_factory=list)
    estimate: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        if hasattr(self, "model_dump"):  # pydantic v2
            return self.model_dump()  # type: ignore[attr-defined]
        return self.dict()  # pydantic v1


def list_catalog() -> List[CatalogItem]:
    """
    Минимальный коммерческий каталог (2–3 товара DevFactory как процедуры).
    Оценки — константы каталога (это не “угадывание”, это прайс/пакет).
    """
    return [
        CatalogItem(
            order_type="stand_diagnostics_v1",
            title="Диагностика стенда (Context Pack + DB facts)",
            description="Снимает Context Pack (git/env/runtime), проверяет DB connectivity, формирует отчёт JSON+текст.",
            required_inputs=[],
            estimate={"sla_minutes": 15, "price_rub": 5000},
        ),
        CatalogItem(
            order_type="verify_db_contract_v1",
            title="Верификация БД-контракта DevFactory",
            description="Проверяет наличие ключевых таблиц/колонок DevFactory (dev.dev_task/dev.dev_order/ops.agent_events).",
            required_inputs=[],
            estimate={"sla_minutes": 20, "price_rub": 7000},
        ),
        CatalogItem(
            order_type="incident_triage_v1",
            title="Инцидент-триаж по runbook (fail-fast)",
            description="Формализованный отказ/диагноз + список конкретных команд для добора фактов. Без магии.",
            required_inputs=[],
            estimate={"sla_minutes": 20, "price_rub": 9000},
        ),
    ]


def get_catalog_item(order_type: str) -> Optional[CatalogItem]:
    ot = (order_type or "").strip()
    for it in list_catalog():
        if it.order_type == ot:
            return it
    return None
