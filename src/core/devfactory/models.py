from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

DevTaskStatus = str
DevTaskId = int


@dataclass
class DevTask:
    """
    Внутренняя модель задачи DevFactory.

    id        — внутренний числовой идентификатор (bigint dev.dev_task.id);
    public_id — устойчивый UUID-идентификатор (dev.dev_task.public_id),
                который мы постепенно будем использовать наружу.
    """

    id: DevTaskId
    public_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    status: DevTaskStatus
    source: str
    stack: str
    title: Optional[str]
    input_spec: Dict[str, Any]
    result_spec: Dict[str, Any]
    error: Optional[str]
    links: Dict[str, Any]

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "DevTask":
        """
        Собирает DevTask из dict (результат _row_to_dict).
        Ожидается, что row уже приведён к python-типам через psycopg.
        """
        return cls(
            id=row["id"],
            public_id=row.get("public_id"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            status=row["status"],
            source=row["source"],
            stack=row["stack"],
            title=row.get("title"),
            input_spec=row.get("input_spec") or {},
            result_spec=row.get("result_spec") or {},
            error=row.get("error"),
            links=row.get("links") or {},
        )

    @property
    def is_open(self) -> bool:
        return self.status in ("new", "in_progress")

    @property
    def is_finished(self) -> bool:
        return self.status in ("done", "failed", "cancelled")
