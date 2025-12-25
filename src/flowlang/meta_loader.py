# -*- coding: utf-8 -*-
# file: src/flowlang/meta_loader.py
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .meta_model import (
    MetaWorld,
    MetaDomain,
    MetaDSL,
    MetaEffect,
    MetaAgentClass,
    MetaPlanClass,
    MetaPolicy,
)

__all__ = [
    "DBConfig",
    "MetaLoaderError",
    "build_world_from_rows",
    "load_world_from_conn",
    "load_world_from_dsn",
    "load_world_from_config",
    "main",
]

JsonDict = Dict[str, Any]

# Пытаемся аккуратно использовать внутреннее подключение FoxProFlow, если оно есть
try:  # pragma: no cover - зависит от структуры проекта
    from src.core.pg_conn import _connect_pg as _ff_connect_pg  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001 - нам любая ошибка одинаково говорит "не получилось"
    _ff_connect_pg = None  # type: ignore[assignment]


# =============================================================================
# Вспомогательные типы и ошибки для загрузчика
# =============================================================================


@dataclass
class DBConfig:
    """
    Простой контейнер для настроек подключения.

    dsn — строка подключения к Postgres.
    """
    dsn: str


class MetaLoaderError(Exception):
    """Базовая ошибка для meta_loader."""


# =============================================================================
# Универсальные функции fetch_* для DB-API соединения
# =============================================================================


def _rows_from_cursor(cur) -> List[JsonDict]:
    """
    Преобразует DB-API cursor (psycopg2/psycopg/другие) в список dict'ов.

    Ожидается, что после cur.execute(...) есть cur.description и cur.fetchall().
    """
    cols = [d[0] for d in cur.description]
    result: List[JsonDict] = []
    for row in cur.fetchall():
        result.append(dict(zip(cols, row)))
    return result


