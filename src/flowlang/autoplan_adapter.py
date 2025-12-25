# -*- coding: utf-8 -*-
"""
FlowLang → Autoplan adapter

Назначение:
    Собрать все параметры автоплана в одну typed-структуру AutoplanSettings,
    комбинируя значения из:
        1) FlowLang-плана (cfg.params от load_plan),
        2) профиля-плана *.flow (flowplans\*.flow / flow_plans\*.flow),
        3) .env-переменных,
        4) жёстких дефолтов в коде.

Приоритет источников внутри get_autoplan_settings:
    1) FlowLang-план / *.flow (если есть и значение указано);
    2) .env;
    3) жёсткий дефолт в коде (на основе текущего боевого профиля).

Использование:

    from src.flowlang.autoplan_adapter import get_autoplan_settings

    settings = get_autoplan_settings("rolling_msk")
    print(settings.rpm_min, settings.p_arrive_min_confirm)

Плюс:
    settings = get_autoplan_settings("msk_day")
    settings = get_autoplan_settings("longhaul_night")

если существуют соответствующие *.flow-профили.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Пытаемся использовать FlowLang plans; если его нет — работаем без него (ENV + *.flow).
try:  # pragma: no cover - защитный слой
    from .plans import load_plan, PlanConfig  # type: ignore
except Exception:  # noqa: BLE001
    load_plan = None  # type: ignore[assignment]
    PlanConfig = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Dataclass настроек автоплана
# ---------------------------------------------------------------------------


@dataclass
class AutoplanSettings:
    # Источники данных
    freights_relation: str
    availability_relation: str
    freights_days_back: int

    # Окна и тайминги
    apply_window_min: int
    confirm_window_min: int
    confirm_horizon_h: int
    freeze_before_h: int
    load_duration_h: int
    unload_duration_h: int
    avg_speed_kmh: int
    service_overhead_min: int

    # Экономика и метрика
    rpm_min: int
    confirm_rpm_min: int
    rph_min: int
    scoring_metric: str

    # Вероятности доезда
    p_arrive_min_audit: float
    p_arrive_min_confirm: float

    # Динамический RPM
    use_dynamic_rpm: bool
    dynamic_rpm_quantile: str
    dynamic_rpm_floor_min: int

    # Маршрутизация
    routing_enabled: bool
    routing_backend: str
    intracity_km_fallback: int
    intracity_speed_kmh: int

    # География плана
    region_include: List[str]
    region_exclude: List[str]

    # Лимиты/квоты
    topk_per_vehicle: int
    phase_limit: int
    freights_batch_limit: int

    # Chain/Beat-слот
    chain_every_minutes: int
    chain_limit: int
    chain_queue: str
    chain_task: str
    chain_slot_id: str
    write_audit: bool
    pipeline_summary_enabled: bool

    # Режим безопасности
    smoke_mode: bool
    hardening_enabled: bool

    # Дополнительные флаги цепочки (из *.flow-профиля)
    # Порядок и дефолты подобраны так, чтобы не ломать старые вызовы.
    chain_enable_audit: bool = True
    chain_enable_apply: bool = True
    chain_enable_confirm: bool = True
    chain_dry_run_only: bool = False


# ---------------------------------------------------------------------------
# Helpers: ENV
# ---------------------------------------------------------------------------


def _env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except Exception as e:  # pragma: no cover
        log.warning(
            "autoplan_adapter: invalid int for %s=%r (err=%r), using default=%s",
            name,
            v,
            e,
            default,
        )
        return default


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except Exception as e:  # pragma: no cover
        log.warning(
            "autoplan_adapter: invalid float for %s=%r (err=%r), using default=%s",
            name,
            v,
            e,
            default,
        )
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    s = v.strip().lower()
    if s in ("1", "true", "yes", "on", "y", "t"):
        return True
    if s in ("0", "false", "no", "off", "n", "f"):
        return False
    log.warning(
        "autoplan_adapter: invalid bool for %s=%r, using default=%s",
        name,
        v,
        default,
    )
    return default


# ---------------------------------------------------------------------------
# Helpers: чтение и парсинг *.flow-профилей (msk_day.flow, longhaul_night.flow и т.п.)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FLOW_PROFILE_DIRS: List[Path] = [
    _PROJECT_ROOT / "flowplans",
    _PROJECT_ROOT / "flow_plans",
]


def _parse_scalar(value: str) -> Any:
    """
    Очень простой парсер скаляров из *.flow:

    - true/false → bool
    - целые числа → int
    - числа с точкой/запятой → float
    - строки в кавычках → строка без кавычек
    - остальное → исходная строка (обрезанная)
    """
    v = value.strip()
    if not v:
        return v

    lower = v.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False

    try:
        return int(v)
    except Exception:
        pass

    try:
        return float(v.replace(",", "."))
    except Exception:
        pass

    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]

    return v


def _find_flow_profile(plan_name: str) -> Optional[Path]:
    """
    Ищем файл {plan_name}.flow в известных директориях:
    - flowplans\
    - flow_plans\
    """
    for d in _FLOW_PROFILE_DIRS:
        path = d / f"{plan_name}.flow"
        if path.is_file():
            return path
    return None


def _load_flow_profile_sections(plan_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Парсим очень простой DSL профиля:

        plan msk_day {
          meta {
            ...
          }

          window {
            freights_days_back: 2
            apply_window_min: 60
          }

          economics {
            rpm_min: 30.0
            ...
          }

          sla { ... }
          chain { ... }
        }

    Возвращаем dict вида:
        {
          "meta": {...},
          "window": {...},
          "economics": {...},
          "sla": {...},
          "chain": {...},
        }

    При любой ошибке возвращаем {}.
    """
    path = _find_flow_profile(plan_name)
    if path is None:
        return {}

    sections: Dict[str, Dict[str, Any]] = {}
    current: Optional[str] = None

    try:
        with path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()

                # срезаем комментарии
                if "#" in line:
                    line = line.split("#", 1)[0].strip()

                if not line:
                    continue

                # заголовок плана: plan msk_day {
                if line.startswith("plan "):
                    # имя плана можно проверить, но пока не строго
                    continue

                # секция: window {, economics {, sla {, chain {, meta {
                if line.endswith("{"):
                    sec_name = line[:-1].strip()
                    if sec_name:
                        sections[sec_name] = {}
                        current = sec_name
                    continue

                # закрытие секции или плана
                if line == "}":
                    current = None
                    continue

                # пара key: value внутри секции
                if ":" in line and current is not None:
                    key, raw_value = line.split(":", 1)
                    key = key.strip()
                    if not key:
                        continue
                    sections[current][key] = _parse_scalar(raw_value)
    except Exception as e:  # pragma: no cover
        log.warning(
            "autoplan_adapter: failed to parse flow profile %r at %s: %r",
            plan_name,
            path,
            e,
        )
        return {}

    return sections


