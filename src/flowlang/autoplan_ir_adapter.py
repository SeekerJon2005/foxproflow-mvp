from __future__ import annotations

from typing import Any, Dict, Optional

from .ir import FlowEffectKind, FlowNode, FlowPlanIR, explain_plan


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_autoplan_chain_ir_from_config(config: Dict[str, Any]) -> FlowPlanIR:
    """Собрать FlowPlanIR для цепочки автоплана из конфига /api/autoplan/config.

    Ожидаемый формат config — примерно как JSON из /api/autoplan/config:
    {
      "flow_plan_name": "msk_day",
      "rpm_min": "120",
      "rpm_floor_min": "120",
      "p_arrive_min": "0.30",
      "apply_window_min": "360",
      "horizon_h": "24",
      "flow_plan": {
        "freights_days_back": 2,
        "apply_window_min": 360,
        "confirm_window_min": 360,
        "confirm_horizon_h": 72,
        "rpm_min": 90,
        "confirm_rpm_min": 90,
        "rph_min": 2000,
        "use_dynamic_rpm": true,
        "dynamic_rpm_quantile": "p25",
        "dynamic_rpm_floor_min": 110,
        "chain_every_minutes": 30,
        "chain_limit": 50,
        "chain_queue": "autoplan",
        "chain_task": "task_autoplan_chain",
        "chain_slot_id": "autoplan-msk-day-30m"
      },
      ...
    }

    Функция не ходит в БД/Redis/OSRM, работает только с диктом.
    """

    plan_name = str(config.get("flow_plan_name") or "autoplan")
    flow_plan = config.get("flow_plan") or {}

    # Версию плана можно брать из вложенного flow_plan, если она там есть
    plan_version = str(flow_plan.get("version", "1"))

    # Параметры цепочки — либо из flow_plan, либо из верхнего уровня, либо дефолты
    chain_task = (
        flow_plan.get("chain_task")
        or config.get("chain_task")
        or "task_autoplan_chain"
    )
    chain_queue = (
        flow_plan.get("chain_queue")
        or config.get("chain_queue")
        or "autoplan"
    )
    chain_every_minutes = (
        flow_plan.get("chain_every_minutes")
        or config.get("chain_every_minutes")
    )
    chain_limit = (
        flow_plan.get("chain_limit")
        or config.get("chain_limit")
    )
    chain_slot_id = (
        flow_plan.get("chain_slot_id")
        or config.get("chain_slot_id")
        or f"autoplan-{plan_name}"
    )

    plan_id = f"autoplan_chain:{plan_name}"
    plan_title = f"Autoplan chain ({plan_name})"

    # Собираем основные параметры в meta — пригодится для Explain/агентов
    meta: Dict[str, Any] = {
        "flow_plan_name": plan_name,
        # Параметры окна/горизонта
        "freights_days_back": flow_plan.get("freights_days_back"),
        "apply_window_min": flow_plan.get("apply_window_min"),
        "confirm_window_min": flow_plan.get("confirm_window_min"),
        "confirm_horizon_h": flow_plan.get("confirm_horizon_h"),
        # Пороговые значения
        "rpm_min": flow_plan.get("rpm_min"),
        "confirm_rpm_min": flow_plan.get("confirm_rpm_min"),
        "rph_min": flow_plan.get("rph_min"),
        "use_dynamic_rpm": flow_plan.get("use_dynamic_rpm"),
        "dynamic_rpm_quantile": flow_plan.get("dynamic_rpm_quantile"),
        "dynamic_rpm_floor_min": flow_plan.get("dynamic_rpm_floor_min"),
        # Env-уровень для полного контекста
        "env_rpm_min": _as_float(config.get("rpm_min")),
        "env_rpm_floor_min": _as_float(config.get("rpm_floor_min")),
        "env_p_arrive_min": _as_float(config.get("p_arrive_min")),
        "env_apply_window_min": _as_float(config.get("apply_window_min")),
        "env_horizon_h": _as_float(config.get("horizon_h")),
        # Параметры самой цепочки (beat / Celery)
        "chain_task": chain_task,
        "chain_queue": chain_queue,
        "chain_every_minutes": chain_every_minutes,
        "chain_limit": chain_limit,
        "chain_slot_id": chain_slot_id,
    }

    plan = FlowPlanIR(
        id=plan_id,
        name=plan_title,
        version=plan_version,
        meta=meta,
    )

    # --- audit ---

    audit = FlowNode(
        id="audit",
        name="planner.autoplan.audit",
        description="Аудит заявок/ТС с учётом окон, RPM/RPH и вероятности прибытия.",
        critical=True,
    ).add_effect(
        FlowEffectKind.DB,
        "Читает заявки/ТС, матчит окна погрузки/выгрузки и считает базовые метрики (p_arrive, RPM, RPH).",
        phase="audit",
    ).add_tags("phase:audit", "autoplan")

    # --- apply ---

    apply = FlowNode(
        id="apply",
        name="planner.autoplan.apply",
        description="Формирует проектные рейсы (draft) и план на ТС по результатам аудита.",
        critical=True,
        upstream=["audit"],
    ).add_effect(
        FlowEffectKind.DB,
        "Создаёт/обновляет draft-трипы и план на ТС с учётом ограничений RPM/RPH/окон.",
        phase="apply",
    ).add_tags("phase:apply", "autoplan")

    # --- push_to_trips ---

    push = FlowNode(
        id="push_to_trips",
        name="planner.autoplan.push_to_trips",
        description="Переносит утверждённый план из драфта в таблицу trips.",
        critical=True,
        upstream=["apply"],
    ).add_effect(
        FlowEffectKind.DB,
        "Заполняет trips и сегменты, связывает с фрахтами и ТС.",
        phase="push",
    ).add_tags("phase:push", "autoplan")

    # --- confirm ---

    confirm = FlowNode(
        id="confirm",
        name="planner.autoplan.confirm",
        description="Финальное подтверждение рейсов, фиксация цен и блокировка слота ТС.",
        critical=True,
        upstream=["push_to_trips"],
    ).add_effect(
        FlowEffectKind.DB,
        "Фиксирует confirm, цены и окна, закрывает слот доступности ТС.",
        phase="confirm",
    ).add_effect(
        FlowEffectKind.OSRM,
        "При необходимости инициирует обогащение маршрутов (OSRM / OD-кэш) для новых подтверждённых рейсов.",
        phase="confirm",
    ).add_tags("phase:confirm", "autoplan")

    for node in (audit, apply, push, confirm):
        plan.add_node(node)

    return plan


def explain_autoplan_chain_from_config(config: Dict[str, Any]) -> str:
    """Explain для реального плана автоплана на основе конфига."""
    plan = build_autoplan_chain_ir_from_config(config)
    return explain_plan(plan)


def _main() -> None:
    """CLI для использования из контейнера.

    Ожидает JSON-конфиг автоплана на stdin и печатает либо человекочитаемый Explain,
    либо JSON-представление IR-плана.

    Примеры вызова (из worker-контейнера):

        # Explain-представление (по умолчанию)
        python -m src.flowlang.autoplan_ir_adapter < /tmp/autoplan_config.json

        # JSON-представление FlowIR (plan.to_dict())
        python -m src.flowlang.autoplan_ir_adapter --json < /tmp/autoplan_config.json
    """
    import json
    import sys

    args = sys.argv[1:]
    json_mode = "--json" in args

    try:
        data = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"failed to read JSON config from stdin: {exc}\n")
        sys.exit(1)

    if json_mode:
        plan = build_autoplan_chain_ir_from_config(data)
        json.dump(plan.to_dict(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        text = explain_autoplan_chain_from_config(data)
        print(text)


if __name__ == "__main__":
    _main()
