import json
import os
from pathlib import Path
from typing import Dict, Iterable, Tuple, Optional

import sqlalchemy as sa


DEFAULT_BASE_DIR = Path("src/parsers/regions_data")
DEFAULT_SRC = "ati_html_region"


def iter_region_files(base_dir: Path) -> Iterable[Path]:
    """
    Рекурсивно обходит папку с данными регионов и отдаёт все *.jsonl файлы.
    """
    base_dir = Path(base_dir).resolve()
    for root, _dirs, files in os.walk(base_dir):
        root_path = Path(root)
        for name in files:
            if name.lower().endswith(".jsonl"):
                yield root_path / name


def iter_jsonl(path: Path) -> Iterable[Dict]:
    """
    Читает jsonl-файл построчно, отдаёт dict'ы.
    """
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def build_payload(record: Dict, region_name: str, source: str) -> Dict:
    """
    Строим payload для freights_ati_raw в формате, который понимает freights_from_ati_v.
    Всё складываем под ключ 'raw'.
    """
    loading_points = record.get("loading_points") or []
    unloading_points = record.get("unloading_points") or []
    prices = record.get("prices") or {}

    loading_point = loading_points[0] if loading_points else None
    unloading_point = unloading_points[0] if unloading_points else None

    # выбираем цену: приоритет "без НДС", иначе "с НДС"
    price_text = prices.get("без_НДС") or prices.get("с_НДС")

    raw = {
        "id": record.get("id"),
        "hash": record.get("hash"),
        "from_city": loading_point,
        "to_city": unloading_point,
        "loading_points": loading_points,
        "unloading_points": unloading_points,
        "cargo": record.get("cargo"),
        "body": record.get("body_type"),
        "loading_date": record.get("loading_date"),
        "loading_method": record.get("loading_method"),
        "possible_reload": record.get("possible_reload"),
        "weight": record.get("weight"),
        "volume": record.get("volume"),
        "distance_km": record.get("distance"),
        "price": price_text,
        "prices": prices,
        "region_name": region_name,
        "parsed_at": record.get("parsed_at"),
        "source": source,
    }

    return {"raw": raw}


def iter_rows_for_db(
    base_dir: Path,
    src: str = DEFAULT_SRC,
    limit: Optional[int] = None,
) -> Iterable[Tuple[str, str, Dict, Optional[str]]]:
    """
    Отдаёт кортежи (src, external_id, payload_dict, parsed_at_iso)
    для всех записей во всех файлах regions_data.

    limit — максимум записей (для тестов/отладки); если None — без ограничения.
    """
    base_dir = Path(base_dir)
    total = 0

    for path in iter_region_files(base_dir):
        region_name = path.parent.name  # имя папки: "Алтайский край"
        for rec in iter_jsonl(path):
            external_id = rec.get("id") or rec.get("hash")
            if not external_id:
                # пропускаем сломанные записи
                continue

            payload = build_payload(rec, region_name=region_name, source=src)
            parsed_at = rec.get("parsed_at") or None

            yield src, external_id, payload, parsed_at

            total += 1
            if limit is not None and total >= limit:
                return


