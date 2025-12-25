from __future__ import annotations

"""
DevFactory Question Engine models (v0.1)

Файл:
    src/core/devfactory/question_models.py

Назначение:
    Pydantic-модели для описания вопросов, пакетов вопросов и результата работы
    Question Engine. Не содержат бизнес-логики, только типы данных.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .intent_models import IntentTaskKind, IntentScope


JsonDict = Dict[str, Any]


class QuestionAnswerType(str, Enum):
    """Тип ожидаемого ответа на вопрос."""

    TEXT = "text"
    CHOICE = "choice"
    NUMBER = "number"
    BOOLEAN = "boolean"


class QuestionSpec(BaseModel):
    """
    Описание одного вопроса, который Question Engine может задать оператору/клиенту.

    id:
        стабильный идентификатор вопроса (используется для маппинга ответов, логов и т.п.)
    text:
        текст вопроса (на естественном языке)
    target:
        строковый путь к аспекту задачи/intent, к которому относится вопрос
        (например: "api.response.pagination" или "migration.data.backfill_strategy")
    required:
        обязательный ли вопрос (без ответа задачу считать неполной)
    answer_type:
        тип ожидаемого ответа (text/choice/number/boolean)
    choices:
        список вариантов ответа (для answer_type=choice)
    help:
        краткое пояснение, помогающее оператору/клиенту ответить
    """

    id: str = Field(..., description="Стабильный идентификатор вопроса.")
    text: str = Field(..., description="Текст вопроса.")
    target: str = Field(
        ...,
        description="Путь к аспекту intent/задачи, к которому относится вопрос.",
    )
    required: bool = Field(
        default=True, description="Обязателен ли ответ на этот вопрос."
    )
    answer_type: QuestionAnswerType = Field(
        default=QuestionAnswerType.TEXT,
        description="Тип ожидаемого ответа.",
    )
    choices: List[str] = Field(
        default_factory=list,
        description="Доступные варианты ответа (для choice).",
    )
    help: Optional[str] = Field(
        default=None,
        description="Дополнительное пояснение к вопросу.",
    )

    class Config:
        extra = "ignore"


class QuestionPackSelector(BaseModel):
    """
    Условия, при которых пакет вопросов применяется к задаче.

    task_kinds:
        список подходящих типов задач (feature/bugfix/migration/...).
        Если пусто — подходит к любому типу.
    domains:
        список доменов (primary-домен intent.domain.primary).
        Если пусто — подходит к любому домену.
    stack_contains:
        список ключевых элементов стека, которые должны присутствовать
        хотя бы в одном из списков intent.stack (languages/frameworks/datastores/infra).
        Если пусто — ограничение по стеку не накладывается.
    min_scope, max_scope:
        границы размера задачи (S/M/L). Если не заданы — ограничение отсутствует.
    """

    task_kinds: List[IntentTaskKind] = Field(
        default_factory=list,
        description="Каким классам задач подходит пакет.",
    )
    domains: List[str] = Field(
        default_factory=list,
        description="Каким доменам (primary) подходит пакет.",
    )
    stack_contains: List[str] = Field(
        default_factory=list,
        description="Какие элементы стека должны присутствовать.",
    )
    min_scope: Optional[IntentScope] = Field(
        default=None,
        description="Минимальный размер задачи.",
    )
    max_scope: Optional[IntentScope] = Field(
        default=None,
        description="Максимальный размер задачи.",
    )

    class Config:
        extra = "ignore"


class QuestionPack(BaseModel):
    """
    Пакет вопросов, применяемый при выполнении условия selector.

    id:
        идентификатор пакета (для логов/диагностики)
    selector:
        условия применения пакета
    questions:
        список вопросов этого пакета
    """

    id: str = Field(..., description="Идентификатор пакета вопросов.")
    selector: QuestionPackSelector = Field(
        ..., description="Условия применения пакета."
    )
    questions: List[QuestionSpec] = Field(
        default_factory=list,
        description="Вопросы, входящие в пакет.",
    )

    class Config:
        extra = "ignore"


class QuestionEngineResult(BaseModel):
    """
    Результат работы Question Engine.

    version:
        версия схемы результата (для миграций в будущем)
    questions:
        финальный список вопросов (0–N)
    meta:
        служебная информация (пояснения, отладка, использованные пакеты и т.п.)
    """

    version: str = Field(
        default="0.1",
        description="Версия схемы результата Question Engine.",
    )
    questions: List[QuestionSpec] = Field(
        default_factory=list,
        description="Список сгенерированных вопросов.",
    )
    meta: JsonDict = Field(
        default_factory=dict,
        description="Служебная информация (пояснения, отладка).",
    )

    class Config:
        extra = "ignore"

    def to_storage_dict(self) -> JsonDict:
        """
        Представление для сохранения в JSONB (dev.dev_task.input_spec['questions']).

        Отдельный метод полезен для будущих миграций/фильтрации.
        """
        return self.dict()
