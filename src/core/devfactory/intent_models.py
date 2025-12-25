"""
DevFactory Intent Parser models (v0.1)

Файл:
    src/core/devfactory/intent_models.py

Назначение:
    Базовые Pydantic-модели для представления:
      - контекста намерения (IntentContext),
      - структуры намерения задачи (IntentSpecV0_1),
      - вспомогательных структур (summary/domain/stack/artifacts/constraints/risk).

Важно:
    - Модуль не имеет побочных эффектов (нет доступа к БД, файлам, сети).
    - Используется как внутренняя модель для DevFactory и Intent Parser.
    - Хранится в JSONB-поле dev.dev_task.input_spec["intent"].
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


JsonDict = Dict[str, Any]


class IntentSource(str, Enum):
    """Источник текста задачи."""

    OPERATOR_CLI = "operator_cli"
    CRM_IMPORT = "crm_import"
    DEVORDER = "devorder"
    ARCHITECT_SESSION = "architect_session"
    OTHER = "other"


class IntentLanguage(str, Enum):
    """Язык исходного текста."""

    RU = "ru"
    EN = "en"
    OTHER = "other"


class IntentChannel(str, Enum):
    """Канал, через который пришёл текст."""

    TEXT = "text"
    VOICE_TRANSCRIPT = "voice_transcript"
    OTHER = "other"


class IntentTaskKind(str, Enum):
    """Класс задачи для DevFactory (v0.1)."""

    FEATURE = "feature"          # Новая функциональность
    BUGFIX = "bugfix"            # Исправление ошибки
    REFACTOR = "refactor"        # Рефакторинг без смены поведения
    MIGRATION = "migration"      # Изменение схемы БД/структуры данных
    OPTIMIZATION = "optimization"  # Оптимизация производительности/ресурсов
    RESEARCH = "research"        # Исследование, прототип, анализ
    DOC = "doc"                  # Документация, схемы, описания
    INFRA = "infra"              # Инфраструктура, CI, деплой, мониторинг


class IntentScope(str, Enum):
    """Прикидочный размер задачи."""

    SMALL = "S"
    MEDIUM = "M"
    LARGE = "L"


class EnvTarget(str, Enum):
    """Целевое окружение для выката результата."""

    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class RiskLevel(str, Enum):
    """Уровень риска изменения."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IntentHints(BaseModel):
    """
    Мягкие подсказки для парсера:
      - stack: предполагаемые технологии
      - area: предполагаемые домены/подсистемы организма
    """

    stack: List[str] = Field(default_factory=list)
    area: List[str] = Field(default_factory=list)

    class Config:
        extra = "ignore"


class IntentContext(BaseModel):
    """
    Контекст, передаваемый вместе с сырым текстом задачи.

    Пример:
        {
          "project_ref": "foxproflow-core",
          "source": "operator_cli",
          "language": "ru",
          "channel": "text",
          "hints": {
            "stack": ["python", "fastapi", "postgres"],
            "area": ["devfactory", "logistics", "crm"]
          }
        }
    """

    project_ref: str = Field(..., description="Идентификатор проекта (как в dev.dev_task)")
    source: IntentSource = Field(IntentSource.OPERATOR_CLI, description="Источник текста")
    language: IntentLanguage = Field(IntentLanguage.RU, description="Язык исходного текста")
    channel: IntentChannel = Field(IntentChannel.TEXT, description="Канал получения текста")
    hints: IntentHints = Field(default_factory=IntentHints, description="Подсказки парсеру")

    class Config:
        extra = "ignore"


class IntentSummary(BaseModel):
    """Краткое резюме намерения."""

    short_title: str = Field(..., description="Краткий заголовок задачи")
    goal: str = Field(..., description="Формулировка цели задачи в одной-двух фразах")


class IntentDomainInfo(BaseModel):
    """
    Информация о домене задачи (по FlowMeta).

    primary:
        основной домен (logistics, devfactory, crm, sec, flowmeta, eri, observability, billing, hardware, robotics, ...)
    secondary:
        дополнительные домены, которых задача тоже касается
    flowmeta_refs:
        ссылки на сущности FlowMeta (например: logistics.trip, devfactory.dev_task)
    """

    primary: Optional[str] = Field(
        default=None,
        description="Основной домен (например, 'logistics', 'devfactory', 'crm').",
    )
    secondary: List[str] = Field(
        default_factory=list,
        description="Вторичные домены задачи.",
    )
    flowmeta_refs: List[str] = Field(
        default_factory=list,
        description="Коды сущностей FlowMeta, вовлечённых в задачу.",
    )


