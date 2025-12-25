# -*- coding: utf-8 -*-
"""
ATI ETL CLI.

Задача модуля:
- пройтись по всем JSONL-файлам, которые пишет src.parsers.ati_parser (REGIONS_DATA_DIR),
- собрать честную статистику по файлам/строкам/уникальным hash,
- опционально (если задан DSN и установлен psycopg2) записать данные в Postgres
  в указанную таблицу (по умолчанию raw.freights_ati_raw) с UPSERT по (source, source_uid).

Запуск:
  python -m src.cli.ati_etl daily --dry-run
  python -m src.cli.ati_etl daily --dsn postgresql://user:pass@host:5432/dbname

По-умолчанию:
- режим dry-run, только лог и статистика;
- TABLE берётся из ATI_ETL_TABLE (по умолчанию raw.freights_ati_raw);
- DSN берётся из ATI_ETL_DSN, если не передан явно.
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple, Any

# ---------------------------
# Настройка логирования
# ---------------------------

LOG_FILE = "ati_etl.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------
# Попытка импортировать REGIONS_DATA_DIR из парсера
# ---------------------------

REGIONS_DATA_DIR: Optional[Path] = None

try:
    from src.parsers import ati_parser  # type: ignore

    if hasattr(ati_parser, "REGIONS_DATA_DIR"):
        REGIONS_DATA_DIR = Path(ati_parser.REGIONS_DATA_DIR).resolve()
        logger.info(f"REGIONS_DATA_DIR взят из src.parsers.ati_parser: {REGIONS_DATA_DIR}")
    else:
        raise AttributeError("REGIONS_DATA_DIR not found in ati_parser")
except Exception as e:
    # fallback: вычисляем путь относительно src/cli
    here = Path(__file__).resolve()
    project_root = here.parents[2]  # .../foxproflow-mvp 2.0
    REGIONS_DATA_DIR = project_root / "src" / "parsers" / "regions_data"
    logger.warning(
        f"Не удалось импортировать REGIONS_DATA_DIR из src.parsers.ati_parser ({e}). "
        f"Используем fallback: {REGIONS_DATA_DIR}"
    )

# ---------------------------
# Опциональный импорт psycopg2
# ---------------------------

try:
    import psycopg2  # type: ignore
    from psycopg2.extras import Json as PsyJson  # noqa
    PSYCOPG2_AVAILABLE = True
except Exception:
    PSYCOPG2_AVAILABLE = False
    psycopg2 = None  # type: ignore
    PsyJson = None   # type: ignore
    logger.warning(
        "psycopg2 не установлен. ETL в Postgres будет недоступен, "
        "cli отработает только в dry-run режиме."
    )

# ---------------------------
# Конфигурация ETL
# ---------------------------

DEFAULT_TABLE = os.getenv("ATI_ETL_TABLE", "raw.freights_ati_raw")
DEFAULT_SOURCE = "ati"


@dataclass
class EtlConfig:
    regions_data_dir: Path
    dsn: Optional[str]
    table: str
    dry_run: bool
    since_hours: int


@dataclass
class EtlStats:
    files_total: int = 0
    files_processed: int = 0
    lines_total: int = 0
    lines_ok: int = 0
    lines_bad: int = 0
    unique_hashes: int = 0
    db_inserted: int = 0
    db_updated: int = 0
    db_failed: int = 0


# ---------------------------
# Утилиты по файлам / JSONL
# ---------------------------

def iter_jsonl_files(base_dir: Path, since_hours: int) -> Iterator[Path]:
    """
    Итерируемся по *.jsonl в дереве base_dir, начиная с файлов,
    модифицированных не ранее cutoff.
    """
    if not base_dir.exists():
        logger.warning(f"Папка с JSONL не найдена: {base_dir}")
        return
    cutoff = datetime.now() - timedelta(hours=since_hours)
    for path in sorted(base_dir.rglob("*.jsonl")):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            continue
        if mtime >= cutoff:
            yield path


def iter_jsonl_records(path: Path) -> Iterator[Dict[str, Any]]:
    """
    Читаем JSONL-файл построчно.
    """
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    yield obj
                else:
                    logger.debug(f"{path}#{line_no}: строка не является JSON-объектом, пропускаем")
            except json.JSONDecodeError as e:
                logger.warning(f"{path}#{line_no}: ошибка JSON: {e}")


# ---------------------------
# Подготовка данных для БД
# ---------------------------

def extract_source_uid(record: Dict[str, Any]) -> Optional[str]:
    """
    Берём source_uid из raw.id, если есть, иначе из hash.
    """
    raw = record.get("raw") or {}
    sid = raw.get("id") or record.get("hash")
    if isinstance(sid, str) and sid:
        return sid
    return None


def normalize_record_for_db(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Приводим запись к минимальному набору полей для сырого слоя.
    Структура payload целиком складывается в JSONB.
    """
    payload = record
    source_uid = extract_source_uid(record)
    h = record.get("hash")

    def _get(key: str) -> Optional[str]:
        v = record.get(key)
        if v is None:
            return None
        return str(v)

    return {
        "source": DEFAULT_SOURCE,
        "source_uid": source_uid,
        "hash": h,
        "loading_city": _get("loading_city"),
        "unloading_city": _get("unloading_city"),
        "cargo": _get("cargo"),
        "body_type": _get("body_type"),
        "loading_date": _get("loading_date"),
        "weight": _get("weight"),
        "volume": _get("volume"),
        "price": _get("price"),
        "parsed_at": record.get("parsed_at"),
        "payload": payload,
    }


