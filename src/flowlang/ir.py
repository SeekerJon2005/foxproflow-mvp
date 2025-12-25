from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional


class FlowEffectKind(str, Enum):
    """Тип побочного эффекта узла плана.

    Это тех. классификация: что трогает узел — БД, сеть, OSRM, ML и т.д.
    """

    DB = "db"
    OSRM = "osrm"
    NET = "net"
    ML = "ml"
    AGENT = "agent"
    IO = "io"


@dataclass
class FlowEffect:
    """Описание побочного эффекта узла (что именно он делает с внешним миром)."""

    kind: FlowEffectKind
    description: str
    weight: int = 1
    meta: Dict[str, Any] = field(default_factory=dict)

    # --- служебные методы ---

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация эффекта в dict (для логов / JSON / хранения в БД)."""
        return {
            "kind": self.kind.value,
            "description": self.description,
            "weight": self.weight,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowEffect":
        """Обратная операция к to_dict.

        Сделано максимально терпимым к "кривым" данным:
        если kind неизвестен — по умолчанию считаем, что это DB.
        """
        kind_raw = data.get("kind", FlowEffectKind.DB.value)
        try:
            kind = FlowEffectKind(kind_raw)
        except ValueError:
            kind = FlowEffectKind.DB

        return cls(
            kind=kind,
            description=data.get("description", ""),
            weight=int(data.get("weight", 1)),
            meta=dict(data.get("meta", {}) or {}),
        )


@dataclass
class FlowNode:
    """Узел плана (шаг пайплайна / таска / витрина)."""

    id: str
    name: str
    description: str = ""
    upstream: List[str] = field(default_factory=list)
    effects: List[FlowEffect] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    critical: bool = False

    # --- fluent API ---

    def add_effect(self, kind: FlowEffectKind, description: str, **meta: Any) -> "FlowNode":
        self.effects.append(FlowEffect(kind=kind, description=description, meta=meta))
        return self

    def add_upstream(self, *node_ids: str) -> "FlowNode":
        for nid in node_ids:
            if nid not in self.upstream:
                self.upstream.append(nid)
        return self

    def add_tags(self, *tags: str) -> "FlowNode":
        for tag in tags:
            if tag not in self.tags:
                self.tags.append(tag)
        return self

    # --- служебные методы ---

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация узла в dict."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "upstream": list(self.upstream),
            "effects": [e.to_dict() for e in self.effects],
            "tags": list(self.tags),
            "critical": self.critical,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowNode":
        """Создание узла из dict (обратная операция к to_dict)."""
        effects_raw = data.get("effects", []) or []
        effects = [FlowEffect.from_dict(e) for e in effects_raw]

        return cls(
            id=str(data.get("id")),
            name=str(data.get("name", "")),
            description=data.get("description", "") or "",
            upstream=list(data.get("upstream", []) or []),
            effects=effects,
            tags=list(data.get("tags", []) or []),
            critical=bool(data.get("critical", False)),
        )


@dataclass
class FlowPlanIR:
    """FlowIR-представление плана.

    Это уже «сваренная» структура, удобная для Explain и генераторов,
    независимо от синтаксиса исходного FlowLang.
    """

    id: str
    name: str
    version: str = "0"
    nodes: Dict[str, FlowNode] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    # --- работа с узлами ---

    def add_node(self, node: FlowNode) -> "FlowPlanIR":
        if node.id in self.nodes:
            raise ValueError(f"FlowPlanIR[{self.id!r}] already has node id={node.id!r}")
        self.nodes[node.id] = node
        return self

    def get_node(self, node_id: str) -> Optional[FlowNode]:
        return self.nodes.get(node_id)

    def __iter__(self) -> Iterable[FlowNode]:
        return iter(self.nodes.values())

    def topo_sorted(self) -> List[FlowNode]:
        """Простейшая топосортировка по upstream.

        Если есть цикл — он не ломает систему, но узлы с циклом
        окажутся в конце списка в произвольном порядке.
        """
        nodes = self.nodes
        indegree: Dict[str, int] = {nid: 0 for nid in nodes}
        for node in nodes.values():
            for parent in node.upstream:
                if parent in indegree:
                    indegree[node.id] += 1

        queue: List[str] = [nid for nid, deg in indegree.items() if deg == 0]
        ordered: List[str] = []

        while queue:
            nid = queue.pop(0)
            ordered.append(nid)
            for child in nodes.values():
                if nid in child.upstream:
                    indegree[child.id] -= 1
                    if indegree[child.id] == 0:
                        queue.append(child.id)

        # добавляем «хвост» (возможные циклы)
        for nid in nodes:
            if nid not in ordered:
                ordered.append(nid)

        return [nodes[nid] for nid in ordered]

    def nodes_by_tag(self, tag: str) -> List[FlowNode]:
        """Вернуть все узлы, помеченные данным тегом (например, phase:audit)."""
        return [n for n in self.nodes.values() if tag in n.tags]

    # --- сериализация плана ---

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация плана в dict (для JSON / БД / API)."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "meta": self.meta,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowPlanIR":
        """Создать FlowPlanIR из dict (обратная операция к to_dict)."""
        plan = cls(
            id=str(data.get("id")),
            name=str(data.get("name", "")),
            version=str(data.get("version", "0")),
            meta=dict(data.get("meta", {}) or {}),
        )

        nodes_raw = data.get("nodes", {}) or {}
        # nodes_raw может быть dict(id -> node_dict) или list[node_dict]
        if isinstance(nodes_raw, dict):
            items = nodes_raw.items()
        else:
            # список — тогда ожидаем, что в каждом dict есть id
            items = [(n.get("id"), n) for n in nodes_raw]

        for nid, nd in items:
            if nd is None:
                continue
            node = FlowNode.from_dict(nd)
            # на всякий случай соблюдаем согласованность id
            node.id = str(nid) if nid is not None else node.id
            plan.add_node(node)

        return plan


def explain_plan(plan: FlowPlanIR) -> str:
    """Человекочитаемый Explain для плана (без походов в БД)."""
    lines: List[str] = []
    lines.append(f"Flow plan: {plan.name} (id={plan.id}, version={plan.version})")

    if plan.meta:
        lines.append("")
        lines.append("Meta:")
        for key, value in sorted(plan.meta.items()):
            lines.append(f"  - {key}: {value}")

    lines.append("")
    lines.append("Nodes:")

    for node in plan.topo_sorted():
        prefix = "!*" if node.critical else " *"
        lines.append(f"{prefix} {node.id}: {node.name}")

        if node.description:
            lines.append(f"    {node.description}")

        if node.upstream:
            upstream_str = ", ".join(node.upstream)
            lines.append(f"    depends on: {upstream_str}")

        if node.tags:
            tags_str = ", ".join(sorted(node.tags))
            lines.append(f"    tags: {tags_str}")

        if node.effects:
            lines.append("    effects:")
            for eff in node.effects:
                suffix = f" (x{eff.weight})" if eff.weight != 1 else ""
                lines.append(f"      - [{eff.kind.value}]{suffix} {eff.description}")

    return "\n".join(lines)


def _demo_autoplan_chain_ir() -> FlowPlanIR:
    """Демо-план для цепочки автоплана audit→apply→push→confirm.

    Это не боевой конфиг, а пример структуры для отладки Explain/визуализации.
    """
    plan = FlowPlanIR(
        id="autoplan_chain_demo",
        name="Autoplan chain (demo)",
        version="1",
        meta={
            "slot": "autoplan-msk-day-30m",
            "queue": "autoplan",
            "chain_task": "task_autoplan_chain",
        },
    )

    audit = FlowNode(
        id="audit",
        name="planner.autoplan.audit",
        description="Аудит заявок/ТС с учётом окон и RPM/RPH.",
        critical=True,
    ).add_effect(
        FlowEffectKind.DB,
        "Читает заявки/ТС, матчит окна, считает вероятности и метрики RPM/RPH.",
    ).add_tags("phase:audit", "autoplan")

    apply = FlowNode(
        id="apply",
        name="planner.autoplan.apply",
        description="Формирует проектные рейсы (draft) и план на ТС.",
        critical=True,
        upstream=["audit"],
    ).add_effect(
        FlowEffectKind.DB,
        "Создаёт/обновляет draft-трипы и план на ТС.",
    ).add_tags("phase:apply", "autoplan")

    push = FlowNode(
        id="push_to_trips",
        name="planner.autoplan.push_to_trips",
        description="Записывает утверждённый план в таблицу trips.",
        critical=True,
        upstream=["apply"],
    ).add_effect(
        FlowEffectKind.DB,
        "Заполняет trips и сегменты, подготавливает к confirm.",
    ).add_tags("phase:push", "autoplan")

    confirm = FlowNode(
        id="confirm",
        name="planner.autoplan.confirm",
        description="Финальное подтверждение рейсов и блокировка слота ТС.",
        critical=True,
        upstream=["push_to_trips"],
    ).add_effect(
        FlowEffectKind.DB,
        "Фиксирует confirm, цены и окна, запускает обогащение маршрутом.",
    ).add_effect(
        FlowEffectKind.OSRM,
        "При необходимости инициирует обогащение маршрутов (OSRM / OD-кэш).",
    ).add_tags("phase:confirm", "autoplan")

    for node in (audit, apply, push, confirm):
        plan.add_node(node)

    return plan


def explain_autoplan_chain_demo() -> str:
    """Удобная обёртка для Explain демо-плана автоплана."""
    return explain_plan(_demo_autoplan_chain_ir())


if __name__ == "__main__":
    # Простейший CLI для ручного прогона:
    # docker exec -it worker sh -lc "cd /app && python -m src.flowlang.ir"
    print(explain_autoplan_chain_demo())
