# -*- coding: utf-8 -*-
from __future__ import annotations
import os
from celery import shared_task

@shared_task(name="planner.hourly.replan.all")
def planner_hourly_replan_all() -> dict:
    """
    Минимальная заглушка часового реплана.
    На MVP просто возвращаем ok, чтобы не ломать пайплайн.
    Позже здесь вызываем ваш планировщик (SQL/py), который пишет в аудит.
    """
    return {"ok": True, "note": "planner stub (MVP)"}
