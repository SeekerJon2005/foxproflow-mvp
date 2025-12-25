# -*- coding: utf-8 -*-
"""
FoxProFlow — офлайновый импорт ATI JSON/JSONL → public.freights_ati_raw.

Этот скрипт — тонкая обёртка над той же логикой, которую использует Celery-таска
parser.ati.freights.pull в режиме "local_json":

  • сканирует каталог с *.json / *.jsonl (ATI_PULL_DIR);
  • приводит каждую запись к виду:
        {src, external_id, parsed_at, payload}
  • делает UPSERT в public.freights_ati_raw по (src, external_id).

Задачи скрипта:
  - удобный ручной импорт исторических дампов ATI без запуска Celery/Beat;
  - гарантировать, что формат записей и upsert совпадают с боевым пайплайном.

Запуск (из корня проекта):

  python -m src.parsers.ati_import_jsonl
  python -m src.parsers.ati_import_jsonl -d ./data/ati_freights -m 4320
"""

from __future__ import annotations

import argparse
import os
from datetime import timedelta
from typing import List, Optional

# Берём готовые хелперы из рабочего ETL-модуля, чтобы не дублировать логику:
#  - _iter_local_json_records  — читает JSON/JSONL из каталога и отдаёт нормализованные записи;
#  - _upsert_freights_ati_raw  — UPSERT в public.freights_ati_raw;
#  - _utcnow                   — "правильные" UTC-часы проекта.
from ..worker.tasks_etl import (
    _iter_local_json_records,
    _upsert_freights_ati_raw,
    _utcnow,
)

# ---------------------------------------------------------------------------
# Конфиг по умолчанию (совместим с parser.ati.freights.pull)
# ---------------------------------------------------------------------------

# Где искать файлы с ATI-фрахтами:
#   по умолчанию — ATI_PULL_DIR или /app/data/ati_freights (как в worker’е).
DEFAULT_BASE_DIR = os.getenv("ATI_PULL_DIR", "/app/data/ati_freights")

# От какого момента по времени брать записи (минут назад).
# 0 или отрицательное значение трактуем как "без фильтра по времени".
DEFAULT_SINCE_MINUTES = int(os.getenv("ATI_JSONL_SINCE_MINUTES", "720"))


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m src.parsers.ati_import_jsonl",
        description=(
            "Импорт локальных ATI JSON/JSONL файлов в public.freights_ati_raw "
            "через ту же логику, что использует parser.ati.freights.pull[local_json]."
        ),
    )

    parser.add_argument(
        "-d",
        "--base-dir",
        default=DEFAULT_BASE_DIR,
        help=(
            "Каталог с ATI-файлами (*.json / *.jsonl). "
            "По умолчанию берётся ATI_PULL_DIR или /app/data/ati_freights."
        ),
    )

    parser.add_argument(
        "-m",
        "--since-minutes",
        type=int,
        default=DEFAULT_SINCE_MINUTES,
        help=(
            "Сколько минут назад брать нижнюю границу по parsed_at. "
            "0 или отрицательное число ≈ импорт всех записей без фильтра по времени."
        ),
    )

    args = parser.parse_args(argv)

    base_dir = os.path.abspath(args.base_dir)

    # cutoff для _coerce_ati_record внутри worker.tasks_etl:
    #  - если >0 — стандартное окно (как в parser.ati.freights.pull);
    #  - если <=0 — задаём очень старую дату, чтобы не отфильтровать ничего.
    if args.since_minutes and args.since_minutes > 0:
        cutoff = _utcnow() - timedelta(minutes=args.since_minutes)
    else:
        # Практически "без фильтра": всё, что новее, чем 50 лет назад.
        cutoff = _utcnow() - timedelta(days=365 * 50)

    print("=== FoxProFlow — офлайновый импорт ATI ===")
    print(f"Каталог: {base_dir}")
    print(f"cutoff_utc: {cutoff.isoformat()}")

    # 1) Собираем нормализованные записи из JSON/JSONL
    records = list(_iter_local_json_records(base_dir, cutoff))
    total = len(records)
    print(f"Найдено подходящих записей: {total}")

    if not records:
        print("Импорт не выполнен: нет подходящих записей.")
        return

    # 2) UPSERT в public.freights_ati_raw
    stats = _upsert_freights_ati_raw(records)
    inserted = stats.get("inserted", 0)
    updated = stats.get("updated", 0)

    print(
        "UPSERT в public.freights_ati_raw завершён: "
        f"inserted={inserted}, updated={updated}, total={total}"
    )


if __name__ == "__main__":
    main()