def import_regions_data(
    database_url: str,
    base_dir: Path = DEFAULT_BASE_DIR,
    src: str = DEFAULT_SRC,
    dry_run: bool = False,
    limit: Optional[int] = None,
    echo_every: int = 50_000,
) -> Dict:
    """
    Загружает все regions_data в public.freights_ati_raw.

    - src: метка источника ('ati_html_region')
    - external_id: id/hash из json
    - payload: jsonb с полем raw
    - parsed_at: timestamp (берём из json, если есть)

    ON CONFLICT (src, external_id) DO UPDATE:
      • новые записи вставляются,
      • существующие обновляют payload/parsed_at.

    limit — максимум записей (для тестов); по умолчанию грузим всё.
    echo_every — как часто печатать прогресс (по числу записей).
    """
    if not database_url:
        raise ValueError("database_url is required")

    base_dir = Path(base_dir)
    if not base_dir.exists():
        raise FileNotFoundError(f"Base dir with regions data not found: {base_dir}")

    engine = sa.create_engine(database_url)

    # ВАЖНО:
    #  - используем единый стиль параметров :name (SQLAlchemy),
    #  - приведение типов делаем через CAST, чтобы избежать конструкции :payload::jsonb,
    #    которая ранее приводила к тому, что :payload не подменялся параметром.
    insert_sql = sa.text(
        """
        INSERT INTO public.freights_ati_raw (src, external_id, payload, parsed_at, created_at)
        VALUES (
            :src,
            :external_id,
            CAST(:payload AS jsonb),
            COALESCE(CAST(:parsed_at AS timestamptz), NOW()),
            NOW()
        )
        ON CONFLICT (src, external_id) DO UPDATE
        SET payload = EXCLUDED.payload,
            parsed_at = EXCLUDED.parsed_at
        RETURNING (xmax = 0) AS inserted_flag
        """
    ).bindparams(
        sa.bindparam("src"),
        sa.bindparam("external_id"),
        # payload — это JSON-строка, которую Postgres приведёт к jsonb
        sa.bindparam("payload"),
        # parsed_at — ISO-строка или None, приводим к timestamptz
        sa.bindparam("parsed_at"),
    )

    inserted = 0
    updated = 0
    total = 0

    with engine.begin() as conn:
        for src_val, ext_id, payload_dict, parsed_at in iter_rows_for_db(
            base_dir=base_dir,
            src=src,
            limit=limit,
        ):
            total += 1

            if dry_run:
                # В dry_run просто считаем строки, в БД не пишем
                if echo_every and total % echo_every == 0:
                    print(
                        f"[regions_data_loader][dry_run] processed={total}",
                        flush=True,
                    )
                continue

            result = conn.execute(
                insert_sql,
                {
                    "src": src_val,
                    "external_id": ext_id,
                    "payload": json.dumps(payload_dict, ensure_ascii=False),
                    "parsed_at": parsed_at,
                },
            )
            row = result.fetchone()
            if row is not None and bool(row[0]):
                inserted += 1
            else:
                updated += 1

            if echo_every and total % echo_every == 0:
                # лёгкий прогресс-лог, чтобы понимать, что процесс живой
                print(
                    f"[regions_data_loader] processed={total}, "
                    f"inserted={inserted}, updated={updated}",
                    flush=True,
                )

    return {
        "ok": True,
        "src": src,
        "base_dir": str(base_dir),
        "total": total,
        "inserted": inserted,
        "updated": updated,
        "dry_run": dry_run,
        "limit": limit,
    }


def main() -> None:
    """
    Простейший CLI, чтобы можно было дернуть модуль напрямую:

      python -m src.parsers.regions_data_loader --limit 10000 --dry-run
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Импорт данных регионов ATI в public.freights_ati_raw"
    )
    parser.add_argument(
        "--database-url",
        "-d",
        dest="database_url",
        help="Строка подключения к БД. Если не задано — берём из DATABASE_URL/FF_DATABASE_URL.",
    )
    parser.add_argument(
        "--base-dir",
        "-b",
        dest="base_dir",
        default=str(DEFAULT_BASE_DIR),
        help="Папка с jsonl-файлами (по умолчанию src/parsers/regions_data)",
    )
    parser.add_argument(
        "--src",
        dest="src",
        default=DEFAULT_SRC,
        help="Значение src для freights_ati_raw (по умолчанию ati_html_region)",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Ничего не пишем в БД, только считаем строки",
    )
    parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=None,
        help="Максимальное число записей для обработки (для тестов)",
    )
    parser.add_argument(
        "--echo-every",
        dest="echo_every",
        type=int,
        default=50_000,
        help="Как часто печатать прогресс (0 — отключить)",
    )

    args = parser.parse_args()

    database_url = (
        args.database_url
        or os.getenv("DATABASE_URL")
        or os.getenv("FF_DATABASE_URL")
    )
    if not database_url:
        raise SystemExit(
            "DATABASE_URL / FF_DATABASE_URL не заданы и --database-url не передан"
        )

    stats = import_regions_data(
        database_url=database_url,
        base_dir=Path(args.base_dir),
        src=args.src,
        dry_run=bool(args.dry_run),
        limit=args.limit,
        echo_every=args.echo_every,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
