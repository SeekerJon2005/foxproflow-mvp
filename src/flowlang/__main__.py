# -*- coding: utf-8 -*-
"""
CLI-обёртка для FlowLang.

Варианты использования:

  1) Запуск плана автоплана через API:

        python -m src.flowlang flowplans/autoplan_msk.flow

  2) Только парсинг (без вызова API):

        python -m src.flowlang flowplans/autoplan_msk.flow --only-parse

  3) Вывод результата в JSON-формате (для скриптов):

        python -m src.flowlang flowplans/autoplan_msk.flow --json

На v0 CLI управляет только тем, запускать ли HTTP-вызов, и форматом вывода.
Сам план (limit/dry и т.п.) задаётся в .flow-файле.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from .parser import parse_plan
from .runtime_autoplan import run_autoplan_from_flow


def _print_human(obj: Any) -> None:
    """Человеческий вывод словаря/объекта."""
    if isinstance(obj, dict):
        # Лёгкий pretty-print для словаря
        for k, v in obj.items():
            print(f"{k}: {v}")
    else:
        print(obj)


def _print_json(obj: Any) -> None:
    """JSON-вывод (машиночитаемый)."""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="FlowLang CLI: запуск планов автоплана FoxProFlow"
    )
    ap.add_argument(
        "plan_path",
        help="Путь до .flow файла (например, flowplans/autoplan_msk.flow)",
    )
    ap.add_argument(
        "--only-parse",
        action="store_true",
        help="Только разобрать .flow и вывести конфиг, без вызова API",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Выводить результат в JSON-формате",
    )

    args = ap.parse_args(argv)

    # 1) Только парсинг (без HTTP)
    if args.only_parse:
        plan_cfg = parse_plan(args.plan_path)
        payload: Dict[str, Any] = {
            "ok": True,
            "mode": "parse_only",
            "plan": plan_cfg.name,
            "config": {
                "region": plan_cfg.region,
                "limit": plan_cfg.limit,
                "window_minutes": plan_cfg.window_minutes,
                "confirm_horizon_hours": plan_cfg.confirm_horizon_hours,
                "freeze_hours_before": plan_cfg.freeze_hours_before,
                "rpm_floor_min": plan_cfg.rpm_floor_min,
                "p_arrive_min": plan_cfg.p_arrive_min,
                "dry": plan_cfg.dry,
                "chain_every_min": plan_cfg.chain_every_min,
            },
        }
        if args.json:
            _print_json(payload)
        else:
            print("FlowLang → parse result:")
            _print_human(payload)
        return

    # 2) Полный запуск плана через API
    result = run_autoplan_from_flow(args.plan_path)

    if args.json:
        _print_json(result)
    else:
        print("FlowLang → Autoplan result:")
        _print_human(result)

    # если хотим, можем возвращать ненулевой код при ok=False
    if isinstance(result, dict) and not result.get("ok", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
