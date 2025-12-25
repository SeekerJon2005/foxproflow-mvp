# -*- coding: utf-8 -*-
"""
FoxProFlow: parsers + ETL tasks (ATI и прочие парсеры).

Назначение:
- Зарегистрировать задачи `parsers.*`, чтобы не было ошибок "Received unregistered task".
- Дать лёгкий, неразрушающий (NDC) способ обновлять freights_ati_raw
  из локальных JSON/JSONL-файлов или подключаемого парсера ATI.
- Реализовать базовый ETL `etl.freights.from_ati` → public.freights
  с заполнением дат погрузки/выгрузки и базовой экономики.

ENV / режимы
============

PARSERS_QUEUE="parsers"
    Очередь по умолчанию для всех парсерных задач.

ATI_PULL_MODE="stub|local_json|regions_json"
    Режим работы parser.ati.freights.pull:
      * "stub"         — ничего не делает, только логирует (по умолчанию).
      * "local_json"   — читает JSON/JSONL из каталога ATI_PULL_DIR и UPSERT'ит
                         их в freights_ati_raw.
      * "regions_json" — читает региональные JSON/JSONL из REGIONS_DATA_DIR
                         (src/parsers/regions_data) и UPSERT'ит в freights_ati_raw
                         с src='ati_html_region'.

ATI_PULL_DIR="/app/data/ati_freights"
    Каталог, откуда брать *.json / *.jsonl для режима local_json.

REGIONS_DATA_DIR="/app/src/parsers/regions_data"
    Каталог региональных дампов для режима regions_json.

ATI_ETL_LIMIT_DEFAULT=5000
    Лимит строк за один прогон etl.freights.from_ati (верхняя граница).

Структура записи для local_json/regions_json (рекомендуемая)
============================================================

    {
      "external_id": "86d63624-1d5d-4df7-91c5-e4237149c7b3",
      "src": "ati_html",                  # опционально, по умолчанию 'ati_html'
      "parsed_at": "2025-11-19T10:23:45", # ISO8601, опционально
      "payload": { ... полный JSON, который должен оказаться в freights_ati_raw.payload ... }
    }

Если поля payload нет, вся запись целиком будет использована как payload.
Если parsed_at нет или не парсится — берём текущий UTC.

Важно
=====

- Мы НИЧЕГО не удаляем из freights_ati_raw и public.freights.
- Вставка в freights_ati_raw идёт через UPSERT по (src, external_id).
- Вставка в public.freights:
    * по возможности заполняет loading_region/unloading_region и loading_date/unloading_date,
      чтобы не падать на NOT NULL;
    * иначе использует дефолты (например, loading_region/unloading_region='RU-UNK'),
      а записи без нормальной даты погрузки пропускает.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Set

from celery import shared_task

from src.core import emit_start, emit_done, emit_error
from .tasks_agents import _connect_pg

# psycopg нужны в рантайме, но делаем мягкий импорт, чтобы IDE не орала
try:  # pragma: no cover - защитный импорт
    import psycopg  # type: ignore[import]
    from psycopg.rows import dict_row  # type: ignore[import]
except Exception:  # noqa: BLE001
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.getenv("CELERY_LOG_LEVEL", "INFO"))

PARSERS_QUEUE = os.getenv("PARSERS_QUEUE", "parsers")
ATI_ETL_LIMIT_DEFAULT = int(os.getenv("ATI_ETL_LIMIT_DEFAULT", "5000"))
REGIONS_DATA_DIR = os.getenv("REGIONS_DATA_DIR", "/app/src/parsers/regions_data")


# =============================================================================
# Вспомогательные функции (время / ISO)
# =============================================================================


def _utcnow() -> datetime:
    """UTC-now с таймзоной и без микросекунд — удобно для логов и сравнений."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    """Разбираем ISO-дату, возвращаем None при любой странности."""
    if not value:
        return None
    try:
        v = value.strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        return datetime.fromisoformat(v)
    except Exception:  # noqa: BLE001
        return None


# =============================================================================
# Normalization для freights_ati_raw
# =============================================================================


def _coerce_ati_record(
    obj: Dict[str, Any],
    cutoff: Optional[datetime],
    force_src: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Приводим входной объект к стандартной записи для freights_ati_raw.

    Ожидаемый контракт freights_ati_raw:

      - src        : text
      - external_id: text
      - payload    : jsonb
      - parsed_at  : timestamptz

    Логика:
      * src — либо force_src (если задан), либо obj["src"] или "ati_html" по умолчанию.
      * external_id — из obj["external_id"] / obj["id"] / obj["uid"] / obj["ati_id"].
      * parsed_at — obj["parsed_at"] (ISO) или utcnow().
      * cutoff — если задан и parsed_at < cutoff → пропускаем запись.
      * payload — obj["payload"] или весь объект целиком.
    """
    src = force_src or str(obj.get("src") or "ati_html").strip() or "ati_html"

    external_id = (
        obj.get("external_id")
        or obj.get("id")
        or obj.get("uid")
        or obj.get("ati_id")
    )
    if not external_id:
        return None
    external_id = str(external_id).strip()
    if not external_id:
        return None

    parsed_at_dt = _parse_iso_dt(obj.get("parsed_at")) or _utcnow()
    if cutoff is not None and parsed_at_dt < cutoff:
        return None

    payload = obj.get("payload") or obj

    return {
        "src": src,
        "external_id": external_id,
        "parsed_at": parsed_at_dt,
        "payload": payload,
    }