# ---------------------------
# Работа с БД (Postgres)
# ---------------------------

class DbClient:
    def __init__(self, dsn: str, table: str):
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("psycopg2 недоступен, ETL в БД невозможен")
        self.dsn = dsn
        self.table = table
        self._conn = None

    def connect(self) -> None:
        if self._conn is not None:
            return
        logger.info(f"Подключаемся к Postgres: {self.dsn}")
        self._conn = psycopg2.connect(self.dsn)  # type: ignore
        self._conn.autocommit = False

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def upsert_batch(self, rows: List[Dict[str, Any]]) -> Tuple[int, int, int]:
        """
        Простенький UPSERT батчем. Предполагаем, что в таблице есть уникальный индекс:
          UNIQUE(source, source_uid)
        Возвращаем: (inserted, updated, failed)
        """
        if not rows:
            return (0, 0, 0)

        self.connect()
        inserted = 0
        updated = 0
        failed = 0

        sql = f"""
        INSERT INTO {self.table} (
            source,
            source_uid,
            hash,
            loading_city,
            unloading_city,
            cargo,
            body_type,
            loading_date,
            weight,
            volume,
            price,
            parsed_at,
            payload
        )
        VALUES (
            %(source)s,
            %(source_uid)s,
            %(hash)s,
            %(loading_city)s,
            %(unloading_city)s,
            %(cargo)s,
            %(body_type)s,
            %(loading_date)s,
            %(weight)s,
            %(volume)s,
            %(price)s,
            %(parsed_at)s,
            %(payload)s
        )
        ON CONFLICT (source, source_uid)
        DO UPDATE SET
            hash = EXCLUDED.hash,
            loading_city = EXCLUDED.loading_city,
            unloading_city = EXCLUDED.unloading_city,
            cargo = EXCLUDED.cargo,
            body_type = EXCLUDED.body_type,
            loading_date = EXCLUDED.loading_date,
            weight = EXCLUDED.weight,
            volume = EXCLUDED.volume,
            price = EXCLUDED.price,
            parsed_at = EXCLUDED.parsed_at,
            payload = EXCLUDED.payload;
        """

        cur = self._conn.cursor()  # type: ignore
        for row in rows:
            # если нет source_uid — смысла писать в БД нет, считаем failed
            if not row.get("source_uid"):
                failed += 1
                continue
            try:
                db_row = dict(row)
                # psycopg2.Json для payload
                db_row["payload"] = PsyJson(db_row["payload"])  # type: ignore
                cur.execute(sql, db_row)
                # отличить insert/ update по cur.rowcount нельзя напрямую в UPSERT,
                # поэтому считаем всё как "insert_or_update".
                inserted += 1
            except Exception as e:
                failed += 1
                logger.error(f"Ошибка вставки в БД: {e}")
        try:
            self._conn.commit()  # type: ignore
        except Exception as e:
            logger.error(f"Ошибка commit в БД: {e}")
        cur.close()
        # Технически мы не различили insert/update, поэтому:
        updated = 0
        return (inserted, updated, failed)


# ---------------------------
# Основная ETL-логика
# ---------------------------

