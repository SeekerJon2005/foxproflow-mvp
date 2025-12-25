from __future__ import annotations

from typing import Callable, Any, Sequence
from functools import wraps
import asyncio


async def flowsec_check_for_task(
    *,
    subject_type: str,
    subject_id: str,
    domain: str,
    actions: Sequence[str],
) -> None:
    """
    Асинхронная проверка FlowSec для Celery-задач.

    Вызывается из декоратора перед выполнением задачи.
    """
    # Ленивая загрузка, чтобы избежать циклов импортов и жёсткой привязки к worker.db.
    from src.api.security.flowsec_middleware import (
        check_policies_allowed,
        FlowSecSubject,
        get_db_conn,
    )

    db = await get_db_conn()
    subject = FlowSecSubject(
        subject_type=subject_type,
        subject_id=subject_id,
        roles=[],  # роли можно не подгружать отдельно, если v_subject_policies_effective уже всё считает
    )

    await check_policies_allowed(
        db=db,
        subject=subject,
        domain=domain,
        actions=actions,
    )


def flowsec_guard(
    *,
    domain: str,
    actions: Sequence[str],
    subject_type_kw: str = "subject_type",
    subject_id_kw: str = "subject_id",
):
    """
    Декоратор для Celery-задач.

    Пример:

        @app.task(bind=True)
        @flowsec_guard(domain="devfactory", actions=["apply_patch"])
        def devfactory_apply_patch(self, patch_id, subject_id=None, subject_type="user"):
            ...

    По умолчанию ожидает kwargs:
      - subject_type_kw: имя аргумента для типа субъекта (user/service/eri/ai_agent)
      - subject_id_kw:   имя аргумента для идентификатора субъекта
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            subject_type = kwargs.get(subject_type_kw, "service")
            subject_id = kwargs.get(subject_id_kw, "unknown")

            # В Celery-задаче мы находимся в sync-контексте,
            # поэтому в лоб дёргаем asyncio.run().
            asyncio.run(
                flowsec_check_for_task(
                    subject_type=subject_type,
                    subject_id=subject_id,
                    domain=domain,
                    actions=actions,
                )
            )
            return fn(*args, **kwargs)

        return wrapper

    return decorator