def _iter_local_json_records(
    base_dir: str,
    cutoff: Optional[datetime],
    force_src: Optional[str] = None,
) -> Iterable[Dict[str, Any]]:
    """
    Итерируем по локальным JSON/JSONL-файлам в каталоге base_dir.

    Поддерживаем:
      * *.json  — либо одиночный объект, либо список объектов.
      * *.jsonl — по объекту в строке (одна строка = один JSON-объект).

    cutoff:
      * если None — НЕ фильтруем по времени (для исторических дампов).
      * если datetime — применяем его в _coerce_ati_record (parsed_at < cutoff → skip).

    force_src:
      * если задан, передаётся в _coerce_ati_record и жёстко задаёт src для всех записей.
    """
    base_dir = os.path.abspath(base_dir)
    logger.info(
        "parser.ati.freights.pull[local_json]: scanning dir=%s cutoff=%s",
        base_dir,
        cutoff.isoformat() + "Z" if isinstance(cutoff, datetime) else "None",
    )

    for root, _, files in os.walk(base_dir):
        for name in files:
            fname = name.lower()
            if not (fname.endswith(".json") or fname.endswith(".jsonl")):
                continue

            path = os.path.join(root, name)
            total = 0
            accepted = 0

            try:
                if fname.endswith(".jsonl"):
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            total += 1
                            try:
                                obj = json.loads(line)
                            except Exception as e:  # noqa: BLE001
                                logger.warning(
                                    "parser.ati.freights.pull[local_json]: bad JSONL line in %s: %r",
                                    path,
                                    e,
                                )
                                continue
                            if not isinstance(obj, dict):
                                logger.warning(
                                    "parser.ati.freights.pull[local_json]: non-dict JSONL in %s: %r",
                                    path,
                                    type(obj),
                                )
                                continue
                            rec = _coerce_ati_record(obj, cutoff, force_src=force_src)
                            if rec is not None:
                                accepted += 1
                                yield rec
                else:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            for obj in data:
                                if not isinstance(obj, dict):
                                    continue
                                total += 1
                                rec = _coerce_ati_record(obj, cutoff, force_src=force_src)
                                if rec is not None:
                                    accepted += 1
                                    yield rec
                        elif isinstance(data, dict):
                            total += 1
                            rec = _coerce_ati_record(data, cutoff, force_src=force_src)
                            if rec is not None:
                                accepted += 1
                                yield rec
                        else:
                            logger.warning(
                                "parser.ati.freights.pull[local_json]: unsupported JSON type in %s: %r",
                                path,
                                type(data),
                            )
            except FileNotFoundError:
                continue
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "parser.ati.freights.pull[local_json]: failed to read %s: %r",
                    path,
                    e,
                )
                continue

            logger.info(
                "parser.ati.freights.pull[local_json]: file=%s total=%s accepted=%s",
                path,
                total,
                accepted,
            )


