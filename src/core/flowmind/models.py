from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FlowMindPlan(BaseModel):
    plan_id: UUID
    created_at: datetime
    updated_at: datetime
    status: str
    domain: str
    goal: str
    context: Dict[str, Any] = Field(default_factory=dict)
    plan_json: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class FlowMindAdvice(BaseModel):
    advice_id: UUID
    created_at: datetime
    plan_id: Optional[UUID] = None
    target_type: str
    target_ref: str
    severity: str
    status: str
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class FlowMindSnapshot(BaseModel):
    snapshot_id: UUID
    created_at: datetime
    source: str
    summary: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class DevFactorySuggestion(BaseModel):
    """То, что FlowMind предлагает создать в DevFactory."""

    project_ref: str
    stack: str  # sql-postgres | python_backend | frontend | docs | ...
    title: str
    goal: str
    deliverables: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
