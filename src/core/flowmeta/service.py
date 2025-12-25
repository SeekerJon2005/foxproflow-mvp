from __future__ import annotations

from typing import Any, List

from .models import FlowMetaDomainWithEntities, FlowMetaEntity


def _normalize_raw_json(raw: Any) -> Any:
    """
    Приводит сырое значение из БД к python-структуре (list[dict]).
    flowmeta.fn_get_domain_entities_json() возвращает jsonb, но драйвер
    может отдать либо уже декодированный объект, либо строку JSON.
    """
    if raw is None:
        return []

    # Если пришла строка JSON — декодируем
    if isinstance(raw, str):
        import json

        return json.loads(raw)

    # Если это уже list/dict — используем как есть
    return raw


def parse_flowmeta_domains_with_entities(raw: Any) -> List[FlowMetaDomainWithEntities]:
    """
    Преобразует результат функции flowmeta.fn_get_domain_entities_json()
    в список Pydantic-моделей FlowMetaDomainWithEntities.
    """
    data = _normalize_raw_json(raw)

    if not isinstance(data, list):
        raise ValueError(
            "FlowMeta JSON должен быть массивом объектов доменов "
            "(ожидается list[dict])."
        )

    result: List[FlowMetaDomainWithEntities] = []

    for item in data:
        if not isinstance(item, dict):
            continue

        entities_raw = item.get("entities") or []
        entities: List[FlowMetaEntity] = []

        if isinstance(entities_raw, list):
            for e in entities_raw:
                if not isinstance(e, dict):
                    continue
                entities.append(
                    FlowMetaEntity(
                        entity_code=str(e.get("entity_code")),
                        title=e.get("title"),
                        description=e.get("description"),
                    )
                )

        domain = FlowMetaDomainWithEntities(
            code=str(item.get("code")),
            title=str(item.get("title") or ""),
            tier=item.get("tier"),
            importance=item.get("importance"),
            entities=entities,
        )
        result.append(domain)

    return result


async def fetch_flowmeta_domains_with_entities(db) -> List[FlowMetaDomainWithEntities]:
    """
    Загружает домены+сущности FlowMeta из БД через функцию
    flowmeta.fn_get_domain_entities_json().

    Параметр db сознательно обобщён:
    - это может быть databases.Database,
    - asyncpg connection / pool,
    - или другой асинхронный слой.

    Ориентируемся на интерфейс вида:
        row = await db.fetch_one(sql)

    Если у тебя другой интерфейс (fetchrow, execute и т.п.) — поправь
    всего несколько строк, оставив SQL и парсинг как есть.
    """
    sql = "SELECT flowmeta.fn_get_domain_entities_json() AS data;"

    row = await db.fetch_one(sql)  # <--- здесь адаптируй под свой db-layer при необходимости

    raw = None
    if row is None:
        raw = None
    elif isinstance(row, dict):
        raw = row.get("data")
    else:
        # Поддержка объектов-строк с доступом через индекс/атрибут
        try:
            raw = row["data"]  # type: ignore[index]
        except Exception:
            raw = getattr(row, "data", None)

    return parse_flowmeta_domains_with_entities(raw)
