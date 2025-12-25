from __future__ import annotations

"""
DevFactory Question Engine (v0.1)

Файл:
    src/core/devfactory/question_engine.py

Назначение:
    Реализация ядра Question Engine:

        generate_questions(intent: IntentSpecV0_1, ctx: IntentContext) -> QuestionEngineResult

    Работает поверх Intent Parser, не трогает БД/файлы/сеть.
"""

from typing import List, Sequence, Set

from .intent_models import (
    IntentContext,
    IntentScope,
    IntentSpecV0_1,
    IntentTaskKind,
)
from .question_models import (
    QuestionAnswerType,
    QuestionEngineResult,
    QuestionPack,
    QuestionPackSelector,
    QuestionSpec,
)


def _scope_to_rank(scope: IntentScope | None) -> int:
    """
    Удобное числовое представление размеров задач.
    Используется только для сравнения min_scope/max_scope.
    """
    if scope is None:
        return 0
    if scope == IntentScope.SMALL:
        return 1
    if scope == IntentScope.MEDIUM:
        return 2
    if scope == IntentScope.LARGE:
        return 3
    return 0


def _selector_matches(
    selector: QuestionPackSelector,
    task_kind: IntentTaskKind,
    domain_primary: str | None,
    stack_tokens: Sequence[str],
    scope: IntentScope | None,
) -> bool:
    """Проверка, применим ли пакет вопросов к данной задаче."""

    # task_kind
    if selector.task_kinds and task_kind not in selector.task_kinds:
        return False

    # domain
    if selector.domains and (not domain_primary or domain_primary not in selector.domains):
        return False

    # stack_contains
    if selector.stack_contains:
        stack_set: Set[str] = {s.lower() for s in stack_tokens}
        needed_set: Set[str] = {s.lower() for s in selector.stack_contains}
        if not (stack_set & needed_set):
            return False

    # scope
    if scope is not None:
        scope_rank = _scope_to_rank(scope)
        if selector.min_scope is not None:
            if scope_rank < _scope_to_rank(selector.min_scope):
                return False
        if selector.max_scope is not None:
            if scope_rank > _scope_to_rank(selector.max_scope):
                return False

    return True


def _collect_stack_tokens(intent: IntentSpecV0_1) -> List[str]:
    """
    Собираем все элементы стека в один плоский список строк.
    """
    tokens: List[str] = []
    tokens.extend(intent.stack.languages or [])
    tokens.extend(intent.stack.frameworks or [])
    tokens.extend(intent.stack.datastores or [])
    tokens.extend(intent.stack.infra or [])
    return tokens


# -------------------------------
# Статические QuestionPack'и для v0.1
# -------------------------------

