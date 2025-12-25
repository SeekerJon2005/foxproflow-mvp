# -*- coding: utf-8 -*-
# file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\src\parsers\__init__.py
"""
FoxProFlow — src.parsers (aggregator, NDC-safe)

Назначение
----------
Единая точка входа к существующим парсерам:
- Парсер грузов (loads.ati.su):   src.parsers.ati_parser
- Парсер транспорта (trucks.ati): src.parsers.ati_cars_parser

Мы не дублируем логику, а лениво проксируем вызовы к фактическим модулям.
Если модуль или функция отсутствуют, выдаём понятную ошибку.

Экспортируемые «канонические» точки входа:
- loads_cli(*args, **kwargs)                 → ati_parser.main(...)
- loads_parse_all_regions(*args, **kwargs)   → ati_parser.parse_all_regions(...)
- loads_setup_region_filters(*args, **kwargs)→ ati_parser.setup_all_region_filters(...)

- trucks_cli(*args, **kwargs)                → ati_cars_parser.main(...)
- trucks_authorize(*args, **kwargs)          → ati_cars_parser.scenario_authorize(...)
- trucks_save_filter(*args, **kwargs)        → ati_cars_parser.scenario_save_filter(...)
- trucks_parse_saved_filter(*args, **kwargs) → ati_cars_parser.scenario_parse_saved_filter(...)
- trucks_parse_regions(*args, **kwargs)      → ati_cars_parser.scenario_autoparse_regions(...)
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "loads_cli",
    "loads_parse_all_regions",
    "loads_setup_region_filters",
    "trucks_cli",
    "trucks_authorize",
    "trucks_save_filter",
    "trucks_parse_saved_filter",
    "trucks_parse_regions",
]


# ─────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────

def _import(modname: str):
    """
    Lazy relative import: _import("ati_parser") → import src.parsers.ati_parser
    """
    try:
        return importlib.import_module(f".{modname}", __package__)
    except Exception as e:
        raise RuntimeError(f"Required parser module '{modname}' not found or failed to import: {e}") from e


def _call(modname: str, func: str, *args: Any, **kwargs: Any) -> Any:
    """
    Call a function by name from a lazily imported module with clear errors.
    """
    mod = _import(modname)
    fn = getattr(mod, func, None)
    if fn is None:
        raise NotImplementedError(f"Function '{func}' not found in module '{modname}'.")
    return fn(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────
# Loads (ati_parser.py)
# ─────────────────────────────────────────────────────────────────────

def loads_cli(*args: Any, **kwargs: Any) -> Any:
    """CLI entry for loads parser → ati_parser.main(...)"""
    return _call("ati_parser", "main", *args, **kwargs)


def loads_parse_all_regions(*args: Any, **kwargs: Any) -> Any:
    """Bulk parse all regions for loads → ati_parser.parse_all_regions(...)"""
    return _call("ati_parser", "parse_all_regions", *args, **kwargs)


def loads_setup_region_filters(*args: Any, **kwargs: Any) -> Any:
    """Configure saved filters for loads → ati_parser.setup_all_region_filters(...)"""
    return _call("ati_parser", "setup_all_region_filters", *args, **kwargs)


# ─────────────────────────────────────────────────────────────────────
# Trucks (ati_cars_parser.py)
# ─────────────────────────────────────────────────────────────────────

def trucks_cli(*args: Any, **kwargs: Any) -> Any:
    """CLI entry for trucks parser → ati_cars_parser.main(...)"""
    return _call("ati_cars_parser", "main", *args, **kwargs)


def trucks_authorize(*args: Any, **kwargs: Any) -> Any:
    """Auth flow for trucks parser → ati_cars_parser.scenario_authorize(...)"""
    return _call("ati_cars_parser", "scenario_authorize", *args, **kwargs)


def trucks_save_filter(*args: Any, **kwargs: Any) -> Any:
    """Save filter in trucks parser → ati_cars_parser.scenario_save_filter(...)"""
    return _call("ati_cars_parser", "scenario_save_filter", *args, **kwargs)


def trucks_parse_saved_filter(*args: Any, **kwargs: Any) -> Any:
    """Parse using saved filter → ati_cars_parser.scenario_parse_saved_filter(...)"""
    return _call("ati_cars_parser", "scenario_parse_saved_filter", *args, **kwargs)


def trucks_parse_regions(*args: Any, **kwargs: Any) -> Any:
    """Auto-parse by regions → ati_cars_parser.scenario_autoparse_regions(...)"""
    return _call("ati_cars_parser", "scenario_autoparse_regions", *args, **kwargs)


# Optional: allow running from CLI for quick smoke-tests
if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(prog="src.parsers", description="FoxProFlow parsers (aggregator)")
    ap.add_argument("--role", choices=[
        "loads-cli", "loads-all", "loads-setup",
        "trucks-cli", "trucks-auth", "trucks-save-filter",
        "trucks-parse-saved", "trucks-parse-regions"
    ], required=True)
    ap.add_argument("rest", nargs="*")
    ns = ap.parse_args()

    dispatch = {
        "loads-cli":           lambda r: loads_cli(*r),
        "loads-all":           lambda r: loads_parse_all_regions(*r),
        "loads-setup":         lambda r: loads_setup_region_filters(*r),
        "trucks-cli":          lambda r: trucks_cli(*r),
        "trucks-auth":         lambda r: trucks_authorize(*r),
        "trucks-save-filter":  lambda r: trucks_save_filter(*r),
        "trucks-parse-saved":  lambda r: trucks_parse_saved_filter(*r),
        "trucks-parse-regions":lambda r: trucks_parse_regions(*r),
    }
    try:
        res = dispatch[ns.role](ns.rest)
        try:
            print(json.dumps(res, ensure_ascii=False))
        except Exception:
            print(str(res))
    except Exception as e:
        print(f"ERROR: {e}")
        raise