def _fetch_all(conn, sql: str) -> List[JsonDict]:
    """
    Выполняет SELECT и возвращает список dict'ов.

    conn — любой DB-API connection (psycopg2/psycopg/etc.).
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return _rows_from_cursor(cur)


# =============================================================================
# Построение MetaWorld из уже прочитанных строк (dict'ов)
# =============================================================================


def build_world_from_rows(
    *,
    domains: Iterable[Mapping[str, Any]],
    dsls: Iterable[Mapping[str, Any]],
    effects: Iterable[Mapping[str, Any]],
    agent_classes: Iterable[Mapping[str, Any]],
    plan_classes: Iterable[Mapping[str, Any]],
    policies: Iterable[Mapping[str, Any]],
    world_name: str = "foxproflow",
) -> MetaWorld:
    """
    Конструктор MetaWorld из заранее прочитанных строк (dict'ов).

    Удобен для тестов и для интеграции, где запросы к БД выполняются снаружи.
    """
    world = MetaWorld(world_name=world_name)

    # Домены
    for row in domains:
        dom = MetaDomain.from_row(dict(row))
        world.add_domain(dom)

    # DSL
    for row in dsls:
        dsl = MetaDSL.from_row(dict(row))
        world.add_dsl(dsl)

    # Эффекты
    for row in effects:
        eff = MetaEffect.from_row(dict(row))
        world.add_effect(eff)

    # Классы агентов
    for row in agent_classes:
        ac = MetaAgentClass.from_row(dict(row))
        world.add_agent_class(ac)

    # Классы планов
    for row in plan_classes:
        pc = MetaPlanClass.from_row(dict(row))
        world.add_plan_class(pc)

    # Политики
    for row in policies:
        pol = MetaPolicy.from_row(dict(row))
        world.add_policy(pol)

    return world


# =============================================================================
# Загрузка MetaWorld из DB-API соединения
# =============================================================================


def load_world_from_conn(conn, world_name: str = "foxproflow") -> MetaWorld:
    """
    Загружает MetaWorld из БД Postgres через уже открытое DB-API соединение.

    Никаких изменений в БД не делает — только SELECT из flowmeta.*.
    """
    domain_rows = _fetch_all(conn, "SELECT * FROM flowmeta.domain ORDER BY code;")
    dsl_rows = _fetch_all(conn, "SELECT * FROM flowmeta.dsl ORDER BY code;")
    effect_rows = _fetch_all(conn, "SELECT * FROM flowmeta.effect_type ORDER BY code;")
    agent_rows = _fetch_all(conn, "SELECT * FROM flowmeta.agent_class ORDER BY code;")
    plan_rows = _fetch_all(conn, "SELECT * FROM flowmeta.plan_class ORDER BY code;")
    policy_rows = _fetch_all(conn, "SELECT * FROM flowmeta.policy ORDER BY code;")

    return build_world_from_rows(
        domains=domain_rows,
        dsls=dsl_rows,
        effects=effect_rows,
        agent_classes=agent_rows,
        plan_classes=plan_rows,
        policies=policy_rows,
        world_name=world_name,
    )


# =============================================================================
# Подключение к БД по DSN (psycopg / psycopg2) + fallback на _connect_pg
# =============================================================================


@contextmanager
def _connect_via_dsn(dsn: str):
    """
    Обёртка над psycopg (v3) / psycopg2.

    Пытается сначала psycopg (v3), затем psycopg2. Если ничего нет — MetaLoaderError.
    """
    # Сначала пробуем psycopg (v3)
    try:
        import psycopg  # type: ignore[import]

        conn = psycopg.connect(dsn)
        try:
            yield conn
        finally:
            conn.close()
        return
    except ModuleNotFoundError:
        pass
    except Exception as exc:  # pragma: no cover - неожиданная ошибка psycopg
        raise MetaLoaderError(f"Ошибка подключения через psycopg: {exc}") from exc

    # Затем пробуем psycopg2
    try:
        import psycopg2  # type: ignore[import]

        conn = psycopg2.connect(dsn)
        try:
            yield conn
        finally:
            conn.close()
        return
    except ModuleNotFoundError as exc:  # pragma: no cover - зависит от окружения
        raise MetaLoaderError(
            "Не удалось импортировать ни psycopg, ни psycopg2. "
            "Установи 'psycopg[binary]' или 'psycopg2-binary', "
            "либо используй встроенное подключение FoxProFlow (_connect_pg)."
        ) from exc
    except Exception as exc:  # pragma: no cover
        raise MetaLoaderError(f"Ошибка подключения через psycopg2: {exc}") from exc


def load_world_from_dsn(dsn: str, world_name: str = "foxproflow") -> MetaWorld:
    """
    Удобный помощник: сам открывает соединение по DSN и загружает MetaWorld.
    """
    with _connect_via_dsn(dsn) as conn:
        return load_world_from_conn(conn, world_name=world_name)


def load_world_from_config(config: DBConfig, world_name: str = "foxproflow") -> MetaWorld:
    """
    Обёртка над load_world_from_dsn для случая, когда настройки обёрнуты в DBConfig.
    """
    return load_world_from_dsn(config.dsn, world_name=world_name)


def _get_dsn_from_env(
    primary_var: str = "FF_DB_DSN",
    fallback_var: str = "DATABASE_URL",
) -> str:
    """
    Берёт DSN из переменных окружения.

    Сначала FF_DB_DSN, потом DATABASE_URL. Если ничего нет — MetaLoaderError.
    """
    dsn = os.environ.get(primary_var) or os.environ.get(fallback_var)
    if not dsn:
        raise MetaLoaderError(
            f"Не найден DSN для БД: ни {primary_var}, ни {fallback_var} не заданы."
        )
    return dsn


def _load_world_auto(world_name: str = "foxproflow") -> MetaWorld:
    """
    Автоматический выбор стратегии подключения:

    1. Если есть FF_DB_DSN / DATABASE_URL — подключаемся по DSN.
    2. Иначе, если доступен src.core.pg_conn._connect_pg — используем его.
    3. Иначе — MetaLoaderError.
    """
    # 1) пробуем взять DSN из окружения
    try:
        dsn = _get_dsn_from_env()
    except MetaLoaderError:
        dsn = ""

    if dsn:
        return load_world_from_dsn(dsn, world_name=world_name)

    # 2) пробуем встроенное подключение FoxProFlow
    if _ff_connect_pg is not None:
        conn = _ff_connect_pg()
        try:
            return load_world_from_conn(conn, world_name=world_name)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # 3) ничего не получилось
    raise MetaLoaderError(
        "Не удалось подключиться к БД FlowMeta: "
        "нет FF_DB_DSN/DATABASE_URL и недоступен src.core.pg_conn._connect_pg."
    )


# =============================================================================
# CLI: запуск через `python -m src.flowlang.meta_loader`
# =============================================================================


def main(argv: Optional[List[str]] = None) -> None:
    """
    Небольшая CLI-утилита: загружает MetaWorld и печатает summary.

    Варианты использования (в контейнере worker):

        # 1) через DSN
        FF_DB_DSN=postgresql://... docker compose exec worker \
            python -m src.flowlang.meta_loader

        # 2) без DSN, используя внутренний _connect_pg (если он есть)
        docker compose exec worker \
            python -m src.flowlang.meta_loader
    """
    from json import dumps

    world = _load_world_auto(world_name="foxproflow")
    summary = world.summary()  # метод из MetaWorld (meta_model.py)

    print(dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