def _flow_profile_sections_to_params(plan_name: str) -> Dict[str, Any]:
    """
    Конвертируем секции профиля *.flow в плоский dict params,
    совместимый с логикой get_autoplan_settings/_plan_*.

    Правила маппинга:

      window:
        freights_days_back   → freights_days_back
        apply_window_min     → apply_window_minutes
        confirm_window_min   → confirm_window_minutes
        horizon_hours        → confirm_horizon_hours

      economics:
        rpm_min              → rpm_min
        rph_min              → rph_min
        min_profit_per_trip  → min_profit_per_trip (пока только в params, не в dataclass)
        allow_negative_margin→ allow_negative_margin

      sla:
        p_arrive_min_normal   → p_arrive_min_audit
        p_arrive_min_critical → p_arrive_min_confirm
        max_lateness_min      → max_lateness_min

      chain:
        dry_run_only          → smoke_mode + chain_dry_run_only
        enable_audit          → chain_enable_audit (+ по умолчанию write_audit)
        enable_apply          → chain_enable_apply
        enable_confirm        → chain_enable_confirm
    """
    sections = _load_flow_profile_sections(plan_name)
    if not sections:
        return {}

    params: Dict[str, Any] = {}

    window = sections.get("window", {})
    if "freights_days_back" in window:
        params["freights_days_back"] = window["freights_days_back"]
    if "apply_window_min" in window:
        params["apply_window_minutes"] = window["apply_window_min"]
    if "confirm_window_min" in window:
        params["confirm_window_minutes"] = window["confirm_window_min"]
    if "horizon_hours" in window:
        params["confirm_horizon_hours"] = window["horizon_hours"]

    econ = sections.get("economics", {})
    if "rpm_min" in econ:
        params["rpm_min"] = econ["rpm_min"]
    if "rph_min" in econ:
        params["rph_min"] = econ["rph_min"]
    if "min_profit_per_trip" in econ:
        params["min_profit_per_trip"] = econ["min_profit_per_trip"]
    if "allow_negative_margin" in econ:
        params["allow_negative_margin"] = econ["allow_negative_margin"]

    sla = sections.get("sla", {})
    if "p_arrive_min_normal" in sla:
        params["p_arrive_min_audit"] = sla["p_arrive_min_normal"]
    if "p_arrive_min_critical" in sla:
        params["p_arrive_min_confirm"] = sla["p_arrive_min_critical"]
    if "max_lateness_min" in sla:
        params["max_lateness_min"] = sla["max_lateness_min"]

    chain = sections.get("chain", {})
    if "dry_run_only" in chain:
        params["smoke_mode"] = chain["dry_run_only"]
        params["chain_dry_run_only"] = chain["dry_run_only"]
    if "enable_audit" in chain:
        params["chain_enable_audit"] = chain["enable_audit"]
        # если явно не задан write_audit, синхронизируем его с enable_audit
        params.setdefault("write_audit", chain["enable_audit"])
    if "enable_apply" in chain:
        params["chain_enable_apply"] = chain["enable_apply"]
    if "enable_confirm" in chain:
        params["chain_enable_confirm"] = chain["enable_confirm"]

    return params


