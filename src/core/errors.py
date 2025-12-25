# -*- coding: utf-8 -*-
# file: src/core/errors.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    """
    Единый формат ошибки DevFactory (fail-fast).

    Требования:
      - code: машинный код ошибки
      - message: человеко-читаемое сообщение
      - remediation: что делать дальше
      - missing_inputs: список недостающих входов/фактов
      - evidence: факты, на которых основано решение (без секретов)
      - correlation_id: для трассировки
    """

    code: str = Field(..., description="Machine-readable error code (e.g., DB_MISSING_OBJECT)")
    message: str = Field(..., description="Human-readable error message")
    remediation: Optional[str] = Field(None, description="Next step / how to fix")
    missing_inputs: List[str] = Field(default_factory=list, description="What data/facts are missing")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Facts/evidence for decision")
    correlation_id: Optional[str] = Field(None, description="Correlation id for logs")

    def to_dict(self) -> Dict[str, Any]:
        if hasattr(self, "model_dump"):  # pydantic v2
            return self.model_dump()  # type: ignore[attr-defined]
        return self.dict()  # pydantic v1


def make_error(
    *,
    code: str,
    message: str,
    remediation: Optional[str] = None,
    missing_inputs: Optional[List[str]] = None,
    evidence: Optional[Dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
) -> ErrorEnvelope:
    return ErrorEnvelope(
        code=str(code),
        message=str(message),
        remediation=(str(remediation) if remediation else None),
        missing_inputs=list(missing_inputs or []),
        evidence=dict(evidence or {}),
        correlation_id=(str(correlation_id) if correlation_id else None),
    )