QUESTION_PACKS_V0_1: List[QuestionPack] = [
    QuestionPack(
        id="feature_devfactory_python",
        selector=QuestionPackSelector(
            task_kinds=[IntentTaskKind.FEATURE],
            domains=["devfactory"],
            stack_contains=["python"],
            min_scope=None,
            max_scope=None,
        ),
        questions=[
            QuestionSpec(
                id="devfactory_api_behavior",
                text=(
                    "Опишите ожидаемое поведение эндпоинта /api/...: "
                    "какие параметры он должен принимать и что именно возвращать?"
                ),
                target="api.behavior",
                required=True,
                answer_type=QuestionAnswerType.TEXT,
                help="Кратко опишите входные параметры и структуру ответа.",
            ),
            QuestionSpec(
                id="devfactory_api_auth",
                text=(
                    "Какая модель доступа нужна для эндпоинта "
                    "(public, только авторизованные пользователи, по FlowSec-политикам)?"
                ),
                target="api.security.auth",
                required=True,
                answer_type=QuestionAnswerType.CHOICE,
                choices=["public", "auth_required", "restricted_by_policy"],
                help="Если не уверены, чаще всего подходит вариант auth_required.",
            ),
            QuestionSpec(
                id="devfactory_api_pagination",
                text=(
                    "Список сущностей (например DevOrders) нужно возвращать полностью "
                    "или с пагинацией?"
                ),
                target="api.response.pagination",
                required=False,
                answer_type=QuestionAnswerType.CHOICE,
                choices=["full_list", "paginated"],
                help="Если ожидается большое количество записей, лучше использовать пагинацию.",
            ),
            QuestionSpec(
                id="devfactory_api_filters",
                text=(
                    "Нужны ли фильтры (по статусу, стеку, дате создания) "
                    "для списка сущностей?"
                ),
                target="api.request.filters",
                required=False,
                answer_type=QuestionAnswerType.TEXT,
                help="Перечислите основные поля для фильтрации или напишите 'нет'.",
            ),
            QuestionSpec(
                id="devfactory_api_sorting",
                text=(
                    "Есть ли требования к сортировке списка (по дате, статусу, стеку, ...)?"
                ),
                target="api.response.sorting",
                required=False,
                answer_type=QuestionAnswerType.TEXT,
                help="Например: по дате создания по убыванию.",
            ),
        ],
    ),
    QuestionPack(
        id="migration_logistics_sql",
        selector=QuestionPackSelector(
            task_kinds=[IntentTaskKind.MIGRATION],
            domains=["logistics"],
            stack_contains=["sql"],
            min_scope=None,
            max_scope=None,
        ),
        questions=[
            QuestionSpec(
                id="logistics_migration_backfill",
                text=(
                    "Нужен ли backfill данных при применении миграции? "
                    "Если да, то какой стратегии нужно придерживаться?"
                ),
                target="migration.data.backfill_strategy",
                required=True,
                answer_type=QuestionAnswerType.TEXT,
                help="Опишите, как заполнить значения в новых колонках для существующих строк.",
            ),
            QuestionSpec(
                id="logistics_migration_downtime",
                text="Допускается ли downtime при применении миграции?",
                target="migration.sla.downtime",
                required=True,
                answer_type=QuestionAnswerType.CHOICE,
                choices=["zero_downtime", "maintenance_window"],
                help="Если простаивание недопустимо, выбирайте zero_downtime.",
            ),
            QuestionSpec(
                id="logistics_migration_rollback",
                text="Нужна ли явная стратегия отката миграции? Если да, опишите её кратко.",
                target="migration.rollback.strategy",
                required=True,
                answer_type=QuestionAnswerType.TEXT,
                help=(
                    "Например: отдельный SQL-скрипт для удаления колонок/таблиц "
                    "и восстановления старых данных."
                ),
            ),
        ],
    ),
]


# -------------------------------
# Публичное API Question Engine
# -------------------------------


def generate_questions(
    intent: IntentSpecV0_1,
    ctx: IntentContext,
    max_questions: int = 5,
) -> QuestionEngineResult:
    """
    Сгенерировать список вопросов на основе IntentSpec и контекста.

    Работает на чистых структурах, не обращается к БД/файлам/сети.
    """
    domain_primary = intent.domain.primary
    stack_tokens = _collect_stack_tokens(intent)
    scope = intent.constraints.scope

    applicable_packs: List[QuestionPack] = []
    for pack in QUESTION_PACKS_V0_1:
        if _selector_matches(
            pack.selector,
            task_kind=intent.task_kind,
            domain_primary=domain_primary,
            stack_tokens=stack_tokens,
            scope=scope,
        ):
            applicable_packs.append(pack)

    # Собираем вопросы, устраняя дубликаты по id (последние перекрывают предыдущие)
    questions_by_id: dict[str, QuestionSpec] = {}
    for pack in applicable_packs:
        for q in pack.questions:
            questions_by_id[q.id] = q

    all_questions: List[QuestionSpec] = list(questions_by_id.values())
    if not all_questions:
        # Нет подходящих пакетов — возвращаем пустой список
        return QuestionEngineResult(
            questions=[],
            meta={
                "auto_generated": True,
                "pack_ids": [],
                "reasoning": [
                    f"no_question_packs_matched: task_kind={intent.task_kind.value}, "
                    f"domain={domain_primary or 'unknown'}"
                ],
            },
        )

    # Приоритизация: сначала обязательные, потом необязательные
    required_questions = [q for q in all_questions if q.required]
    optional_questions = [q for q in all_questions if not q.required]

    ordered: List[QuestionSpec] = []
    ordered.extend(required_questions)
    ordered.extend(optional_questions)

    if max_questions > 0:
        ordered = ordered[:max_questions]

    meta_reasoning = [
        f"task_kind={intent.task_kind.value}",
        f"domain={domain_primary or 'unknown'}",
        f"stack_tokens={sorted(set(t.lower() for t in stack_tokens))}",
        f"scope={scope.value if scope is not None else 'none'}",
    ]

    return QuestionEngineResult(
        questions=ordered,
        meta={
            "auto_generated": True,
            "pack_ids": [p.id for p in applicable_packs],
            "reasoning": meta_reasoning,
        },
    )
