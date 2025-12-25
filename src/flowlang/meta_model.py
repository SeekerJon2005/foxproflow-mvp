# -*- coding: utf-8 -*-
# file: src/flowlang/meta_model.py
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

__all__ = [
    "MetaEffect",
    "MetaDSL",
    "MetaDomain",
    "MetaAgentClass",
    "MetaPlanClass",
    "MetaPolicy",
    "MetaWorld",
    "MetaError",
    "MetaNotFoundError",
]


JsonDict = Dict[str, Any]


# === Ошибки FlowMeta ==================================================


class MetaError(Exception):
    """Базовая ошибка для FlowMeta."""


class MetaNotFoundError(MetaError):
    """
    Ошибка "не найдено" для доменов, DSL, эффектов, классов агентов/планов и политик.
    """

    def __init__(self, kind: str, code: str) -> None:
        super().__init__(f"{kind} with code={code!r} not found")
        self.kind = kind
        self.code = code


# === Базовые сущности FlowMeta =======================================


@dataclass
class MetaEffect:
    """
    Тип эффекта: DbRead, DbWrite, FSWrite, NetExternal, OSRMRoute, MLCall, GitOp, CIRun...

    kind: "db" | "fs" | "net" | "osrm" | "ml" | "git" | "ci" | ...
    scope: список паттернов ресурсов (например, ["public.*", "analytics.*"]).

    Соответствует строке таблицы flowmeta.effect_type.
    """

    id: Optional[int] = None
    code: str = ""
    kind: str = ""
    scope: List[str] = field(default_factory=list)
    description: Optional[str] = None
    meta: JsonDict = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: JsonDict) -> "MetaEffect":
        """
        Удобный конструктор из dict/строки БД (psycopg row -> dict).
        Ожидает ключи: id, code, kind, description, scope, meta.
        """
        return cls(
            id=row.get("id"),
            code=row["code"],
            kind=row["kind"],
            scope=list(row.get("scope") or []),
            description=row.get("description"),
            meta=dict(row.get("meta") or {}),
        )


@dataclass
class MetaDSL:
    """
    DSL в рамках домена: 'autoplan', 'dev', 'flowsec', 'etl', 'kpi', ...

    files_pattern: glob-паттерн для файлов, например "flow/autoplan/*.flow".
    Соответствует строке таблицы flowmeta.dsl.
    """

    id: Optional[int] = None
    code: str = ""
    domain: str = ""
    files_pattern: Optional[str] = None
    description: Optional[str] = None
    enabled: bool = True
    meta: JsonDict = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: JsonDict) -> "MetaDSL":
        return cls(
            id=row.get("id"),
            code=row["code"],
            domain=row["domain"],
            files_pattern=row.get("files_pattern"),
            description=row.get("description"),
            enabled=bool(row.get("enabled", True)),
            meta=dict(row.get("meta") or {}),
        )


@dataclass
class MetaDomain:
    """
    Домен/подсистема: logistics, dev, security, accounting, legal, citymap, ...

    dsl_codes: какие DSL принадлежат этому домену (заполняется MetaWorld.add_dsl()).

    Соответствует строке таблицы flowmeta.domain
    (dsl_codes может приходить из вьюхи/джоина, если она появится).
    """

    id: Optional[int] = None
    code: str = ""
    description: Optional[str] = None
    dsl_codes: List[str] = field(default_factory=list)
    meta: JsonDict = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: JsonDict) -> "MetaDomain":
        return cls(
            id=row.get("id"),
            code=row["code"],
            description=row.get("description"),
            dsl_codes=list(row.get("dsl_codes") or []),
            meta=dict(row.get("meta") or {}),
        )


@dataclass
class MetaAgentClass:
    """
    Класс агентов: AutoplanAgent, DevAgent, SecFox, GuardFox, DocFox, CityMapAgent, ...

    allow_effects / deny_effects — список MetaEffect.code.

    Соответствует строке таблицы flowmeta.agent_class.
    """

    id: Optional[int] = None
    code: str = ""
    domain: str = ""
    dsl_code: Optional[str] = None
    description: Optional[str] = None
    allow_effects: List[str] = field(default_factory=list)
    deny_effects: List[str] = field(default_factory=list)
    meta: JsonDict = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: JsonDict) -> "MetaAgentClass":
        return cls(
            id=row.get("id"),
            code=row["code"],
            domain=row["domain"],
            dsl_code=row.get("dsl_code"),
            description=row.get("description"),
            allow_effects=list(row.get("allow_effects") or []),
            deny_effects=list(row.get("deny_effects") or []),
            meta=dict(row.get("meta") or {}),
        )

    def allowed_effects_set(self) -> set[str]:
        return set(self.allow_effects)

    def denied_effects_set(self) -> set[str]:
        return set(self.deny_effects)


@dataclass
class MetaPlanClass:
    """
    Класс планов: AutoplanPlan, DevPlan, SecurityPolicy, ETLPlan, KPIPlan, ...

    default_effects — базовый набор эффектов для планов этого класса.

    Соответствует строке таблицы flowmeta.plan_class.
    """

    id: Optional[int] = None
    code: str = ""
    dsl_code: str = ""
    description: Optional[str] = None
    default_effects: List[str] = field(default_factory=list)
    meta: JsonDict = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: JsonDict) -> "MetaPlanClass":
        return cls(
            id=row.get("id"),
            code=row["code"],
            dsl_code=row["dsl_code"],
            description=row.get("description"),
            default_effects=list(row.get("default_effects") or []),
            meta=dict(row.get("meta") or {}),
        )

    def default_effects_set(self) -> set[str]:
        return set(self.default_effects)


