# -*- coding: utf-8 -*-
# file: src/flowlang/meta_validator.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from .meta_model import MetaWorld
from .meta_loader import load_world_from_dsn, MetaLoaderError

__all__ = [
    "MetaViolation",
    "validate_world",
    "main",
]

JsonDict = Dict[str, Any]

# Коды базовых политик (чтобы не размазывать magic-строки по файлу)
_POLICY_NO_EXTERNAL_NET_IN_CORE = "NoExternalNetInCore"
_POLICY_GUARD_REQUIRES_READ_ONLY = "GuardRequiresReadOnly"

# =============================================================================
# Модель нарушения политик FlowMeta
# =============================================================================


@dataclass
class MetaViolation:
    """
    Нарушение политики FlowMeta.

    policy_code: код политики (например, 'NoExternalNetInCore')
    target_kind: 'agent_class' | 'plan_class' | ...
    target_code: код сущности (например, 'AutoplanAgent')
    message: человекочитаемое описание
    severity: 'info' | 'warning' | 'error'
    details: любые дополнительные данные
    """
    policy_code: str
    target_kind: str
    target_code: str
    message: str
    severity: str = "warning"
    details: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return {
            "policy_code": self.policy_code,
            "target_kind": self.target_kind,
            "target_code": self.target_code,
            "message": self.message,
            "severity": self.severity,
            "details": self.details,
        }


# =============================================================================
# Простые проверки базовых политик
# =============================================================================

_CORE_DOMAINS: Set[str] = {
    "logistics",
    "accounting",
    "legal",
    "observability",
    "citymap",
}


def _check_no_external_net_in_core(world: MetaWorld) -> List[MetaViolation]:
    """
    Политика NoExternalNetInCore:
    - для core-доменов ('logistics','accounting','legal','observability','citymap')
      запрещаем NetExternal в allow_effects для классов агентов;
    - для планов core-DSL (autoplan, etl, kpi) запрещаем NetExternal в default_effects.
    """
    violations: List[MetaViolation] = []
    policy_code = _POLICY_NO_EXTERNAL_NET_IN_CORE

    # AgentClass в core-доменах
    for ac in world.agent_classes.values():
        if ac.domain not in _CORE_DOMAINS:
            continue

        if "NetExternal" in ac.allowed_effects_set():
            violations.append(
                MetaViolation(
                    policy_code=policy_code,
                    target_kind="agent_class",
                    target_code=ac.code,
                    message=(
                        "AgentClass в core-домене не должен иметь NetExternal "
                        "в allow_effects без явного override."
                    ),
                    severity="error",
                    details={
                        "domain": ac.domain,
                        "allow_effects": sorted(ac.allow_effects),
                    },
                )
            )

    # PlanClass в core-DSL
    core_dsls: Set[str] = {"autoplan", "etl", "kpi"}
    for pc in world.plan_classes.values():
        if pc.dsl_code not in core_dsls:
            continue
        if "NetExternal" in pc.default_effects_set():
            violations.append(
                MetaViolation(
                    policy_code=policy_code,
                    target_kind="plan_class",
                    target_code=pc.code,
                    message=(
                        "PlanClass с DSL в core (autoplan/etl/kpi) не должен иметь "
                        "NetExternal в default_effects."
                    ),
                    severity="error",
                    details={
                        "dsl_code": pc.dsl_code,
                        "default_effects": sorted(pc.default_effects),
                    },
                )
            )

    return violations


def _check_guard_requires_read_only(world: MetaWorld) -> List[MetaViolation]:
    """
    Политика GuardRequiresReadOnly:
    - guard-агенты (code содержит 'Guard' без учета регистра)
      должны быть read-only:
        * Нельзя DbWrite/FSWrite/NetExternal в allow_effects.
    """
    violations: List[MetaViolation] = []
    policy_code = _POLICY_GUARD_REQUIRES_READ_ONLY

    for ac in world.agent_classes.values():
        code_lower = ac.code.lower()
        if "guard" not in code_lower:
            continue

        allow = ac.allowed_effects_set()
        forbidden = {"DbWrite", "FSWrite", "NetExternal"}
        bad = sorted(list(allow & forbidden))

        if bad:
            violations.append(
                MetaViolation(
                    policy_code=policy_code,
                    target_kind="agent_class",
                    target_code=ac.code,
                    message=(
                        "Guard-агент должен быть read-only: DbWrite/FSWrite/NetExternal "
                        "запрещены в allow_effects."
                    ),
                    severity="error",
                    details={
                        "allow_effects": sorted(ac.allow_effects),
                        "forbidden_found": bad,
                    },
                )
            )

    return violations


# =============================================================================
# Главная функция валидации
# =============================================================================


def validate_world(world: MetaWorld) -> JsonDict:
    """
    Запускает все проверки FlowMeta и возвращает JSON-совместимый результат:

    {
      "ok": true/false,
      "n_violations": int,
      "violations": [ {...}, ... ],
      "summary": {...}
    }

    Важно: каждая проверка включается только если соответствующая политика
    существует в world.policies и помечена enabled = True.
    """
    violations: List[MetaViolation] = []

    enabled_policies: Set[str] = {
        p.code for p in world.policies.values() if p.enabled
    }

    # NoExternalNetInCore
    if _POLICY_NO_EXTERNAL_NET_IN_CORE in enabled_policies:
        violations.extend(_check_no_external_net_in_core(world))

    # GuardRequiresReadOnly
    if _POLICY_GUARD_REQUIRES_READ_ONLY in enabled_policies:
        violations.extend(_check_guard_requires_read_only(world))

    result: JsonDict = {
        "ok": len(violations) == 0,
        "n_violations": len(violations),
        "violations": [v.to_dict() for v in violations],
        "summary": world.summary(),
    }
    return result


# =============================================================================
# Утилиты для CLI
# =============================================================================


def _get_dsn_from_env(
    primary_var: str = "FF_DB_DSN",
    fallback_var: str = "DATABASE_URL",
) -> str:
    """
    Берёт DSN из переменных окружения (FF_DB_DSN или DATABASE_URL).
    """
    dsn = os.environ.get(primary_var) or os.environ.get(fallback_var)
    if not dsn:
        raise MetaLoaderError(
            f"Не найден DSN для БД: ни {primary_var}, ни {fallback_var} не заданы."
        )
    return dsn


def main() -> None:
    """
    CLI-утилита: загружает MetaWorld из БД, валидирует и печатает результат.

    Использование (из контейнера worker):
        FF_DB_DSN=postgresql://... python -m src.flowlang.meta_validator
    """
    dsn = _get_dsn_from_env()
    world = load_world_from_dsn(dsn)
    result = validate_world(world)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
