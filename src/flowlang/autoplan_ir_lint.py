from __future__ import annotations

import json
import sys
from typing import Any, Dict, List


def _as_float(meta: Dict[str, Any], key: str, issues: List[str]) -> float | None:
    """Безопасно достать число из meta[key]."""
    if key not in meta or meta[key] is None:
        return None
    value = meta[key]
    try:
        return float(value)
    except (TypeError, ValueError):
        issues.append(f"meta.{key} is not numeric: {value!r}")
        return None


def _as_int(meta: Dict[str, Any], key: str, issues: List[str]) -> int | None:
    """Безопасно достать целое число из meta[key]."""
    if key not in meta or meta[key] is None:
        return None
    value = meta[key]
    try:
        return int(value)
    except (TypeError, ValueError):
        issues.append(f"meta.{key} is not integer: {value!r}")
        return None


def lint_flow_plan_ir(ir: Dict[str, Any]) -> Dict[str, Any]:
    """Проверить FlowIR-план на базовую консистентность.

    ir — это dict в формате plan.to_dict() из FlowIR.
    """
    issues: List[str] = []
    warnings: List[str] = []

    meta: Dict[str, Any] = ir.get("meta") or {}
    nodes: Dict[str, Any] = ir.get("nodes") or {}

    # --- 1. Проверяем, что базовые ключи meta присутствуют ---

    required_meta = [
        "flow_plan_name",
        "freights_days_back",
        "apply_window_min",
        "confirm_window_min",
        "confirm_horizon_h",
        "rpm_min",
        "confirm_rpm_min",
        "rph_min",
        "use_dynamic_rpm",
    ]
    for key in required_meta:
        if key not in meta or meta[key] is None:
            issues.append(f"meta.{key} is missing or null")

    # --- 2. Числовые проверки ---

    freights_days_back = _as_int(meta, "freights_days_back", issues)
    if freights_days_back is not None and freights_days_back < 0:
        issues.append("meta.freights_days_back < 0 (ожидается >= 0)")

    apply_window_min = _as_float(meta, "apply_window_min", issues)
    confirm_window_min = _as_float(meta, "confirm_window_min", issues)
    confirm_horizon_h = _as_float(meta, "confirm_horizon_h", issues)
    rpm_min = _as_float(meta, "rpm_min", issues)
    confirm_rpm_min = _as_float(meta, "confirm_rpm_min", issues)
    rph_min = _as_float(meta, "rph_min", issues)

    if apply_window_min is not None and apply_window_min <= 0:
        issues.append("meta.apply_window_min must be > 0")

    if confirm_window_min is not None and confirm_window_min <= 0:
        issues.append("meta.confirm_window_min must be > 0")

    if confirm_horizon_h is not None and confirm_horizon_h <= 0:
        issues.append("meta.confirm_horizon_h must be > 0")

    if rpm_min is not None and rpm_min < 0:
        issues.append("meta.rpm_min must be >= 0")

    if confirm_rpm_min is not None and confirm_rpm_min < 0:
        issues.append("meta.confirm_rpm_min must be >= 0")

    if rph_min is not None and rph_min < 0:
        issues.append("meta.rph_min must be >= 0")

    # Простая проверка «единиц измерения»: окно подтверждения не должно
    # быть сильно больше горизонта (минуты vs часы * 60). Это скорее hint.
    if (
        confirm_window_min is not None
        and confirm_horizon_h is not None
        and confirm_window_min > confirm_horizon_h * 60.0
    ):
        warnings.append(
            "meta.confirm_window_min > meta.confirm_horizon_h * 60 — проверь единицы (минуты/часы)"
        )

    # Env-слой vs plan-слой — это скорее предупреждения, а не ошибки.
    env_apply_window_min = _as_float(meta, "env_apply_window_min", issues)
    if (
        env_apply_window_min is not None
        and apply_window_min is not None
        and abs(env_apply_window_min - apply_window_min) > 1e-6
    ):
        warnings.append(
            f"env_apply_window_min ({env_apply_window_min}) != apply_window_min ({apply_window_min})"
        )

    env_rpm_min = _as_float(meta, "env_rpm_min", issues)

    # --- 2.1. Dynamic RPM ---

    use_dynamic_rpm = meta.get("use_dynamic_rpm")
    dynamic_rpm_quantile = meta.get("dynamic_rpm_quantile")
    dynamic_rpm_floor_min = _as_float(meta, "dynamic_rpm_floor_min", issues)
    env_rpm_floor_min = _as_float(meta, "env_rpm_floor_min", issues)

    use_dynamic_flag = False
    if isinstance(use_dynamic_rpm, bool):
        use_dynamic_flag = use_dynamic_rpm
    elif isinstance(use_dynamic_rpm, str):
        use_dynamic_flag = use_dynamic_rpm.lower() in ("1", "true", "yes", "y")

    if use_dynamic_flag:
        if not dynamic_rpm_quantile:
            issues.append(
                "meta.use_dynamic_rpm is true but meta.dynamic_rpm_quantile is not set"
            )
        if dynamic_rpm_floor_min is None:
            issues.append(
                "meta.use_dynamic_rpm is true but meta.dynamic_rpm_floor_min is not set"
            )
    else:
        # Параметры dynamic_* заданы, но use_dynamic_rpm выключен — подсветим как warning
        if dynamic_rpm_quantile or dynamic_rpm_floor_min is not None:
            warnings.append(
                "dynamic RPM params (dynamic_rpm_quantile/floor_min) заданы, "
                "но meta.use_dynamic_rpm не включён"
            )

    if dynamic_rpm_floor_min is not None and dynamic_rpm_floor_min < 0:
        issues.append("meta.dynamic_rpm_floor_min must be >= 0")

    # Связь dynamic floor с env и плановыми порогами
    if (
        dynamic_rpm_floor_min is not None
        and env_rpm_floor_min is not None
        and dynamic_rpm_floor_min > env_rpm_floor_min
    ):
        warnings.append(
            f"dynamic_rpm_floor_min ({dynamic_rpm_floor_min}) > env_rpm_floor_min ({env_rpm_floor_min}) — "
            "проверь, что глобальный env-флор не ниже динамического."
        )

    if (
        dynamic_rpm_floor_min is not None
        and rpm_min is not None
        and dynamic_rpm_floor_min < rpm_min
    ):
        warnings.append(
            f"dynamic_rpm_floor_min ({dynamic_rpm_floor_min}) < rpm_min ({rpm_min}) — "
            "динамический флор ниже статического порога RPM."
        )

    # Env vs плановый rpm_min
    if env_rpm_min is not None and rpm_min is not None:
        # env_rpm_min выше планового rpm_min — это не ошибка, но можно подсветить
        if env_rpm_min > rpm_min:
            warnings.append(
                f"env_rpm_min ({env_rpm_min}) > rpm_min ({rpm_min}) — "
                "проверь, что это ожидаемое поведение (env как общий floor)."
            )

    # --- 2.2. Параметры цепочки (chain_*) ---

    chain_every_minutes = _as_float(meta, "chain_every_minutes", issues)
    chain_limit = _as_int(meta, "chain_limit", issues)
    chain_task = meta.get("chain_task")
    chain_queue = meta.get("chain_queue")
    chain_slot_id = meta.get("chain_slot_id")

    if not chain_task:
        warnings.append("meta.chain_task is missing or empty")

    if not chain_queue:
        warnings.append("meta.chain_queue is missing or empty")

    if not chain_slot_id:
        warnings.append("meta.chain_slot_id is missing or empty")

    if chain_every_minutes is not None and chain_every_minutes <= 0:
        issues.append("meta.chain_every_minutes must be > 0")

    if chain_limit is not None and chain_limit <= 0:
        issues.append("meta.chain_limit must be > 0")

    # --- 3. Структура узлов цепочки автоплана ---

    # Набор must-have узлов
    required_nodes = ["audit", "apply", "push_to_trips", "confirm"]
    for node_id in required_nodes:
        if node_id not in nodes:
            issues.append(f"node '{node_id}' is missing in FlowIR.nodes")

    # Если какие-то узлы есть — проверяем зависимости
    audit_node = nodes.get("audit") or {}
    apply_node = nodes.get("apply") or {}
    push_node = nodes.get("push_to_trips") or {}
    confirm_node = nodes.get("confirm") or {}

    apply_upstream = apply_node.get("upstream") or []
    if "audit" not in apply_upstream:
        issues.append(
            "node 'apply' does not depend on 'audit' (missing 'audit' in upstream)"
        )

    push_upstream = push_node.get("upstream") or []
    if "apply" not in push_upstream:
        issues.append("node 'push_to_trips' does not depend on 'apply'")

    confirm_upstream = confirm_node.get("upstream") or []
    if "push_to_trips" not in confirm_upstream:
        issues.append("node 'confirm' does not depend on 'push_to_trips'")

    # Теги фаз — не критично, но полезно
    for node_id, expected_tag in [
        ("audit", "phase:audit"),
        ("apply", "phase:apply"),
        ("push_to_trips", "phase:push"),
        ("confirm", "phase:confirm"),
    ]:
        node = nodes.get(node_id) or {}
        tags = node.get("tags") or []
        if expected_tag not in tags:
            warnings.append(f"node '{node_id}' has no tag '{expected_tag}'")

    ok = not issues

    return {
        "ok": ok,
        "issues": issues,
        "warnings": warnings,
        "meta": meta,
    }


def _main() -> None:
    """CLI: читает FlowIR JSON из stdin, печатает результат.

    Примеры (из контейнера worker):

        # Текстовое резюме
        python -m src.flowlang.autoplan_ir_lint < flow_ir.json

        # JSON-резюме
        python -m src.flowlang.autoplan_ir_lint --json < flow_ir.json
    """
    args = sys.argv[1:]
    json_mode = "--json" in args

    try:
        ir = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"failed to read FlowIR JSON from stdin: {exc}\n")
        sys.exit(1)

    summary = lint_flow_plan_ir(ir)

    if json_mode:
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(
            f"FlowIR lint: ok={summary['ok']}, "
            f"issues={len(summary['issues'])}, warnings={len(summary['warnings'])}"
        )
        if summary["issues"]:
            print("\nIssues:")
            for msg in summary["issues"]:
                print(f"  - {msg}")
        if summary["warnings"]:
            print("\nWarnings:")
            for msg in summary["warnings"]:
                print(f"  - {msg}")


if __name__ == "__main__":
    _main()
