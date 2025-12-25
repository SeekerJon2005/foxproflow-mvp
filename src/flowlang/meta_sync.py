# -*- coding: utf-8 -*-
# file: src/flowlang/meta_sync.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .meta_model import (
    MetaWorld,
    MetaDomain,
    MetaDSL,
    MetaEffect,
    MetaAgentClass,
    MetaPlanClass,
)
from .meta_parser import load_meta_world


@dataclass
class SyncResult:
    """
    Результат синхронизации мира FlowMeta в БД.
    """
    domains: int = 0
    dsls: int = 0
    effects: int = 0
    agent_classes: int = 0
    plan_classes: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "domains": self.domains,
            "dsls": self.dsls,
            "effects": self.effects,
            "agent_classes": self.agent_classes,
            "plan_classes": self.plan_classes,
        }


def _get_pg_conn():
    """
    Универсальное подключение к БД Postgres.

    Приоритет:
      1) FF_DB_DSN или DATABASE_URL (полный DSN)
      2) PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD
      3) дефолты для docker-сетки FoxProFlow: host=db, user=postgres, db=postgres.

    Попытка подключения:
      - сначала через psycopg (v3),
      - если его нет — через psycopg2.
    """
    dsn = os.getenv("FF_DB_DSN") or os.getenv("DATABASE_URL")

    # --- Ветка 1: подключение по DSN -----------------------------------
    if dsn:
        # Сначала пробуем psycopg (v3)
        try:
            import psycopg  # type: ignore[import]

            return psycopg.connect(dsn)
        except ModuleNotFoundError:
            # Падаем на psycopg2, если psycopg не установлена
            pass

        try:
            import psycopg2  # type: ignore[import]

            return psycopg2.connect(dsn)
        except Exception as exc:
            raise RuntimeError(
                "Не удалось подключиться к БД по DSN ни через psycopg, ни через psycopg2"
            ) from exc

    # --- Ветка 2: собираем параметры по отдельности --------------------
    host = os.getenv("PGHOST", "db")
    port = os.getenv("PGPORT", "5432")
    dbname = os.getenv("PGDATABASE", "postgres")
    user = os.getenv("PGUSER", "postgres")
    password = os.getenv("PGPASSWORD", "postgres")

    # Пробуем psycopg (v3)
    try:
        import psycopg  # type: ignore[import]

        return psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )
    except ModuleNotFoundError:
        pass

    # Фоллбек на psycopg2
    try:
        import psycopg2  # type: ignore[import]

        return psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )
    except Exception as exc:
        raise RuntimeError(
            "Не удалось подключиться к БД: нет ни psycopg, ни psycopg2, "
            "или обе библиотеки не смогли установиться соединение."
        ) from exc


def load_world_from_meta(path: Path) -> MetaWorld:
    """
    Загружает MetaWorld из файла .meta (FlowMeta язык).
    """
    return load_meta_world(path)