def run_daily_etl(cfg: EtlConfig) -> EtlStats:
    stats = EtlStats()
    regions_dir = cfg.regions_data_dir

    if not regions_dir.exists():
        logger.error(f"REGIONS_DATA_DIR не существует: {regions_dir}")
        return stats

    logger.info(
        f"Старт ATI ETL (daily). REGIONS_DATA_DIR={regions_dir}, "
        f"since_hours={cfg.since_hours}, dry_run={cfg.dry_run}, table={cfg.table}"
    )

    db_client: Optional[DbClient] = None
    if not cfg.dry_run and cfg.dsn:
        try:
            db_client = DbClient(cfg.dsn, cfg.table)
        except Exception as e:
            logger.error(f"Не удалось инициализировать DbClient: {e}")
            logger.info("Продолжаем в dry-run режиме без БД")
            db_client = None

    seen_hashes: set[str] = set()

    for file_path in iter_jsonl_files(regions_dir, cfg.since_hours):
        stats.files_total += 1
        logger.info(f"Обработка файла: {file_path}")
        file_lines = 0
        file_ok = 0
        file_bad = 0
        batch: List[Dict[str, Any]] = []

        for rec in iter_jsonl_records(file_path):
            file_lines += 1
            stats.lines_total += 1

            h = rec.get("hash")
            if isinstance(h, str) and h:
                if h in seen_hashes:
                    # уже видели такую запись в этом ETL-прогоне (из другого файла/региона)
                    continue
                seen_hashes.add(h)

            try:
                norm = normalize_record_for_db(rec)
                file_ok += 1
                stats.lines_ok += 1
                if not cfg.dry_run and db_client is not None:
                    batch.append(norm)
                    # простая порционная загрузка
                    if len(batch) >= 1000:
                        ins, upd, fail = db_client.upsert_batch(batch)
                        stats.db_inserted += ins
                        stats.db_updated += upd
                        stats.db_failed += fail
                        batch.clear()
            except Exception as e:
                file_bad += 1
                stats.lines_bad += 1
                logger.error(f"{file_path}: ошибка нормализации записи: {e}")

        # добиваем хвост батча
        if batch and not cfg.dry_run and db_client is not None:
            ins, upd, fail = db_client.upsert_batch(batch)
            stats.db_inserted += ins
            stats.db_updated += upd
            stats.db_failed += fail

        logger.info(
            f"Файл {file_path.name}: строк всего={file_lines}, ок={file_ok}, с ошибками={file_bad}"
        )
        stats.files_processed += 1

    stats.unique_hashes = len(seen_hashes)

    if db_client is not None:
        db_client.close()

    logger.info(
        "ATI ETL завершён: "
        f"files_total={stats.files_total}, files_processed={stats.files_processed}, "
        f"lines_total={stats.lines_total}, ok={stats.lines_ok}, bad={stats.lines_bad}, "
        f"unique_hashes={stats.unique_hashes}, "
        f"db_inserted={stats.db_inserted}, db_updated={stats.db_updated}, db_failed={stats.db_failed}"
    )
    return stats


# ---------------------------
# CLI
# ---------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI для ETL ATI JSONL → Postgres (или dry-run со статистикой)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily = subparsers.add_parser("daily", help="ежедневная выгрузка (все свежие файлы)")
    daily.add_argument(
        "--regions-dir",
        type=str,
        default=str(REGIONS_DATA_DIR),
        help=f"папка с JSONL (по умолчанию {REGIONS_DATA_DIR})",
    )
    daily.add_argument(
        "--dsn",
        type=str,
        default=os.getenv("ATI_ETL_DSN"),
        help="DSN для Postgres (postgresql://user:pass@host:5432/dbname); "
             "если не задан — режим dry-run",
    )
    daily.add_argument(
        "--table",
        type=str,
        default=DEFAULT_TABLE,
        help=f"целествая таблица (по умолчанию {DEFAULT_TABLE})",
    )
    daily.add_argument(
        "--since-hours",
        type=int,
        default=24,
        help="брать файлы, изменённые за последние N часов (по умолчанию 24)",
    )
    daily.add_argument(
        "--dry-run",
        action="store_true",
        help="не писать в БД, только читать файлы и выводить статистику",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "daily":
        regions_dir = Path(args.regions_dir).resolve()
        dsn = args.dsn
        dry_run = bool(args.dry_run or not dsn or not PSYCOPG2_AVAILABLE)

        if not dsn and not args.dry_run:
            logger.warning(
                "DSN не задан, а --dry-run не включён. "
                "Переключаюсь в dry-run режим без записи в БД."
            )

        if not PSYCOPG2_AVAILABLE and not args.dry_run:
            logger.warning(
                "psycopg2 недоступен, запись в БД невозможна. "
                "Переключаюсь в dry-run."
            )

        cfg = EtlConfig(
            regions_data_dir=regions_dir,
            dsn=dsn if (dsn and PSYCOPG2_AVAILABLE and not args.dry_run) else None,
            table=args.table,
            dry_run=dry_run,
            since_hours=args.since_hours,
        )
        stats = run_daily_etl(cfg)

        # Немного читаемого вывода в stdout на случай запуска из PowerShell-скрипта
        print(
            f"ATI ETL daily done: files={stats.files_processed}/{stats.files_total}, "
            f"lines={stats.lines_ok}/{stats.lines_total} ok, "
            f"unique_hashes={stats.unique_hashes}, "
            f"db_inserted={stats.db_inserted}, db_failed={stats.db_failed}"
        )
    else:
        parser.error(f"Неизвестная команда: {args.command}")


if __name__ == "__main__":
    main()
