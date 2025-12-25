from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional

from celery import shared_task

from src.core.pg_conn import _connect_pg
from src.parsers.regions_data_loader import import_regions_data

log = logging.getLogger(__name__)

UTC = timezone.utc
PARSERS_QUEUE = os.getenv("PARSERS_QUEUE", "parsers")

# Конфигурация источника ATI через ENV
ATI_PULL_MODE_DEFAULT = os.getenv("ATI_PULL_MODE", "stub").strip().lower()
ATI_PULL_DIR_DEFAULT = os.getenv("ATI_PULL_DIR", "/app/data/ati_freights").strip()


# ---------------------------------------------------------------------
# Вспомогательные утилиты
# ---------------------------------------------------------------------
def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    """Пытаемся распарсить ISO-дату в UTC, иначе возвращаем None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)
        return dt
    except Exception:
        log.warning("parser.ati.freights.pull: bad parsed_at=%r", value)
        return None


def _coerce_ati_record(
    obj: Dict[str, Any],
    cutoff: Optional[datetime],
) -> Optional[Dict[str, Any]]:
    """
    Превращаем сырой ATI-объект в нормализованный словарь
    для вставки в public.freights_ati_raw.

    Правила:
      • src — из obj['src'] или 'ati_html' по умолчанию;
      • external_id — приоритет raw.id → payload.raw.id → obj.external_id → obj.hash;
      • parsed_at — obj.parsed_at (ISO, в UTC) или now();
      • cutoff: если задан и parsed_at < cutoff, запись отбрасываем;
      • payload — либо obj['payload'], либо весь объект.
    """
    src = obj.get("src") or "ati_html"

    raw = obj.get("raw") or {}
    payload = obj.get("payload") or obj
    payload_raw: Dict[str, Any] = {}
    if isinstance(payload, dict):
        payload_raw = payload.get("raw") or {}

    external_id = (
        raw.get("id")
        or payload_raw.get("id")
        or obj.get("external_id")
        or obj.get("hash")
    )
    if not external_id:
        # Без стабильного external_id upsert по (src, external_id) невозможен
        return None

    parsed_at_raw = obj.get("parsed_at")
    parsed_at_dt = _parse_iso_dt(parsed_at_raw) or _utcnow()

    # Если задан cutoff — фильтруем старые записи
    if cutoff is not None and parsed_at_dt < cutoff:
        return None

    payload_value = payload if payload is not None else obj

    return {
        "src": str(src),
        "external_id": str(external_id),
        "parsed_at": parsed_at_dt,
        "payload": payload_value,
    }


def _iter_local_json_records(
    base_dir: str,
    cutoff: Optional[datetime],
) -> Iterator[Dict[str, Any]]:
    """
    Итерируем сырые записи ATI (или совместимые с ними) из локального каталога:

      • *.jsonl — JSON-L, одна строка = один объект;
      • *.json  — либо dict, либо list[dict].

    cutoff: optional datetime в UTC; если задан — _coerce_ati_record
    отфильтрует всё, что старше cutoff.
    """
    root = Path(base_dir)
    if not root.exists():
        log.warning(
            "parser.ati.freights.pull[local_json]: dir not found: %s",
            base_dir,
        )
        return

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in (".json", ".jsonl"):
            continue

        total = 0
        accepted = 0

        try:
            if suffix == ".jsonl":
                # Классический JSONL — по строке на объект
                with path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        total += 1
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            log.warning(
                                "parser.ati.freights.pull[local_json]: bad JSONL line in %s",
                                path,
                            )
                            continue
                        if not isinstance(obj, dict):
                            continue
                        rec = _coerce_ati_record(obj, cutoff)
                        if rec is not None:
                            accepted += 1
                            yield rec
            else:
                # Обычный JSON: либо dict, либо list[dict]
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list):
                    for obj in data:
                        if not isinstance(obj, dict):
                            continue
                        total += 1
                        rec = _coerce_ati_record(obj, cutoff)
                        if rec is not None:
                            accepted += 1
                            yield rec
                elif isinstance(data, dict):
                    total += 1
                    rec = _coerce_ati_record(data, cutoff)
                    if rec is not None:
                        accepted += 1
                        yield rec
                else:
                    log.warning(
                        "parser.ati.freights.pull[local_json]: unsupported JSON type in %s: %r",
                        path,
                        type(data),
                    )
        except FileNotFoundError:
            # файл могли удалить между os.walk и open — не страшно
            continue
        except Exception as e:
            log.warning(
                "parser.ati.freights.pull[local_json]: failed to read %s: %r",
                path,
                e,
            )
            continue

        log.info(
            "parser.ati.freights.pull[local_json]: file=%s total=%s accepted=%s",
            path,
            total,
            accepted,
        )


def _upsert_freights_ati_raw(records: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """
    UPSERT в public.freights_ati_raw по (src, external_id).

    Важно: явно указываем схему public, чтобы не писать в raw.freights_ati_raw
    при search_path=['raw','public',...].

    Таблица public.freights_ati_raw должна иметь как минимум поля:
      - src text
      - external_id text
      - payload jsonb
      - parsed_at timestamptz
    И уникальный индекс/constraint по (src, external_id).
    """
    inserted = 0
    updated = 0

    conn = _connect_pg()
    try:
        cur = conn.cursor()
        for rec in records:
            # psycopg3 не умеет адаптировать dict → jsonb автоматически,
            # поэтому превращаем payload в строку JSON и кастуем к jsonb в SQL.
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
            # Для простоты считаем всё как "обработано".
            # Если будет нужно — можно разделить на insert/update.
            inserted += 1

        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return {"inserted": inserted, "updated": updated}


# -----------------------------------------------------------------------------
# parsers.watchdog — существующий stub
# -----------------------------------------------------------------------------
@shared_task(name="parsers.watchdog")
def task_parsers_watchdog() -> Dict[str, Any]:
    return {"ok": True, "note": "parsers.watchdog stub"}


# -----------------------------------------------------------------------------
# parser.ati.freights.pull — загрузка фрахтов ATI в freights_ati_raw
# -----------------------------------------------------------------------------
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
    Универсальная таска-парсер по ATI.

    Параметры:
      • since_minutes — логическое окно свежести (минуты) для HTTP-режимов.
        Для local_json сейчас НЕ используется (берём всё, что лежит в каталоге).
      • mode — режим работы; если не передан, берётся из ATI_PULL_MODE.

    Режимы:
      • "stub"       — ничего не делает, только логирует.
      • "local_json" — читает *.json / *.jsonl из ATI_PULL_DIR
                       и UPSERT'ит их в public.freights_ati_raw.
    """
    mode_eff = (mode or ATI_PULL_MODE_DEFAULT or "stub").strip().lower()
    base_dir = ATI_PULL_DIR_DEFAULT or "/app/data/ati_freights"

    # В перспективе сюда можно добавить HTTP-парсер с since_minutes/cutoff.
    now = _utcnow()
    cutoff = now - timedelta(minutes=since_minutes) if since_minutes is not None else None

    log.info(
        "parser.ati.freights.pull: start mode=%s since_minutes=%s cutoff_utc=%s dir=%s",
        mode_eff,
        since_minutes,
        cutoff.isoformat() if cutoff else None,
        base_dir,
    )

    if mode_eff == "stub":
        return {
            "ok": True,
            "mode": "stub",
            "note": "ATI_PULL_MODE=stub — парсер ничего не делает",
        }

    if mode_eff == "local_json":
        # Для локального JSON мы сейчас игнорируем cutoff, чтобы можно было
        # загрузить исторический дамп. Вся "свежесть" режется уже дальше по витринам.
        records = _iter_local_json_records(base_dir, cutoff=None)
        stats = _upsert_freights_ati_raw(records)
        log.info(
            "parser.ati.freights.pull[local_json]: upsert done: %s",
            stats,
        )
        return {
            "ok": True,
            "mode": "local_json",
            "dir": base_dir,
            "stats": stats,
        }

    log.warning(
        "parser.ati.freights.pull: unknown mode=%s, ничего не делаем",
        mode_eff,
    )
    return {
        "ok": False,
        "mode": mode_eff,
        "error": "unknown ATI_PULL_MODE; expected 'stub' or 'local_json'",
    }