# ---------------------------------------------------------------------------
# Helpers: чтение FlowLang-плана (cfg.params) + overlay *.flow-профиля
# ---------------------------------------------------------------------------


def _load_plan_params(plan_name: Optional[str]) -> Dict[str, Any]:
    """
    Загружаем параметры плана FlowLang (cfg.params), а затем поверх
    накладываем профиль из *.flow (если он есть).

    Если ничего не найдено — возвращаем {}.
    """
    params: Dict[str, Any] = {}

    # 1) FlowLang-план (если доступен)
    if plan_name and load_plan is not None:
        try:
            cfg = load_plan(plan_name)  # type: ignore[operator]
        except FileNotFoundError:
            log.warning(
                "autoplan_adapter: FlowLang plan %r not found, will try *.flow + ENV-only config",
                plan_name,
            )
        except Exception as e:  # pragma: no cover
            log.warning(
                "autoplan_adapter: failed to load FlowLang plan %r: %r, will try *.flow + ENV-only config",
                plan_name,
                e,
            )
        else:
            raw_params = getattr(cfg, "params", None) or {}
            if not isinstance(raw_params, dict):
                log.warning(
                    "autoplan_adapter: unexpected params type for plan %r: %r",
                    plan_name,
                    type(raw_params),
                )
            else:
                params = dict(raw_params)

    # 2) Профиль *.flow (msk_day.flow / longhaul_night.flow и т.п.)
    if plan_name:
        try:
            flow_params = _flow_profile_sections_to_params(plan_name)
        except Exception as e:  # pragma: no cover
            log.warning(
                "autoplan_adapter: failed to overlay flow profile for plan %r: %r",
                plan_name,
                e,
            )
        else:
            # Значения из *.flow имеют приоритет над cfg.params,
            # т.к. это явная профилировка под конкретный план.
            params.update(flow_params)

    return params


