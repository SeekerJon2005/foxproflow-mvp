from typing import List, Optional
from pydantic import BaseModel


class FlowMetaEntity(BaseModel):
    """
    Сущность FlowMeta внутри домена.

    Соответствует строкам из flowmeta.entity и вложенному массиву entities[]
    функции flowmeta.fn_get_domain_entities_json().
    """

    entity_code: str
    title: Optional[str] = None
    description: Optional[str] = None


class FlowMetaDomain(BaseModel):
    """
    Домен FlowMeta.

    Соответствует flowmeta.domain: code/title/tier/importance.
    """

    code: str
    title: str
    tier: Optional[str] = None
    importance: Optional[str] = None


class FlowMetaDomainWithEntities(FlowMetaDomain):
    """
    Домен FlowMeta с вложенным списком сущностей.

    Это базовая модель для ответа API /api/flowmeta/domains-with-entities.
    """

    entities: List[FlowMetaEntity] = []