def _upsert_freights_ati_raw(records: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """
    UPSERT в public.freights_ati_raw по (src, external_id).

    Таблица public.freights_ati_raw должна иметь как минимум поля:
      - src         text
      - external_id text
      - payload     jsonb
      - parsed_at   timestamptz

    И уникальный индекс/constraint по (src, external_id).
    """
    inserted = 0
    updated = 0

    conn = _connect_pg()
    try:
        cur = conn.cursor()
        for rec in records:
            rec_db = dict(rec)
            payload_obj = rec_db.get("payload")
            if not isinstance(payload_obj, str):
                rec_db["payload"] = json.dumps(payload_obj, ensure_ascii=False)

            cur.execute(
                """
                INSERT INTO public.freights_ati_raw (src, external_id, payload, parsed_at)
                VALUES (%(src)s, %(external_id)s, %(payload)s::jsonb, %(parsed_at)s)
                ON CONFLICT (src, external_id) DO UPDATE
                  SET payload  = EXCLUDED.payload,
                      parsed_at = EXCLUDED.parsed_at
                """,
                rec_db,
            )
            status = (cur.statusmessage or "").upper()
            if status.startswith("INSERT"):
                inserted += 1
            elif status.startswith("UPDATE"):
                updated += 1
            else:
                # fallback: считаем вставкой
                inserted += 1

        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    return {"inserted": inserted, "updated": updated}


# =============================================================================
# parsers.watchdog
# =============================================================================


@shared_task(name="parsers.watchdog")
def task_parsers_watchdog() -> Dict[str, Any]:
    """Простейший watchdog, чтобы очередь parsers не считалась «мертвой»."""
    return {"ok": True, "note": "parsers.watchdog stub"}


# =============================================================================
# parser.ati.freights.pull — загрузка фрахтов ATI/рег.дампов в freights_ati_raw
# =============================================================================


@shared_task(
    name="parser.ati.freights.pull",
    queue=PARSERS_QUEUE,
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def parser_ati_freights_pull(
    self,
    since_minutes: int = 720,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Универсальная таска-парсер по ATI/региональным дампам → public.freights_ati_raw.
    """
    cutoff = _utcnow() - timedelta(minutes=since_minutes)
    mode = (mode or os.getenv("ATI_PULL_MODE", "stub")).lower().strip() or "stub"

    logger.info(
        "parser.ati.freights.pull: start mode=%s since_minutes=%s cutoff_utc=%s",
        mode,
        since_minutes,
        cutoff.isoformat() + "Z",
    )

    if mode == "stub":
        return {
            "ok": True,
            "mode": "stub",
            "note": "parser.ati.freights.pull: stub mode (no data collected)",
            "since_minutes": since_minutes,
            "cutoff_utc": cutoff.isoformat() + "Z",
        }

    if mode == "local_json":
        base_dir = os.getenv("ATI_PULL_DIR", "/app/data/ati_freights")
        records = list(_iter_local_json_records(base_dir, cutoff=None, force_src=None))
        stats = _upsert_freights_ati_raw(records)
        payload: Dict[str, Any] = {
            "ok": True,
            "mode": mode,
            "dir": base_dir,
            "since_minutes": since_minutes,
            "cutoff_utc": cutoff.isoformat() + "Z",
            "inserted": stats["inserted"],
            "updated": stats["updated"],
            "total_processed": len(records),
        }
        logger.info(
            "parser.ati.freights.pull[local_json]: inserted=%s updated=%s total=%s dir=%s",
            stats["inserted"],
            stats["updated"],
            len(records),
            base_dir,
        )
        if not records:
            logger.warning(
                "parser.ati.freights.pull[local_json]: no records found (dir=%s, cutoff ignored)",
                base_dir,
            )
        return payload

    if mode == "regions_json":
        base_dir = REGIONS_DATA_DIR
        records = list(
            _iter_local_json_records(
                base_dir,
                cutoff=None,          # исторические дампы — cutoff не режем
                force_src="ati_html_region",
            )
        )
        stats = _upsert_freights_ati_raw(records)
        payload = {
            "ok": True,
            "mode": mode,
            "dir": base_dir,
            "since_minutes": since_minutes,
            "cutoff_utc": cutoff.isoformat() + "Z",
            "inserted": stats["inserted"],
            "updated": stats["updated"],
            "total_processed": len(records),
        }
        logger.info(
            "parser.ati.freights.pull[regions_json]: inserted=%s updated=%s total=%s dir=%s",
            stats["inserted"],
            stats["updated"],
            len(records),
            base_dir,
        )
        if not records:
            logger.warning(
                "parser.ati.freights.pull[regions_json]: no records found (dir=%s)",
                base_dir,
            )
        return payload

    logger.warning("parser.ati.freights.pull: unknown mode=%s", mode)
    return {
        "ok": False,
        "mode": mode,
        "error": "unknown ATI_PULL_MODE, expected one of: stub, local_json, regions_json",
        "since_minutes": since_minutes,
        "cutoff_utc": cutoff.isoformat() + "Z",
    }


# =============================================================================
# ETL: freights_ati_raw → public.freights
# =============================================================================


def _get_freights_columns(cur) -> Set[str]:
    """
    Возвращает множество колонок таблицы public.freights.

    Функция устойчива к разным типам курсоров:
      * ordinary cursor (row как кортеж);
      * cursor с row_factory=dict_row (row как dict).
    """
    cur.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name   = 'freights';
        """
    )
    cols: Set[str] = set()
    for row in cur.fetchall():
        if isinstance(row, dict):
            val = row.get("column_name")
            if val is None and row:
                val = next(iter(row.values()))
            if val is not None:
                cols.add(str(val))
        else:
            cols.add(str(row[0]))
    return cols


def _parse_ati_loading_date(raw_str: Optional[str], parsed_at: datetime) -> Optional[datetime]:
    """
    Парсим ATI-строки с датой погрузки.

    Примеры:
      - "готов 21-22 нояб."
      - "готов 21 нояб."
      - "готов 20-24 нояб."
      - "постоянно"

    Логика:
      - "постоянно" → берём дату parsed_at (как дату готовности).
      - "готов 21-22 нояб." → берём первую дату интервала (21 ноября).
      - если месяц не распознался — fallback на parsed_at.date().
      - при любой жести (битая строка) — тоже fallback на parsed_at.date().

    Возвращает datetime с той же tzinfo, что и parsed_at (если есть).
    """
    if parsed_at is None:
        return None

    base_date = parsed_at.date()
    tzinfo = parsed_at.tzinfo

    if not raw_str:
        return datetime(base_date.year, base_date.month, base_date.day, tzinfo=tzinfo)

    s = raw_str.strip().lower()
    if not s:
        return datetime(base_date.year, base_date.month, base_date.day, tzinfo=tzinfo)

    # "постоянно", "на постоянку" — груз доступен сегодня
    if "постоян" in s:
        return datetime(base_date.year, base_date.month, base_date.day, tzinfo=tzinfo)

    # режем служебные слова в начале
    for prefix in ("готов", "с", "c", "к "):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()

    # карты месяцев по первым 3 буквам
    month_map = {
        "янв": 1,
        "фев": 2,
        "мар": 3,
        "апр": 4,
        "мая": 5,
        "май": 5,
        "июн": 6,
        "июл": 7,
        "авг": 8,
        "сен": 9,
        "окт": 10,
        "ноя": 11,
        "дек": 12,
    }

    # паттерн "21", "21-22", "21-22 нояб."
    m = re.search(r"(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s+([а-я.]+)", s)
    if m:
        day_str = m.group(1)
        month_token = m.group(3).strip(". ")
        month_key = month_token[:3]
        month = month_map.get(month_key)
        if month is None:
            return datetime(base_date.year, base_date.month, base_date.day, tzinfo=tzinfo)

        day = int(day_str)
        year = base_date.year
        try:
            return datetime(year, month, day, tzinfo=tzinfo)
        except ValueError:
            return datetime(base_date.year, base_date.month, base_date.day, tzinfo=tzinfo)

    # ничего не распарсили — используем дату парсинга
    return datetime(base_date.year, base_date.month, base_date.day, tzinfo=tzinfo)


def _coerce_number(val: Any) -> Optional[float]:
    """
    Мягкое приведение к float.

    Поддерживаем:
      - int/float/Decimal
      - строки "1 234,56", "1234.56", "1200 руб" (вычищаем нечисловые символы).
    Любые странности → None.
    """
    if val is None:
        return None
    if isinstance(val, (int, float, Decimal)):
        return float(val)
    if isinstance(val, str):
        s = re.sub(r"[^0-9,\.]", "", val)
        s = s.replace(",", ".")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _extract_freight_core_from_payload(
    _src: str,
    _external_id: str,
    payload: Dict[str, Any],
    parsed_at: datetime,
) -> Optional[Dict[str, Any]]:
    """
    Извлекаем ядро записи для вставки в public.freights.

    Гарантии на выходе (если не None):
      - loading_region / unloading_region — НЕ пустые строки (минимум 'RU-UNK').
      - loading_date / unloading_date — заданы (datetime, без NULL).
      - distance, weight, revenue_rub — "best effort" (могут быть NULL).

    Если дату погрузки вообще не удалось оценить — возвращаем None, такую запись
    ETL пропустит и просто посчитает как skipped_no_date.

    distance интерпретируется как километры и маппится на public.freights.distance_km,
    revenue_rub — на public.freights.price_rub, weight — на public.freights.weight_tons.
    """
    raw = payload.get("raw") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        raw = payload if isinstance(payload, dict) else {}

    # 1) Грубые поля "откуда / куда"
    loading_region: Optional[str] = None
    unloading_region: Optional[str] = None

    # Попытка разобрать region_name вида "Московская область - ХМАО Югра"
    region_name = raw.get("region_name")
    if isinstance(region_name, str):
        s = region_name.strip()
        if s:
            parts = re.split(r"\s*[-–]\s*", s, maxsplit=1)
            if len(parts) == 2:
                left, right = parts
                loading_region = left.strip() or None
                unloading_region = right.strip() or None

    # Fallback к старой логике, если что-то не удалось
    if not loading_region:
        loading_region = (
            raw.get("loading_region")
            or raw.get("from_region")
            or raw.get("from_city")
            or raw.get("loading_city")
            or raw.get("from")
            or raw.get("origin")
        )

    if not unloading_region:
        unloading_region = (
            raw.get("unloading_region")
            or raw.get("to_region")
            or raw.get("to_city")
            or raw.get("unloading_city")
            or raw.get("to")
            or raw.get("destination")
        )

    if isinstance(loading_region, str):
        loading_region = loading_region.strip() or "RU-UNK"
    else:
        loading_region = "RU-UNK"

    if isinstance(unloading_region, str):
        unloading_region = unloading_region.strip() or "RU-UNK"
    else:
        unloading_region = "RU-UNK"

    # 2) Дата погрузки
    loading_raw = (
        raw.get("loading_date")
        or raw.get("date")
        or raw.get("date_from")
    )
    loading_date = _parse_ati_loading_date(loading_raw, parsed_at)
    if loading_date is None:
        return None

    # 3) Экономика / расстояние
    distance = _coerce_number(
        raw.get("distance_km")
        or raw.get("distance")
        or raw.get("km")
    )
    weight = _coerce_number(raw.get("weight"))
    body_type = raw.get("body_type") or raw.get("truck_type")

    revenue_rub = _coerce_number(
        raw.get("price_rub")
        or raw.get("price")
        or raw.get("payment")
        or raw.get("min_price")
        or raw.get("avg_price")
    )

    # 4) Время в пути по простой модели:
    #    2 часа погрузка + distance/55 + 2 часа выгрузка.
    load_hours = 2.0
    unload_hours = 2.0
    if distance is None:
        # если расстояние неизвестно — считаем одну смену + погрузка/выгрузка
        drive_hours = 8.0
    else:
        drive_hours = max(distance / 55.0, 1.0)

    total_hours = load_hours + drive_hours + unload_hours
    unloading_date = loading_date + timedelta(hours=total_hours)

    return {
        "loading_region": loading_region,
        "unloading_region": unloading_region,
        "loading_date": loading_date,
        "unloading_date": unloading_date,
        "distance": distance,
        "revenue_rub": revenue_rub,
        "body_type": body_type,
        "weight": weight,
    }


@shared_task(name="etl.freights.from_ati")
def etl_freights_from_ati(
    limit: Optional[int] = None,
    src_filter: Optional[str] = None,
    days_back: Optional[int] = None,
) -> Dict[str, Any]:
    """
    ETL ATI → public.freights.

    Источник: public.freights_ati_raw (src, external_id, payload, parsed_at).

    Поведение:
      * выбираем хвост из freights_ati_raw (по src_filter и / или days_back);
      * для каждой raw-записи собираем ядро через _extract_freight_core_from_payload;
      * пропускаем записи, для которых не удаётся оценить дату погрузки;
      * вставляем/обновляем в public.freights записи по ключу (source, source_uid).

    Вставляемые/обновляемые поля в public.freights:
      - loading_region   (без NULL, минимум 'RU-UNK')
      - unloading_region (без NULL, минимум 'RU-UNK')
      - loading_date     (NOT NULL)
      - unloading_date   (NOT NULL, по формуле 2ч + distance/55 + 2ч)
      - distance_km, price_rub, weight_tons (best effort)
      - source, source_uid, parsed_at, payload, created_at=parsed_at
    """
    if psycopg is None or dict_row is None:
        raise RuntimeError("psycopg is not available in this environment")

    if limit is None:
        limit = ATI_ETL_LIMIT_DEFAULT
    limit_eff = int(limit or ATI_ETL_LIMIT_DEFAULT)
    if limit_eff <= 0:
        return {
            "ok": True,
            "limit": limit_eff,
            "inserted": 0,
            "updated": 0,
            "processed": 0,
            "skipped_no_date": 0,
            "skipped_conflict": 0,
            "skipped_other": 0,
            "note": "etl.freights.from_ati: limit <= 0, nothing to do",
        }

    # correlation_id для событий — компактная строка с основными параметрами запуска
    correlation_id = (
        f"etl.freights.from_ati:"
        f"src_filter={src_filter}:limit={limit_eff}:days_back={days_back}"
    )

    emit_start(
        "etl.freights",
        correlation_id=correlation_id,
        payload={
            "limit_raw": limit,
            "limit_used": limit_eff,
            "src_filter": src_filter,
            "days_back": days_back,
        },
    )

    # По умолчанию тащим основные источники ATI.
    # Если явно указан src_filter — используем только его.
    # Иначе берём все три потока: 'ati', 'ati_html', 'ati_html_region'.
    if src_filter:
        srcs: List[str] = [src_filter]
    else:
        srcs = ["ati", "ati_html", "ati_html_region"]

    # Именованные параметры, чтобы psycopg превратил Python-list в text[]
    days_clause = ""
    params_sql: Dict[str, Any] = {
        "srcs": srcs,
        "limit": limit_eff,
    }
    if days_back is not None and days_back > 0:
        days_clause = (
            "AND r.parsed_at >= now() - (%(days_back)s || ' days')::interval"
        )
        params_sql["days_back"] = days_back

    result: Dict[str, Any] = {
        "ok": True,
        "srcs": srcs,
        "limit": limit_eff,
        "days_back": days_back,
        "total_raw": 0,
        "processed": 0,
        "inserted": 0,
        "updated": 0,
        "skipped_no_date": 0,
        "skipped_conflict": 0,
        "skipped_other": 0,
    }

    conn = _connect_pg()
    try:
        # ВАЖНО: включаем autocommit, чтобы каждая вставка была отдельной транзакцией.
        # Ошибка на одной строке не блокирует следующие.
        try:
            if hasattr(conn, "autocommit"):
                conn.autocommit = True
        except Exception:  # noqa: BLE001
            logger.warning(
                "etl.freights.from_ati: failed to enable autocommit; "
                "continuing without it",
            )

        # 1) sanity-check схемы freights — отдельным cursor без dict_row
        with conn.cursor() as cur_schema:
            cols = _get_freights_columns(cur_schema)

        required = {
            "loading_region",
            "unloading_region",
            "loading_date",
            "unloading_date",
            "source",
            "source_uid",
            "parsed_at",
            "payload",
            "created_at",
        }
        missing = required - cols
        if missing:
            msg = f"public.freights missing columns: {sorted(missing)}"
            logger.error("etl.freights.from_ati: %s", msg)
            result["ok"] = False
            result["error"] = msg
            return result

        # 2) основной ETL-проход — cursor с dict_row для удобства
        with conn.cursor(row_factory=dict_row) as cur:  # type: ignore[arg-type]
            sql_raw = f"""
                SELECT
                  r.src,
                  r.external_id,
                  r.payload,
                  r.parsed_at
                FROM public.freights_ati_raw AS r
                WHERE r.src = ANY(%(srcs)s)
                  {days_clause}
                ORDER BY r.parsed_at DESC
                LIMIT %(limit)s
            """
            cur.execute(sql_raw, params_sql)
            rows = cur.fetchall()
            result["total_raw"] = len(rows)

            # Вставка/обновление в public.freights под реальную схему:
            # UPSERT по (source, source_uid) с обновлением основных полей.
            insert_sql = """
                INSERT INTO public.freights (
                    loading_region,
                    unloading_region,
                    loading_date,
                    unloading_date,
                    distance_km,
                    price_rub,
                    weight_tons,
                    source,
                    source_uid,
                    parsed_at,
                    payload,
                    created_at
                )
                VALUES (
                    %(loading_region)s,
                    %(unloading_region)s,
                    %(loading_date)s,
                    %(unloading_date)s,
                    %(distance)s,
                    %(revenue_rub)s,
                    %(weight)s,
                    %(source)s,
                    %(source_uid)s,
                    %(parsed_at)s,
                    %(payload)s::jsonb,
                    %(created_at)s
                )
                ON CONFLICT (source, source_uid) DO UPDATE
                SET
                    loading_region   = EXCLUDED.loading_region,
                    unloading_region = EXCLUDED.unloading_region,
                    loading_date     = EXCLUDED.loading_date,
                    unloading_date   = EXCLUDED.unloading_date,
                    distance_km      = EXCLUDED.distance_km,
                    price_rub        = EXCLUDED.price_rub,
                    weight_tons      = EXCLUDED.weight_tons,
                    parsed_at        = EXCLUDED.parsed_at,
                    payload          = EXCLUDED.payload
            """

            for row in rows:
                result["processed"] += 1
                src = row["src"]
                external_id = row["external_id"]
                payload = row["payload"] or {}
                parsed_at = row["parsed_at"]

                core = _extract_freight_core_from_payload(
                    _src=src,
                    _external_id=external_id,
                    payload=payload,
                    parsed_at=parsed_at,
                )
                if core is None:
                    result["skipped_no_date"] += 1
                    continue

                # ВАЖНО: сериализуем payload в JSON-строку,
                # иначе psycopg не умеет адаптировать dict
                payload_json = json.dumps(payload, ensure_ascii=False)

                params_ins: Dict[str, Any] = {
                    "loading_region": core["loading_region"],
                    "unloading_region": core["unloading_region"],
                    "loading_date": core["loading_date"],
                    "unloading_date": core["unloading_date"],
                    "distance": core["distance"],
                    "revenue_rub": core["revenue_rub"],
                    "body_type": core["body_type"],
                    "weight": core["weight"],
                    "source": src,
                    "source_uid": external_id,
                    "parsed_at": parsed_at,
                    "payload": payload_json,
                    "created_at": parsed_at,
                }

                try:
                    cur.execute(insert_sql, params_ins)
                except Exception:  # noqa: BLE001
                    result["skipped_other"] += 1
                    logger.exception(
                        "etl.freights.from_ati: failed on src=%s external_id=%s",
                        src,
                        external_id,
                    )
                else:
                    status = (cur.statusmessage or "").upper()
                    # INSERT 0 1 / UPDATE 1
                    if status.startswith("INSERT"):
                        result["inserted"] += 1
                    elif status.startswith("UPDATE"):
                        result["updated"] += 1
                    else:
                        # fallback: считаем как вставку
                        result["inserted"] += 1

    except Exception as e:  # noqa: BLE001
        logger.exception("etl.freights.from_ati failed: %s", e)
        result["ok"] = False
        result["error"] = str(e)
        emit_error(
            "etl.freights",
            correlation_id=correlation_id,
            payload={
                "error": str(e),
                "result": result,
            },
        )
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    logger.info("etl.freights.from_ati: %s", result)
    emit_done(
        "etl.freights",
        correlation_id=correlation_id,
        payload=result,
    )
    return result


__all__ = [
    "task_parsers_watchdog",
    "parser_ati_freights_pull",
    "etl_freights_from_ati",
]