# -----------------------------------------------------------------------------
# parser.regions_data.import — импорт региональных jsonl в freights_ati_raw
# -----------------------------------------------------------------------------
@shared_task(
    name="parser.regions_data.import",
    queue=PARSERS_QUEUE,
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def parser_regions_data_import(
    self,
    base_dir: str = "src/parsers/regions_data",
    src: str = "ati_html_region",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Импортирует все jsonl/JSON из src/parsers/regions_data в public.freights_ati_raw.

    Используем существующий конвейер ATI:
      freights_ati_raw -> freights_from_ati_v -> geocode -> freights -> freights_price_v.

    Параметры:
      • base_dir — каталог с региональными jsonl (в контейнере /app/src/parsers/regions_data);
      • src      — значение поля 'src' для freights_ati_raw (по умолчанию 'ati_html_region');
      • dry_run  — если True, только считает записи и ничего не пишет в БД.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    base_path = Path(base_dir)
    log.info(
        "parser.regions_data.import: start base_dir=%s src=%s dry_run=%s",
        base_path,
        src,
        dry_run,
    )

    result = import_regions_data(
        database_url=database_url,
        base_dir=base_path,
        src=src,
        dry_run=dry_run,
    )

    log.info("parser.regions_data.import: done: %s", result)
    return result
