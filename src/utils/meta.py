# -*- coding: utf-8 -*-
# file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\src\utils\meta.py
"""
FoxProFlow — utils.meta (NDC-safe helpers)

Хелперы для безопасной работы со словарём meta и пространством meta.autoplan.*.

Цели:
- Удобно читать/писать вложенные ключи через строковые пути ("autoplan.road_km").
- Безопасно проставлять значения в meta.autoplan без перетирания чужих полей.
- Нормализовать коды регионов, проставлять координаты и вычислять производные
  метрики (drive_hours_est, rph) из km/сек/цены.

Все функции *аддитивны* и не трогают внешние ресурсы.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping, Optional, Sequence


# ─────────────────────────────────────────────────────────────────────
# Вспомогательные утилиты
# ─────────────────────────────────────────────────────────────────────

def _split(path: str) -> list[str]:
    """Разбивает dotted-путь 'a.b.c' в список ['a','b','c']."""
    return [p for p in (path or "").strip().split(".") if p]


def _ensure_dict(target: MutableMapping[str, Any], key: str) -> MutableMapping[str, Any]:
    """Гарантирует, что target[key] — dict; при необходимости создаёт."""
    node = target.get(key)
    if not isinstance(node, dict):
        node = {}
        target[key] = node
    return node


def meta_get(meta: Mapping[str, Any], path: str, default: Any = None) -> Any:
    """
    Возвращает значение по dotted-пути из meta или default, если ключей нет.

        meta_get({"a": {"b": 1}}, "a.b") -> 1
        meta_get(..., "a.b.c", default=None) -> None
    """
    cur: Any = meta
    for key in _split(path):
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def meta_set(meta: MutableMapping[str, Any], path: str, value: Any, *, create: bool = True) -> MutableMapping[str, Any]:
    """
    Устанавливает значение по dotted-пути. При create=False не создаёт промежуточные словари.
    Возвращает исходный meta (для чейнинга).

        meta_set(m, "a.b.c", 42)
    """
    parts = _split(path)
    if not parts:
        return meta
    cur: MutableMapping[str, Any] = meta
    for k in parts[:-1]:
        if k not in cur:
            if not create:
                return meta
            cur[k] = {}
        elif not isinstance(cur[k], dict):
            if not create:
                return meta
            cur[k] = {}
        cur = cur[k]  # type: ignore[assignment]
    cur[parts[-1]] = value
    return meta


def meta_del(meta: MutableMapping[str, Any], path: str) -> bool:
    """
    Удаляет ключ по dotted-пути. Возвращает True если удаление произошло.
    """
    parts = _split(path)
    if not parts:
        return False
    cur: Any = meta
    for k in parts[:-1]:
        if not isinstance(cur, Mapping) or k not in cur:
            return False
        cur = cur[k]
    if isinstance(cur, MutableMapping) and parts[-1] in cur:
        del cur[parts[-1]]
        return True
    return False


# ─────────────────────────────────────────────────────────────────────
# Работа с meta.autoplan
# ─────────────────────────────────────────────────────────────────────

def ensure_autoplan(meta: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Гарантирует наличие словаря meta['autoplan'] и возвращает исходный meta."""
    _ensure_dict(meta, "autoplan")
    return meta


def set_autoplan_values(meta: MutableMapping[str, Any], **kwargs: Any) -> MutableMapping[str, Any]:
    """
    Массовая установка значений в meta.autoplan.* без перетирания других полей.

        set_autoplan_values(meta, road_km=397.0, drive_sec=25990, rph=3200)
    """
    ap = _ensure_dict(meta, "autoplan")
    for k, v in kwargs.items():
        ap[k] = v
    return meta


def normalize_region(code: Optional[str]) -> Optional[str]:
    """
    Приводит код региона к каноничному строковому виду: trim + upper.
    Пустые строки → None.
    """
    if code is None:
        return None
    s = str(code).strip().upper()
    return s or None


def set_regions(
    meta: MutableMapping[str, Any],
    *,
    origin_region: Optional[str] = None,
    dest_region: Optional[str] = None,
    normalize: bool = True,
) -> MutableMapping[str, Any]:
    """
    Проставляет meta.autoplan.origin_region / dest_region.
    Если normalize=True — применяет normalize_region().
    """
    ap = _ensure_dict(meta, "autoplan")
    if origin_region is not None:
        ap["origin_region"] = normalize_region(origin_region) if normalize else origin_region
    if dest_region is not None:
        ap["dest_region"] = normalize_region(dest_region) if normalize else dest_region
    return meta