def _plan_int(
    params: Dict[str, Any],
    key: str,
    env_name: Optional[str],
    default: int,
) -> int:
    base = _env_int(env_name, default) if env_name else default
    if key in params and params[key] is not None:
        try:
            return int(params[key])
        except Exception as e:  # pragma: no cover
            log.warning(
                "autoplan_adapter: invalid int for plan key=%s value=%r (err=%r), using=%s",
                key,
                params[key],
                e,
                base,
            )
    return base


def _plan_float(
    params: Dict[str, Any],
    key: str,
    env_name: Optional[str],
    default: float,
) -> float:
    base = _env_float(env_name, default) if env_name else default
    if key in params and params[key] is not None:
        try:
            return float(params[key])
        except Exception as e:  # pragma: no cover
            log.warning(
                "autoplan_adapter: invalid float for plan key=%s value=%r (err=%r), using=%s",
                key,
                params[key],
                e,
                base,
            )
    return base


def _coerce_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "on", "y", "t"):
            return True
        if s in ("0", "false", "no", "off", "n", "f"):
            return False
    return None


def _plan_bool(
    params: Dict[str, Any],
    key: str,
    env_name: Optional[str],
    default: bool,
) -> bool:
    base = _env_bool(env_name, default) if env_name else default
    if key in params and params[key] is not None:
        coerced = _coerce_bool(params[key])
        if coerced is not None:
            return coerced
        log.warning(
            "autoplan_adapter: invalid bool for plan key=%s value=%r, using=%s",
            key,
            params[key],
            base,
        )
    return base


def _plan_str(
    params: Dict[str, Any],
    key: str,
    env_name: Optional[str],
    default: str,
) -> str:
    base = _env_str(env_name, default) if env_name else default
    if key in params and params[key] is not None:
        return str(params[key])
    return base