@dataclass
class MetaPolicy:
    """
    Политика/инвариант FlowMeta.

    kind: 'invariant' | 'allow' | 'deny' | 'constraint' | ...
    definition: нормализованный AST политики в виде JSON-структуры.

    Соответствует строке таблицы flowmeta.policy.
    """

    id: Optional[int] = None
    code: str = ""
    kind: str = ""
    description: Optional[str] = None
    definition: JsonDict = field(default_factory=dict)
    enabled: bool = True
    meta: JsonDict = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: JsonDict) -> "MetaPolicy":
        return cls(
            id=row.get("id"),
            code=row["code"],
            kind=row["kind"],
            description=row.get("description"),
            definition=dict(row.get("definition") or {}),
            enabled=bool(row.get("enabled", True)),
            meta=dict(row.get("meta") or {}),
        )


@dataclass
class MetaWorld:
    """
    Корень FlowMeta: вся информация о доменах, DSL, эффектах, классах агентов/планов и политиках.

    world_name обычно 'foxproflow'.

    Этот объект может быть собран:
     - из flowmeta.domain/dsl/effect_type/agent_class/plan_class/policy,
     - из .meta/.flowmeta конфигов (через парсер),
     - гибридно.
    """

    world_name: str = "foxproflow"

    domains: Dict[str, MetaDomain] = field(default_factory=dict)
    dsls: Dict[str, MetaDSL] = field(default_factory=dict)
    effects: Dict[str, MetaEffect] = field(default_factory=dict)
    agent_classes: Dict[str, MetaAgentClass] = field(default_factory=dict)
    plan_classes: Dict[str, MetaPlanClass] = field(default_factory=dict)
    policies: Dict[str, MetaPolicy] = field(default_factory=dict)
    meta: JsonDict = field(default_factory=dict)

    # --- Добавление сущностей -----------------------------------------

    def add_domain(self, domain: MetaDomain) -> None:
        self.domains[domain.code] = domain

    def add_dsl(self, dsl: MetaDSL) -> None:
        self.dsls[dsl.code] = dsl
        # синхронизируем dsl_codes в домене (если он уже есть)
        dom = self.domains.get(dsl.domain)
        if dom and dsl.code not in dom.dsl_codes:
            dom.dsl_codes.append(dsl.code)

    def add_effect(self, effect: MetaEffect) -> None:
        self.effects[effect.code] = effect

    def add_agent_class(self, agent: MetaAgentClass) -> None:
        self.agent_classes[agent.code] = agent

    def add_plan_class(self, plan: MetaPlanClass) -> None:
        self.plan_classes[plan.code] = plan

    def add_policy(self, policy: MetaPolicy) -> None:
        self.policies[policy.code] = policy

    # --- Поиск/получение сущностей ------------------------------------

    # Домены

    def find_domain(self, code: str) -> Optional[MetaDomain]:
        return self.domains.get(code)

    def get_domain(self, code: str) -> MetaDomain:
        dom = self.find_domain(code)
        if dom is None:
            raise MetaNotFoundError("domain", code)
        return dom

    # DSL

    def find_dsl(self, code: str) -> Optional[MetaDSL]:
        return self.dsls.get(code)

    def get_dsl(self, code: str) -> MetaDSL:
        dsl = self.find_dsl(code)
        if dsl is None:
            raise MetaNotFoundError("dsl", code)
        return dsl

    # Эффекты

    def find_effect(self, code: str) -> Optional[MetaEffect]:
        return self.effects.get(code)

    def get_effect(self, code: str) -> MetaEffect:
        eff = self.find_effect(code)
        if eff is None:
            raise MetaNotFoundError("effect", code)
        return eff

    # Классы агентов

    def find_agent_class(self, code: str) -> Optional[MetaAgentClass]:
        return self.agent_classes.get(code)

    def get_agent_class(self, code: str) -> MetaAgentClass:
        agent = self.find_agent_class(code)
        if agent is None:
            raise MetaNotFoundError("agent_class", code)
        return agent

    # Классы планов

    def find_plan_class(self, code: str) -> Optional[MetaPlanClass]:
        return self.plan_classes.get(code)

    def get_plan_class(self, code: str) -> MetaPlanClass:
        plan = self.find_plan_class(code)
        if plan is None:
            raise MetaNotFoundError("plan_class", code)
        return plan

    # Политики

    def find_policy(self, code: str) -> Optional[MetaPolicy]:
        return self.policies.get(code)

    def get_policy(self, code: str) -> MetaPolicy:
        pol = self.find_policy(code)
        if pol is None:
            raise MetaNotFoundError("policy", code)
        return pol

    # --- Утилиты -------------------------------------------------------

    def summary(self) -> JsonDict:
        """
        Краткий срез мира FlowMeta — удобно для логов и отладки.
        """
        return {
            "world": self.world_name,
            "domains": sorted(self.domains.keys()),
            "dsls": sorted(self.dsls.keys()),
            "effects": sorted(self.effects.keys()),
            "agent_classes": sorted(self.agent_classes.keys()),
            "plan_classes": sorted(self.plan_classes.keys()),
            "policies": sorted(self.policies.keys()),
        }

    def to_dict(self) -> JsonDict:
        """
        Полный дамп мира FlowMeta в обычный dict (для JSON-логов, CLI, отладочных API).
        """
        return asdict(self)