def persist_world_to_db(world: MetaWorld) -> SyncResult:
    """
    Синхронизирует мир FlowMeta в таблицы flowmeta.*.

    ВАЖНО:
      - только INSERT ... ON CONFLICT DO UPDATE
      - никаких DELETE/ALTER — строго NDC-friendly.
    """
    result = SyncResult()

    conn = _get_pg_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # --- Домены ---------------------------------------------------
                for dom_code, dom in world.domains.items():
                    if not isinstance(dom, MetaDomain):
                        continue

                    description = dom.description
                    meta = dom.meta or {}

                    cur.execute(
                        """
                        INSERT INTO flowmeta.domain (code, description, meta)
                        VALUES (%s, %s, %s::jsonb)
                        ON CONFLICT (code) DO UPDATE
                           SET description = EXCLUDED.description,
                               meta        = flowmeta.domain.meta || EXCLUDED.meta,
                               updated_at  = now();
                        """,
                        (
                            dom_code,
                            description,
                            json.dumps(meta),
                        ),
                    )
                    result.domains += 1

                # --- DSL ------------------------------------------------------
                for dsl_code, dsl in world.dsls.items():
                    if not isinstance(dsl, MetaDSL):
                        continue

                    description = dsl.description
                    meta = dsl.meta or {}

                    cur.execute(
                        """
                        INSERT INTO flowmeta.dsl
                            (code, domain, description, files_pattern, enabled, meta)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (code) DO UPDATE
                           SET domain        = EXCLUDED.domain,
                               description   = EXCLUDED.description,
                               files_pattern = EXCLUDED.files_pattern,
                               enabled       = EXCLUDED.enabled,
                               meta          = flowmeta.dsl.meta || EXCLUDED.meta,
                               updated_at    = now();
                        """,
                        (
                            dsl_code,
                            dsl.domain,
                            description,
                            dsl.files_pattern,
                            dsl.enabled,
                            json.dumps(meta),
                        ),
                    )
                    result.dsls += 1

                # --- Эффекты --------------------------------------------------
                for eff_code, eff in world.effects.items():
                    if not isinstance(eff, MetaEffect):
                        continue

                    description = eff.description
                    meta = eff.meta or {}

                    cur.execute(
                        """
                        INSERT INTO flowmeta.effect_type
                            (code, kind, description, scope, meta)
                        VALUES (%s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (code) DO UPDATE
                           SET kind        = EXCLUDED.kind,
                               description = EXCLUDED.description,
                               scope       = EXCLUDED.scope,
                               meta        = flowmeta.effect_type.meta || EXCLUDED.meta,
                               updated_at  = now();
                        """,
                        (
                            eff_code,
                            eff.kind,
                            description,
                            eff.scope,
                            json.dumps(meta),
                        ),
                    )
                    result.effects += 1

                # --- Классы агентов ------------------------------------------
                for ac_code, ac in world.agent_classes.items():
                    if not isinstance(ac, MetaAgentClass):
                        continue

                    meta = ac.meta or {}

                    cur.execute(
                        """
                        INSERT INTO flowmeta.agent_class
                            (code, domain, dsl_code, description,
                             allow_effects, deny_effects, meta)
                        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (code) DO UPDATE
                           SET domain        = EXCLUDED.domain,
                               dsl_code      = EXCLUDED.dsl_code,
                               description   = EXCLUDED.description,
                               allow_effects = EXCLUDED.allow_effects,
                               deny_effects  = EXCLUDED.deny_effects,
                               meta          = flowmeta.agent_class.meta || EXCLUDED.meta,
                               updated_at    = now();
                        """,
                        (
                            ac_code,
                            ac.domain,
                            ac.dsl_code,
                            ac.description,
                            ac.allow_effects,
                            ac.deny_effects,
                            json.dumps(meta),
                        ),
                    )
                    result.agent_classes += 1

                # --- Классы планов -------------------------------------------
                for pc_code, pc in world.plan_classes.items():
                    if not isinstance(pc, MetaPlanClass):
                        continue

                    meta = pc.meta or {}

                    cur.execute(
                        """
                        INSERT INTO flowmeta.plan_class
                            (code, dsl_code, description, default_effects, meta)
                        VALUES (%s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (code) DO UPDATE
                           SET dsl_code        = EXCLUDED.dsl_code,
                               description     = EXCLUDED.description,
                               default_effects = EXCLUDED.default_effects,
                               meta            = flowmeta.plan_class.meta || EXCLUDED.meta,
                               updated_at      = now();
                        """,
                        (
                            pc_code,
                            pc.dsl_code,
                            pc.description,
                            pc.default_effects,
                            json.dumps(meta),
                        ),
                    )
                    result.plan_classes += 1

        return result
    finally:
        try:
            conn.close()
        except Exception:
            pass


def sync_from_meta(
    meta_path: Optional[Path] = None,
) -> Dict[str, int]:
    """
    Высокоуровневая функция: parse .meta -> upsert в flowmeta.* -> вернуть счётчики.
    """
    if meta_path is None:
        meta_path = Path("config/flowmeta/flowmeta.meta")

    world = load_world_from_meta(meta_path)
    result = persist_world_to_db(world)
    return result.to_dict()


def main(argv: Optional[list[str]] = None) -> None:
    """
    CLI-режим:

        docker compose exec worker bash -lc "cd /app && python -m src.flowlang.meta_sync"

    По умолчанию читает config/flowmeta/flowmeta.meta и синхронизирует мир в БД.
    """
    import sys as _sys

    if argv is None:
        argv = _sys.argv[1:]

    meta_path = Path(argv[0]) if argv else Path("config/flowmeta/flowmeta.meta")
    counts = sync_from_meta(meta_path)

    print(json.dumps({"meta_path": str(meta_path), "synced": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