def _to_number(val: Any) -> Optional[float]:
    """Мягкая попытка перевести в float; при провале возвращает None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).strip())
    except Exception:
        return None


def set_coords(
    meta: MutableMapping[str, Any],
    *,
    from_lat: Any = None,
    from_lon: Any = None,
    to_lat: Any = None,
    to_lon: Any = None,
    mirror_origin_dest: bool = True,
) -> MutableMapping[str, Any]:
    """
    Проставляет координаты отправления/назначения в meta.autoplan.*.
    Хранит и дубли ('from_*' и 'origin_*', 'to_*' и 'dest_*'), чтобы не ломать
    потребителей с разными схемами.

        set_coords(meta, from_lat=55.75, from_lon=37.62, to_lat=59.93, to_lon=30.31)
    """
    ap = _ensure_dict(meta, "autoplan")

    flt = _to_number(from_lat)
    fln = _to_number(from_lon)
    tlt = _to_number(to_lat)
    tln = _to_number(to_lon)

    if flt is not None:
        ap["from_lat"] = flt
        if mirror_origin_dest:
            ap["origin_lat"] = flt
    if fln is not None:
        ap["from_lon"] = fln
        if mirror_origin_dest:
            ap["origin_lon"] = fln
    if tlt is not None:
        ap["to_lat"] = tlt
        if mirror_origin_dest:
            ap["dest_lat"] = tlt
    if tln is not None:
        ap["to_lon"] = tln
        if mirror_origin_dest:
            ap["dest_lon"] = tln
    return meta


def set_km_sec(
    meta: MutableMapping[str, Any],
    *,
    road_km: Any = None,
    drive_sec: Any = None,
    polyline: Optional[str] = None,
    overwrite: bool = True,
) -> MutableMapping[str, Any]:
    """
    Проставляет meta.autoplan.road_km / drive_sec / polyline.
    Если overwrite=False — не перезаписывает уже существующие значения.
    """
    ap = _ensure_dict(meta, "autoplan")

    def _maybe_set(key: str, val: Any) -> None:
        if val is None:
            return
        if not overwrite and key in ap and ap[key] not in (None, "", 0):
            return
        ap[key] = val

    km = _to_number(road_km)
    sec = _to_number(drive_sec)
    _maybe_set("road_km", km)
    if sec is not None:
        _maybe_set("drive_sec", int(sec))
    if polyline is not None:
        _maybe_set("polyline", str(polyline))
    return meta


@dataclass
class RPHParams:
    speed_kmh: float = 55.0
    overhead_min: float = 45.0  # сервисные простои на рейс


def compute_rph(
    meta: MutableMapping[str, Any],
    *,
    price_rub: Any = None,
    rph_min: Optional[float] = None,
    params: Optional[RPHParams] = None,
    store: bool = True,
) -> Optional[float]:
    """
    Вычисляет RPH (руб/час) для рейса по meta.autoplan:
      drive_hours_est = road_km / speed_kmh + overhead_min/60
      price = price_rub (если передан) иначе meta.autoplan.price
      rph   = price / drive_hours_est

    Если store=True — пишет meta.autoplan.rph и meta.autoplan.drive_hours_est.
    Возвращает rph или None (если не получается посчитать).

    rph_min — необязательный нижний порог (если посчитанное rph < rph_min, возвращается rph как есть,
    а порог можно использовать вне функции).
    """
    ap = _ensure_dict(meta, "autoplan")
    params = params or RPHParams()

    km = _to_number(ap.get("road_km"))
    price = _to_number(price_rub if price_rub is not None else ap.get("price"))
    if km is None or km <= 0 or price is None or price <= 0:
        return None

    drive_hours = (km / max(params.speed_kmh, 1e-6)) + (params.overhead_min / 60.0)
    if drive_hours <= 0:
        return None

    rph = float(price) / float(drive_hours)
    if store:
        ap["drive_hours_est"] = drive_hours
        ap["rph"] = rph
    return rph


# ─────────────────────────────────────────────────────────────────────
# Утилиты безопасного обновления
# ─────────────────────────────────────────────────────────────────────

def set_if_absent(meta: MutableMapping[str, Any], path: str, value: Any) -> MutableMapping[str, Any]:
    """
    Устанавливает значение только если ключ отсутствует или пуст (None/'').
    """
    cur = meta_get(meta, path, None)
    if cur is None or (isinstance(cur, str) and cur == ""):
        meta_set(meta, path, value)
    return meta


def update_if_none(meta: MutableMapping[str, Any], updates: Mapping[str, Any]) -> MutableMapping[str, Any]:
    """
    Идём по словарю вида {'a.b': 1, 'x.y.z': 'v'} и ставим значения только там,
    где сейчас None/отсутствует/пустая строка.
    """
    for path, val in updates.items():
        set_if_absent(meta, path, val)
    return meta


def deep_merge(dst: MutableMapping[str, Any], src: Mapping[str, Any]) -> MutableMapping[str, Any]:
    """
    Аддитивный deep-merge: словари сливаются, скаляры из src перезаписывают dst.
    """
    for k, v in src.items():
        if isinstance(v, Mapping) and isinstance(dst.get(k), Mapping):
            deep_merge(dst[k], v)  # type: ignore[index]
        else:
            dst[k] = v  # type: ignore[index]
    return dst


# ─────────────────────────────────────────────────────────────────────
# Примеры использования (докстринг)
# ─────────────────────────────────────────────────────────────────────
__doc_examples__ = r"""
>>> m = {}
>>> ensure_autoplan(m)
{'autoplan': {}}

>>> set_regions(m, origin_region='ru-mow', dest_region=' ru-niz ')
{'autoplan': {'origin_region': 'RU-MOW', 'dest_region': 'RU-NIZ'}}

>>> set_coords(m, from_lat='55.75', from_lon=37.62, to_lat=59.93, to_lon='30.31')
{'autoplan': {'origin_region': 'RU-MOW', 'dest_region': 'RU-NIZ',
              'from_lat': 55.75, 'from_lon': 37.62,
              'origin_lat': 55.75, 'origin_lon': 37.62,
              'to_lat': 59.93, 'to_lon': 30.31,
              'dest_lat': 59.93, 'dest_lon': 30.31}}

>>> set_km_sec(m, road_km='397.06', drive_sec=25990)
>>> compute_rph(m, price_rub=52000)
~2004.0  # пример

>>> meta_get(m, 'autoplan.road_km')
397.06

>>> meta_set(m, 'autoplan.extra.flag', True)
{'autoplan': {..., 'extra': {'flag': True}}}
"""