class IntentStackInfo(BaseModel):
    """
    Технологический стек задачи.

    languages:
        основные языки разработки (python, sql, typescript, ...)
    frameworks:
        фреймворки и библиотеки (fastapi, celery, react, ...)
    datastores:
        хранилища данных (postgres, redis, s3, ...)
    infra:
        инфраструктура и окружение (docker, k8s, nginx, ...)
    """

    languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    datastores: List[str] = Field(default_factory=list)
    infra: List[str] = Field(default_factory=list)

    @validator("languages", "frameworks", "datastores", "infra", pre=True, always=True)
    def _deduplicate(cls, v: Any) -> List[str]:
        """Убираем дубликаты, приводим к списку строк."""
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        result: List[str] = []
        for item in v:
            if not isinstance(item, str):
                continue
            item_norm = item.strip()
            if item_norm and item_norm not in result:
                result.append(item_norm)
        return result


class IntentArtifactsExpected(BaseModel):
    """
    Ожидаемые артефакты по итогам задачи.

    code:
        пути к файлам кода (python/ts/etc)
    sql_patches:
        пути к SQL-патчам
    docs:
        пути к документации (md, rst, diagram source)
    scripts:
        пути к вспомогательным скриптам (pwsh, bash, python-cli)
    """

    code: List[str] = Field(default_factory=list)
    sql_patches: List[str] = Field(default_factory=list)
    docs: List[str] = Field(default_factory=list)
    scripts: List[str] = Field(default_factory=list)

    @validator("code", "sql_patches", "docs", "scripts", pre=True, always=True)
    def _normalize_paths(cls, v: Any) -> List[str]:
        """Простая нормализация списков путей (обрезка пробелов, без дубликатов)."""
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        result: List[str] = []
        for item in v:
            if not isinstance(item, str):
                continue
            path = item.strip()
            if path and path not in result:
                result.append(path)
        return result


class IntentConstraints(BaseModel):
    """
    Ограничения задачи.

    deadline_hours:
        ориентировочный дедлайн в часах (может быть None, если не задан)
    scope:
        примерный размер задачи (S/M/L)
    non_destructive_only:
        обязателен ли non-destructive подход (NDC)
    needs_review_by_architect:
        требует ли обязательного ревью Архитектором
    env_target:
        целевое окружение (dev/staging/prod)
    """

    deadline_hours: Optional[int] = Field(
        default=None, description="Прикидочный дедлайн в часах."
    )
    scope: Optional[IntentScope] = Field(
        default=None, description="Размер задачи (S/M/L)."
    )
    non_destructive_only: bool = Field(
        default=True,
        description="Разрешены только non-destructive изменения (канон FoxProFlow).",
    )
    needs_review_by_architect: bool = Field(
        default=False,
        description="Требует обязательного ревью Архитектора.",
    )
    env_target: EnvTarget = Field(
        default=EnvTarget.DEV,
        description="Целевое окружение для выката.",
    )


class IntentRisk(BaseModel):
    """
    Оценка риска.

    level:
        уровень риска
    tags:
        дополнительные метки (touches_security, changes_db_schema, touches_flowsec, ...)
    notes:
        произвольные заметки
    """

    level: RiskLevel = Field(default=RiskLevel.MEDIUM)
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None)

    @validator("tags", pre=True, always=True)
    def _normalize_tags(cls, v: Any) -> List[str]:
        """Нормализуем список тэгов (строки, без дубликатов)."""
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        result: List[str] = []
        for item in v:
            if not isinstance(item, str):
                continue
            tag = item.strip()
            if tag and tag not in result:
                result.append(tag)
        return result


class IntentSpecV0_1(BaseModel):
    """
    Основная модель намерения задачи для DevFactory (версия 0.1).

    Структура должна быть совместима с JSON, который
    хранится в dev.dev_task.input_spec["intent"].
    """

    version: str = Field(
        default="0.1",
        description="Версия схемы IntentSpec (для дальнейших миграций).",
    )

    summary: IntentSummary = Field(
        ..., description="Краткое описание задачи и цели."
    )
    task_kind: IntentTaskKind = Field(
        ..., description="Класс задачи (feature, bugfix, migration, ...)."
    )

    domain: IntentDomainInfo = Field(
        default_factory=IntentDomainInfo,
        description="Информация о доменах и сущностях FlowMeta.",
    )
    stack: IntentStackInfo = Field(
        default_factory=IntentStackInfo,
        description="Технологический стек задачи.",
    )

    artifacts_expected: IntentArtifactsExpected = Field(
        default_factory=IntentArtifactsExpected,
        description="Предполагаемые артефакты по итогам задачи.",
    )

    constraints: IntentConstraints = Field(
        default_factory=IntentConstraints,
        description="Ограничения задачи (сроки, NDC, окружение).",
    )
    risk: IntentRisk = Field(
        default_factory=IntentRisk,
        description="Оценка риска и дополнительные теги.",
    )

    meta: JsonDict = Field(
        default_factory=dict,
        description="Свободное поле для будущих расширений (v0.1).",
    )

    class Config:
        extra = "ignore"

    def to_storage_dict(self) -> JsonDict:
        """
        Представление для сохранения в JSONB (dev.dev_task.input_spec["intent"]).

        По умолчанию Pydantic .dict() и так даёт подходящий результат,
        но отдельный метод полезен для потенциальных миграций/фильтраций.
        """
        return self.dict()



