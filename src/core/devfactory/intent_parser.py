"""
DevFactory Intent Parser (v0.1)

Файл:
    src/core/devfactory/intent_parser.py

Назначение:
    Реализация функции:
        parse_intent(raw_text: str, ctx: IntentContext) -> IntentSpecV0_1

    Функция:
      - принимает сырой текст задачи + IntentContext,
      - извлекает базовую структуру намерения (task_kind, domain, stack, артефакты, ограничения, риск),
      - возвращает заполненный IntentSpecV0_1.

Ограничения v0.1:
    - Никакого доступа к БД, файлам, сети.
    - Никакого обращения к FlowMeta API.
    - Всё на простых правилах и словарях ключевых слов (ru/en).
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .intent_models import (
    EnvTarget,
    IntentChannel,
    IntentContext,
    IntentDomainInfo,
    IntentLanguage,
    IntentRisk,
    IntentScope,
    IntentSpecV0_1,
    IntentStackInfo,
    IntentSummary,
    IntentTaskKind,
    IntentArtifactsExpected,
    IntentConstraints,
    RiskLevel,
)


# -------------------------------
# Вспомогательные словари и константы
# -------------------------------

# Приоритет классов задач при конфликте
_TASK_KIND_PRIORITY: List[IntentTaskKind] = [
    IntentTaskKind.BUGFIX,
    IntentTaskKind.MIGRATION,
    IntentTaskKind.FEATURE,
    IntentTaskKind.OPTIMIZATION,
    IntentTaskKind.REFACTOR,
    IntentTaskKind.INFRA,
    IntentTaskKind.DOC,
    IntentTaskKind.RESEARCH,
]

# Ключевые слова по классам задач (ru/en)
_TASK_KIND_KEYWORDS: Dict[IntentTaskKind, List[str]] = {
    IntentTaskKind.BUGFIX: [
        "исправить",
        "починить",
        "не работает",
        "не работает.",
        "не работает,",
        "падает",
        "ошибка",
        "баг",
        "bug",
        "error",
        "exception",
        "traceback",
        "fail",
        "failing",
    ],
    IntentTaskKind.MIGRATION: [
        "миграция",
        "migration",
        "schema change",
        "изменить схему",
        "alter table",
        "создать таблицу",
        "добавить колонку",
        "удалить колонку",
    ],
    IntentTaskKind.FEATURE: [
        "добавить",
        "реализовать",
        "сделать",
        "нужно чтобы",
        "new feature",
        "add feature",
        "implement",
        "добавление",
        "поддержать",
    ],
    IntentTaskKind.OPTIMIZATION: [
        "оптимизировать",
        "ускорить",
        "слишком медленно",
        "долго работает",
        "performance",
        "optimize",
        "throughput",
        "latency",
    ],
    IntentTaskKind.REFACTOR: [
        "рефакторинг",
        "переписать",
        "разнести по модулям",
        "убрать дубли",
        "cleanup",
        "refactor",
        "restructure",
    ],
    IntentTaskKind.INFRA: [
        "docker",
        "compose",
        "k8s",
        "kubernetes",
        "ci",
        "cd",
        "deploy",
        "деплой",
        "инфраструктура",
        "инфра",
        "monitoring",
        "grafana",
        "prometheus",
        "логирование",
        "логгирование",
    ],
    IntentTaskKind.DOC: [
        "документация",
        "описать",
        "описание",
        "spec",
        "спецификация",
        "написать doc",
        "write doc",
        "readme",
    ],
    IntentTaskKind.RESEARCH: [
        "исследовать",
        "исследование",
        "прототип",
        "prototype",
        "проверить варианты",
        "поэкспериментировать",
        "experiment",
    ],
}

# Доменные ключевые слова (ru/en)
_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "devfactory": [
        "devfactory",
        "dev factory",
        "dev_task",
        "dev task",
        "devorder",
        "dev order",
        "developer agent",
        "агент-программист",
        "агенты-программисты",
        "оператор devfactory",
        "devorders",
    ],
    "logistics": [
        "логистика",
        "рейс",
        "рейсы",
        "маршрут",
        "груз",
        "заявка",
        "погрузка",
        "выгрузка",
        "ts",
        "тс",
        "автоплан",
        "autoplan",
        "osrm",
    ],
    "crm": [
        "crm",
        "клиент",
        "лид",
        "контакт",
        "сделка",
        "pipeline",
        "воронка",
        "salesfox",
    ],
    "sec": [
        "sec.",
        "security",
        "безопасность",
        "flowsec",
        "policy",
        "политика доступа",
        "роли доступа",
    ],
    "flowmeta": [
        "flowmeta",
        "flow meta",
        "метаязык",
        "онтология",
        "master canon",
        "геном",
    ],
    "eri": [
        "eri",
        "эри",
        "ребёнок",
        "ребенок",
        "эмоции",
        "эмпатия",
        "наставник",
        "семья",
        "familycore",
    ],
    "observability": [
        "observability",
        "metrics",
        "kpi",
        "логирование",
        "traces",
        "monitoring",
        "healthcheck",
        "watchdog",
    ],
    "billing": [
        "billing",
        "счета",
        "счет",
        "оплата",
        "инвойс",
        "invoice",
        "подписка",
        "subscription",
    ],
    "hardware": [
        "железо",
        "hardware",
        "сервер",
        "видеокарта",
        "gpu",
        "cpu",
        "платы",
        "motherboard",
    ],
    "robotics": [
        "робот",
        "роботы",
        "роботами",
        "андроид",
        "гуманоид",
        "optimu",
        "optimus",
        "манипулятор",
    ],
}

# Связка домена Intent → сущности FlowMeta (минимальный набор v1.1)
_DOMAIN_FLOWMETA_REFS: Dict[str, List[str]] = {
    # DevFactory
    "devfactory": [
        "devfactory.task",
        "devfactory.order",
        "devfactory.project",
        "devfactory.task_results_mv",
        "devfactory.kpi_daily",
        "devfactory.intent_parser",
        "devfactory.question_engine",
        "devfactory.operator_ui",
    ],
    # Логистика
    "logistics": [
        "logistics.vehicle",
        "logistics.load",
        "logistics.trip",
        "logistics.trip_segment",
        "logistics.route_mv",
        "logistics.kpi_daily",
    ],
    # FlowWorld
    "flowworld": [
        "flowworld.space",
        "flowworld.object",
        "flowworld.state_api",
        "flowworld.link_trip",
    ],
    # ERI
    "eri": [
        "eri.session",
        "eri.mode",
        "eri.context_layer",
        "eri.api_talk",
        "eri.api_context",
    ],
    # Роботы
    "robots": [
        "robots.instance",
        "robots.role",
        "robots.assignment",
        "robots.api_control",
    ],
}

# Ключевые слова для определения стека
_STACK_LANG_KEYWORDS: Dict[str, List[str]] = {
    "python": ["python", "py", "fastapi", "celery"],
    "sql": ["sql", "select", "insert", "update", "delete", "postgres"],
    "typescript": ["typescript", "ts", "tsx"],
    "javascript": ["javascript", "js", "node"],
}

_STACK_FRAMEWORK_KEYWORDS: Dict[str, List[str]] = {
    "fastapi": ["fastapi"],
    "celery": ["celery"],
    "react": ["react", "reactjs"],
}

_STACK_DATASTORE_KEYWORDS: Dict[str, List[str]] = {
    "postgres": ["postgres", "postgresql"],
    "redis": ["redis"],
}

_STACK_INFRA_KEYWORDS: Dict[str, List[str]] = {
    "docker": ["docker", "compose"],
    "k8s": ["k8s", "kubernetes"],
    "nginx": ["nginx"],
}


# Регекс для более-менее похожих на пути файлов штук
_PATH_PATTERN = re.compile(r"(?P<path>(?:src|scripts|docs)[^ \t\n\r\"]+)")


# -------------------------------
# Основная функция
# -------------------------------


def parse_intent(raw_text: str, ctx: IntentContext) -> IntentSpecV0_1:
    """
    Главная функция Intent Parser v0.1.

    :param raw_text: Сырой текст задачи (любой длины, ru/en).
    :param ctx: IntentContext с project_ref, source, hints и т.д.
    :return: IntentSpecV0_1, готовый к сохранению в dev.dev_task.input_spec["intent"].
    """
    text = (raw_text or "").strip()
    text_norm = text.lower()

    summary = _build_summary(text, ctx)
    task_kind = _detect_task_kind(text_norm)
    domain = _detect_domain(text_norm)
    stack = _detect_stack(text_norm, ctx)
    artifacts = _detect_artifacts(text)
    constraints = _build_constraints(text_norm, task_kind, domain, ctx)
    risk = _build_risk(text_norm, task_kind, domain, constraints)

    meta = {
        "raw_text_length": len(text),
        "ctx_language": ctx.language.value,
        "ctx_source": ctx.source.value,
        "ctx_channel": ctx.channel.value,
    }

    return IntentSpecV0_1(
        summary=summary,
        task_kind=task_kind,
        domain=domain,
        stack=stack,
        artifacts_expected=artifacts,
        constraints=constraints,
        risk=risk,
        meta=meta,
    )


# -------------------------------
# Части алгоритма
# -------------------------------


def _build_summary(text: str, ctx: IntentContext) -> IntentSummary:
    if not text:
        return IntentSummary(
            short_title="Пустое намерение",
            goal="Намерение не было задано (пустой текст задачи).",
        )

    # Берём первую строку/предложение для заголовка
    first_line = text.splitlines()[0].strip()
    if len(first_line) > 120:
        first_line = first_line[:117].rstrip() + "..."

    # Для goal возьмём первые 300 символов всего текста
    goal_text = text
    if len(goal_text) > 300:
        goal_text = goal_text[:297].rstrip() + "..."

    short_title = first_line

    # Небольшая пометка проекта, если явно есть
    if ctx.project_ref and ctx.project_ref not in short_title:
        short_title = f"[{ctx.project_ref}] {short_title}"

    return IntentSummary(
        short_title=short_title,
        goal=goal_text,
    )


def _detect_task_kind(text_norm: str) -> IntentTaskKind:
    """
    Определяем класс задачи по ключевым словам.
    Если ничего не совпало — по умолчанию считаем feature.
    При множественных совпадениях берём класс с максимальным количеством попаданий,
    при равенстве — по приоритету _TASK_KIND_PRIORITY.
    """
    if not text_norm:
        return IntentTaskKind.FEATURE

    scores: Dict[IntentTaskKind, int] = {k: 0 for k in _TASK_KIND_KEYWORDS.keys()}

    for kind, keywords in _TASK_KIND_KEYWORDS.items():
        for kw in keywords:
            if kw in text_norm:
                scores[kind] += 1

    # Если ни один класс не набрал очков — feature
    if all(score == 0 for score in scores.values()):
        return IntentTaskKind.FEATURE

    # Ищем максимум
    best_score = max(scores.values())
    best_candidates = [k for k, s in scores.items() if s == best_score]

    # Если один явный победитель
    if len(best_candidates) == 1:
        return best_candidates[0]

    # При равенстве — по приоритету
    for kind in _TASK_KIND_PRIORITY:
        if kind in best_candidates:
            return kind

    # Fallback (на всякий случай)
    return IntentTaskKind.FEATURE


def _detect_domain(text_norm: str) -> IntentDomainInfo:
    """
    Простое доменное сопоставление по ключевым словам.
    primary — домен с максимальным числом совпадений,
    secondary — домены с заметным весом (>= 0.3 от максимума),
    flowmeta_refs — базовый набор сущностей FlowMeta для primary-домена (v1.1).
    """
    if not text_norm:
        return IntentDomainInfo()

    scores: Dict[str, int] = {domain: 0 for domain in _DOMAIN_KEYWORDS.keys()}

    for domain, keywords in _DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in text_norm:
                scores[domain] += 1

    if all(score == 0 for score in scores.values()):
        # Не удалось привязать ни к одному домену
        return IntentDomainInfo()

    max_score = max(scores.values())
    if max_score <= 0:
        return IntentDomainInfo()

    # primary — домен(ы) с максимальным счётом
    primary_candidates = [d for d, s in scores.items() if s == max_score]
    primary = sorted(primary_candidates)[0]  # детерминированный выбор

    # secondary — домены с достаточным отношением к максимуму
    threshold = max(1, int(max_score * 0.3))
    secondary = [
        d for d, s in scores.items() if d != primary and s >= threshold and s > 0
    ]

    # FlowMeta refs — минимальный набор сущностей для домена (по FlowMeta v1.1)
    flowmeta_refs = _DOMAIN_FLOWMETA_REFS.get(primary, [])

    return IntentDomainInfo(
        primary=primary,
        secondary=sorted(secondary),
        flowmeta_refs=flowmeta_refs,
    )


def _detect_stack(text_norm: str, ctx: IntentContext) -> IntentStackInfo:
    """
    Определение стека по ключевым словам в тексте + hints из IntentContext.
    """
    languages: List[str] = []
    frameworks: List[str] = []
    datastores: List[str] = []
    infra: List[str] = []

    # Из текста
    for lang, kws in _STACK_LANG_KEYWORDS.items():
        if any(kw in text_norm for kw in kws):
            languages.append(lang)

    for fw, kws in _STACK_FRAMEWORK_KEYWORDS.items():
        if any(kw in text_norm for kw in kws):
            frameworks.append(fw)

    for ds, kws in _STACK_DATASTORE_KEYWORDS.items():
        if any(kw in text_norm for kw in kws):
            datastores.append(ds)

    for infra_name, kws in _STACK_INFRA_KEYWORDS.items():
        if any(kw in text_norm for kw in kws):
            infra.append(infra_name)

    # Из hints (stack/area)
    for hint in ctx.hints.stack:
        if hint not in languages:
            languages.append(hint)

    # Можно в будущем распознавать area→domain→stack; пока оставим как есть.

    return IntentStackInfo(
        languages=languages,
        frameworks=frameworks,
        datastores=datastores,
        infra=infra,
    )


def _classify_path(path: str) -> Tuple[str, str]:
    """
    Классифицируем путь как code/sql/docs/scripts.

    Возвращает:
        (category, normalized_path)
        category ∈ {"code", "sql_patches", "docs", "scripts"}
    """
    normalized = path.strip().strip("',\"")

    lowered = normalized.lower()
    if lowered.endswith(".sql"):
        return "sql_patches", normalized
    if lowered.endswith((".md", ".rst")):
        return "docs", normalized
    if lowered.endswith((".ps1", ".sh", ".bat")):
        return "scripts", normalized

    # Всё остальное по умолчанию считаем кодом
    return "code", normalized


def _detect_artifacts(text: str) -> IntentArtifactsExpected:
    """
    Простое извлечение путей, похожих на файлы проекта (src/scripts/docs).
    """
    if not text:
        return IntentArtifactsExpected()

    code_paths: List[str] = []
    sql_paths: List[str] = []
    doc_paths: List[str] = []
    script_paths: List[str] = []

    for match in _PATH_PATTERN.finditer(text):
        path = match.group("path")
        if not path:
            continue

        category, norm = _classify_path(path)

        if category == "code" and norm not in code_paths:
            code_paths.append(norm)
        elif category == "sql_patches" and norm not in sql_paths:
            sql_paths.append(norm)
        elif category == "docs" and norm not in doc_paths:
            doc_paths.append(norm)
        elif category == "scripts" and norm not in script_paths:
            script_paths.append(norm)

    return IntentArtifactsExpected(
        code=code_paths,
        sql_patches=sql_paths,
        docs=doc_paths,
        scripts=script_paths,
    )


def _estimate_scope(text_norm: str) -> IntentScope:
    length = len(text_norm)
    if length <= 400:
        return IntentScope.SMALL
    if length <= 1500:
        return IntentScope.MEDIUM
    return IntentScope.LARGE


def _detect_env_target(text_norm: str) -> EnvTarget:
    """
    Грубое определение целевого окружения.
    По умолчанию dev, если явно не упомянут prod/staging.
    """
    if "staging" in text_norm or "стейдж" in text_norm:
        return EnvTarget.STAGING
    if "prod" in text_norm or "production" in text_norm or "прод" in text_norm:
        return EnvTarget.PROD
    return EnvTarget.DEV


def _build_constraints(
    text_norm: str,
    task_kind: IntentTaskKind,
    domain: IntentDomainInfo,
    ctx: IntentContext,
) -> IntentConstraints:
    scope = _estimate_scope(text_norm)
    env_target = _detect_env_target(text_norm)

    # Дедлайн — грубая прикидка по размеру задачи
    if scope == IntentScope.SMALL:
        deadline_hours = 8
    elif scope == IntentScope.MEDIUM:
        deadline_hours = 24
    else:
        deadline_hours = 72

    non_destructive_only = True  # по канону FoxProFlow
    needs_review = False

    # Условия, когда явно нужен ревью Архитектора
    if task_kind in (IntentTaskKind.MIGRATION, IntentTaskKind.INFRA):
        needs_review = True
    if domain.primary in ("sec", "flowmeta", "eri"):
        needs_review = True
    if env_target is EnvTarget.PROD:
        needs_review = True

    return IntentConstraints(
        deadline_hours=deadline_hours,
        scope=scope,
        non_destructive_only=non_destructive_only,
        needs_review_by_architect=needs_review,
        env_target=env_target,
    )


def _build_risk(
    text_norm: str,
    task_kind: IntentTaskKind,
    domain: IntentDomainInfo,
    constraints: IntentConstraints,
) -> IntentRisk:
    tags: List[str] = []

    # Базовый уровень риска
    level = RiskLevel.MEDIUM

    # Повышенный риск для миграций/безопасности/ядра FlowMeta/ERI
    if task_kind == IntentTaskKind.MIGRATION:
        level = RiskLevel.HIGH
        tags.append("changes_db_schema")

    if domain.primary in ("sec", "flowmeta", "eri"):
        if level != RiskLevel.HIGH:
            level = RiskLevel.HIGH
        tags.append("touches_core_domain")

    # Присутствие security/FlowSec в тексте
    if "security" in text_norm or "flowsec" in text_norm or "безопасност" in text_norm:
        tags.append("touches_security")

    # Прод: чуть подтягиваем риск
    if constraints.env_target is EnvTarget.PROD and level != RiskLevel.HIGH:
        level = RiskLevel.HIGH
        tags.append("production_change")

    # Документация и исследование — чаще всего low
    if task_kind in (IntentTaskKind.DOC, IntentTaskKind.RESEARCH):
        if level != RiskLevel.HIGH:  # если уже high (sec/migration/prod) — не занижаем
            level = RiskLevel.LOW

    notes_parts: List[str] = []
    if task_kind == IntentTaskKind.MIGRATION:
        notes_parts.append("Содержит миграцию/изменение схемы БД.")
    if domain.primary in ("sec", "flowmeta", "eri"):
        notes_parts.append("Затрагивает чувствительный домен (sec/flowmeta/eri).")
    if constraints.env_target is EnvTarget.PROD:
        notes_parts.append("Планируется изменение в окружении prod.")

    notes = " ".join(notes_parts) if notes_parts else None

    # Убираем дубликаты тэгов
    unique_tags: List[str] = []
    for t in tags:
        if t not in unique_tags:
            unique_tags.append(t)

    return IntentRisk(
        level=level,
        tags=unique_tags,
        notes=notes,
    )
