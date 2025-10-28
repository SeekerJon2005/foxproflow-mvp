# src/services/schedule.py
import os
from celery.schedules import crontab

# Beat-расписание FoxProFlow.
# Часовой пояс на стороне Celery задаётся через celery_app.py (CELERY_TIMEZONE).

BEAT_SCHEDULE = {
  # Прогнозные витрины: раз в 3 часа
  "forecast-refresh-3h": {
    "task": "forecast.refresh",
    "schedule": 60 * 60 * 3,
  },

  # NEW: доступность ТС — сначала рефрешим MV на HH:00
  "mv-availability-refresh-hourly": {
    "task": "mv.refresh.vehicle_availability",
    "schedule": crontab(minute=0),  # каждый час, на нулевой минуте
  },

  # Почасовой переплан всех ТС — после REFRESH MV (HH:05)
  "planner-hourly-replan-all": {
    "task": "planner.hourly.replan.all",
    "schedule": crontab(minute=5),  # на 05-й минуте каждого часа
  },
}