def _plan_str_list(params: Dict[str, Any], key: str, default: List[str]) -> List[str]:
    v = params.get(key)
    if v is None:
        return list(default)
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    # одиночное значение — превращаем в список
    return [str(v)]


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def get_autoplan_settings(plan_name: str = "rolling_msk") -> AutoplanSettings:
    """
    Собирает AutoplanSettings, используя:

        - FlowLang-план (cfg.params),
        - профиль из *.flow (если есть),
        - ENV-переменные,
        - жёсткие дефолты.

    plan_name:
        имя плана без расширения (.flow).
        По умолчанию "rolling_msk".

    Если план не найден или не читается — используется комбинация *.flow + ENV.
    """
    params = _load_plan_params(plan_name)

    # --- Источники данных ---
    freights_relation = _plan_str(
        params,
        "freights_relation",
        "FE_RELATION",
        "public.freights_enriched_mv",
    )
    availability_relation = _plan_str(
        params,
        "availability_relation",
        "AVAILABILITY_REL",
        "public.vehicle_availability_mv",
    )
    freights_days_back = _plan_int(
        params,
        "freights_days_back",
        "AUTOPLAN_FREIGHTS_DAYS_BACK",
        3,
    )

    # --- Окна и тайминги ---
    apply_window_min = _plan_int(
        params,
        "apply_window_minutes",
        "AUTOPLAN_APPLY_WINDOW_MIN",
        240,
    )
    confirm_window_min = _plan_int(
        params,
        "confirm_window_minutes",
        "AUTOPLAN_CONFIRM_WINDOW_MIN",
        240,
    )
    confirm_horizon_h = _plan_int(
        params,
        "confirm_horizon_hours",
        "CONFIRM_HORIZON_H",
        96,
    )
    freeze_before_h = _plan_int(
        params,
        "freeze_before_hours",
        "CONFIRM_FREEZE_H_BEFORE",
        2,
    )
    load_duration_h = _plan_int(
        params,
        "load_duration_hours",
        "LOAD_DURATION_H",
        4,
    )
    unload_duration_h = _plan_int(
        params,
        "unload_duration_hours",
        "UNLOAD_DURATION_H",
        4,
    )
    avg_speed_kmh = _plan_int(
        params,
        "avg_speed_kmh",
        "AUTOPLAN_AVG_SPEED_KMH",
        55,
    )
    service_overhead_min = _plan_int(
        params,
        "service_overhead_min",
        "AUTOPLAN_SERVICE_OVERHEAD_MIN",
        45,
    )

    # --- Экономика и метрика ---
    rpm_min = _plan_int(
        params,
        "rpm_min",
        "AUTOPLAN_RPM_MIN",
        90,
    )
    confirm_rpm_min = _plan_int(
        params,
        "confirm_rpm_min",
        "CONFIRM_RPM_MIN",
        90,
    )
    rph_min = _plan_int(
        params,
        "rph_min",
        "AUTOPLAN_RPH_MIN",
        2000,
    )
    scoring_metric = _plan_str(
        params,
        "scoring_metric",
        "AUTOPLAN_SCORING_METRIC",
        "rph",
    )

    # --- Вероятности доезда ---
    p_arrive_min_audit = _plan_float(
        params,
        "p_arrive_min_audit",
        "AUTOPLAN_P_ARRIVE_MIN_AUDIT",
        0.40,
    )
    p_arrive_min_confirm = _plan_float(
        params,
        "p_arrive_min_confirm",
        "AUTOPLAN_P_ARRIVE_MIN",
        0.40,
    )

    # --- Динамический RPM ---
    use_dynamic_rpm = _plan_bool(
        params,
        "use_dynamic_rpm",
        "USE_DYNAMIC_RPM",
        True,
    )
    dynamic_rpm_quantile = _plan_str(
        params,
        "dynamic_rpm_quantile",
        "DYNAMIC_RPM_QUANTILE",
        "p25",
    )
    dynamic_rpm_floor_min = _plan_int(
        params,
        "dynamic_rpm_floor_min",
        "DYNAMIC_RPM_FLOOR_MIN",
        110,
    )

    # --- Маршрутизация ---
    routing_enabled = _plan_bool(
        params,
        "routing_enabled",
        "ROUTING_ENABLED",
        True,
    )
    routing_backend = _plan_str(
        params,
        "routing_backend",
        "ROUTING_BACKEND",
        "osrm",
    )
    intracity_km_fallback = _plan_int(
        params,
        "intracity_km_fallback",
        "INTRACITY_FALLBACK_KM",
        50,
    )
    intracity_speed_kmh = _plan_int(
        params,
        "intracity_speed_kmh",
        "INTRACITY_SPEED_KMH",
        35,
    )

    # --- География плана ---
    region_include = _plan_str_list(params, "region_include", [])
    region_exclude = _plan_str_list(params, "region_exclude", [])

    # --- Лимиты/квоты ---
    topk_per_vehicle = _plan_int(
        params,
        "topk_per_vehicle",
        "AUTOPLAN_TOPK",
        5,
    )
    phase_limit = _plan_int(
        params,
        "phase_limit",
        "AUTOPLAN_PHASE_LIMIT",
        200,
    )
    freights_batch_limit = _plan_int(
        params,
        "freights_batch_limit",
        "ATI_ETL_LIMIT_DEFAULT",
        500,
    )

    # --- Chain / Beat-слот ---
    chain_every_minutes = _plan_int(
        params,
        "chain_every_minutes",
        "AUTOPLAN_CHAIN_EVERY_MIN",
        15,
    )
    chain_limit = _plan_int(
        params,
        "chain_limit",
        "AUTOPLAN_CHAIN_LIMIT",
        50,
    )
    chain_queue = _plan_str(
        params,
        "chain_queue",
        "AUTOPLAN_CHAIN_QUEUE",
        "autoplan",
    )
    chain_task = _plan_str(
        params,
        "chain_task",
        "AUTOPLAN_CHAIN_TASK",
        "task_autoplan_chain",
    )
    chain_slot_id = _plan_str(
        params,
        "chain_slot_id",
        "AUTOPLAN_CHAIN_ID",
        "autoplan-chain-15m",
    )
    write_audit = _plan_bool(
        params,
        "write_audit",
        "AUTOPLAN_CHAIN_WRITE_AUDIT",
        True,
    )
    pipeline_summary_enabled = _plan_bool(
        params,
        "pipeline_summary_enabled",
        "FF_ENABLE_PIPELINE_SUMMARY",
        True,
    )

    # --- Режим безопасности ---
    smoke_mode = _plan_bool(
        params,
        "smoke_mode",
        "AUTOPLAN_SMOKE_MODE",
        False,
    )
    hardening_enabled = _plan_bool(
        params,
        "hardening_enabled",
        "ENABLE_AUTOPLAN_HARDENING",
        False,
    )

    # --- Дополнительные флаги цепочки (из *.flow, без ENV) ---
    chain_enable_audit = _plan_bool(
        params,
        "chain_enable_audit",
        None,
        True,
    )
    chain_enable_apply = _plan_bool(
        params,
        "chain_enable_apply",
        None,
        True,
    )
    chain_enable_confirm = _plan_bool(
        params,
        "chain_enable_confirm",
        None,
        True,
    )
    chain_dry_run_only = _plan_bool(
        params,
        "chain_dry_run_only",
        None,
        False,
    )

    return AutoplanSettings(
        freights_relation=freights_relation,
        availability_relation=availability_relation,
        freights_days_back=freights_days_back,
        apply_window_min=apply_window_min,
        confirm_window_min=confirm_window_min,
        confirm_horizon_h=confirm_horizon_h,
        freeze_before_h=freeze_before_h,
        load_duration_h=load_duration_h,
        unload_duration_h=unload_duration_h,
        avg_speed_kmh=avg_speed_kmh,
        service_overhead_min=service_overhead_min,
        rpm_min=rpm_min,
        confirm_rpm_min=confirm_rpm_min,
        rph_min=rph_min,
        scoring_metric=scoring_metric,
        p_arrive_min_audit=p_arrive_min_audit,
        p_arrive_min_confirm=p_arrive_min_confirm,
        use_dynamic_rpm=use_dynamic_rpm,
        dynamic_rpm_quantile=dynamic_rpm_quantile,
        dynamic_rpm_floor_min=dynamic_rpm_floor_min,
        routing_enabled=routing_enabled,
        routing_backend=routing_backend,
        intracity_km_fallback=intracity_km_fallback,
        intracity_speed_kmh=intracity_speed_kmh,
        region_include=region_include,
        region_exclude=region_exclude,
        topk_per_vehicle=topk_per_vehicle,
        phase_limit=phase_limit,
        freights_batch_limit=freights_batch_limit,
        chain_every_minutes=chain_every_minutes,
        chain_limit=chain_limit,
        chain_queue=chain_queue,
        chain_task=chain_task,
        chain_slot_id=chain_slot_id,
        write_audit=write_audit,
        pipeline_summary_enabled=pipeline_summary_enabled,
        smoke_mode=smoke_mode,
        hardening_enabled=hardening_enabled,
        chain_enable_audit=chain_enable_audit,
        chain_enable_apply=chain_enable_apply,
        chain_enable_confirm=chain_enable_confirm,
        chain_dry_run_only=chain_dry_run_only,
    )


__all__ = ["AutoplanSettings", "get_autoplan_settings"]
