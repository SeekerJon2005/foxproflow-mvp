# FoxProFlow — Состояние проекта и план выравнивания (на 2025-09-25)

## 1) Текущее состояние (снимок)
- **Инфраструктура (Docker Compose):**
  - `foxproflow-postgres` — PostgreSQL 15 (healthy), порт 5432.
  - `foxproflow-redis` — Redis 7 (healthy), порт 6379.
  - `foxproflow-pgadmin` — pgAdmin, http://localhost:5050.
  - `foxproflow-api` — контейнер API перезапускается (reason: несогласованность кода/окружения внутри контейнера).
- **Локальный API (uvicorn)** — запускается и отвечает (`/health` ok), ручки `/freights`, `/freights/{fid}` готовы (асинхронные, `asyncpg`).
- **База данных:**
  - Ядро транспорта создано по `init_transport.sql`: `vehicles`, `drivers`, `managers`, `trips`, `trip_segments`, `gps_events`, `gps_daily`, `market_rates`, `kpi_baseline`.
  - В БД уже существует **VIEW** `freights_enriched`, которое строится из таблиц `freights`, `macro_data`, `transport_demand` (LATERAL JOIN по ближайшим датам).
  - Из-за того, что `freights_enriched` — *view*, к нему нельзя создавать индексы; вставка данных в view невозможна по определению.

## 2) Целевая картина данных (MVP транспортного ядра)
- **Сырые рыночные данные** → `freights` (ATI.su и др.).
- **Макро‑показатели** → `macro_data` (usd/eur/fuel по дате).
- **Транспортный спрос по регионам** → `transport_demand` (trucks_available/requests по региону/дате).
- **Обогащение для чтения API** → `freights_enriched_mv` (MATERIALIZED VIEW с индексами; селект = текущее view).
- **Транспортное ядро** → `vehicles`, `drivers`, `managers`, `trips`, `trip_segments`, `gps_events`, `gps_daily`, `market_rates`, `kpi_baseline`.

## 3) Проблемы/несоответствия
- API‑контейнер `foxproflow-api` стартует как `uvicorn app.main:app` и перезапускается: внутри образа ожидается другой layout/драйвер БД (`+psycopg2`), а актуальный код и `.env` используют `+asyncpg` и `src.api.main`.
- `freights_enriched` — это **VIEW**. Мы пытались создать TABLE с тем же именем, из‑за чего появились ошибки индексов/вставок. Для производительности и стабильности лучше создать **MATERIALIZED VIEW** с индексами и переключить API на него.
- Типы полей в сырой таблице `freights` вероятно не идеальны (например, `loading_date` может быть `text` → нужен `timestamptz`).

## 4) Что уже реализовано (согласно репозиторию и SQL‑аддендуму)
- База транспортного ядра и GPS (DDL + индексы), базовые таблицы ставок и KPI. 
- Тонкий слой API с ручками `/freights`, `/freights/{fid}`, а также каркас транспортного API из аддендума.
- Логика асинхронного доступа к БД (`asyncpg`) и pydantic‑схемы для `/freights`.
- Docker Compose‑окружение (Postgres, Redis, pgAdmin, API).

## 5) Блоки, которые можно сделать быстро и правильно
1. **Материализованное представление `freights_enriched_mv`** + индексы; переключить API на чтение из него.
2. **Заполнение `macro_data`** (usd, eur, fuel) по календарю — ежедневная строка; простая загрузка CSV/SQL.
3. **Заполнение `transport_demand`** по регионам (trucks_available/requests), например, агрегируя текущие грузы/транспорт за день.
4. **Агрегатор `market_rates`** на основе `freights` (p50/p75/p90 `руб/км` по паре регионов + тип ТС).
5. **Ручка `/api/advice/next-loads`** («умный блок v0.1») — ранжирование по `руб/час`/`руб/км`, штраф порожняку, бонус surge.

## 6) Пошаговый план выравнивания (1–2 дня)
**D0 (сегодня):**
- Создать `freights_enriched_mv` и индексы, переключить API на mv (см. прилагаемый SQL).
- Привести `.env` в контейнере API к `postgresql+asyncpg://...` и указать правильный модуль запуска (`src.api.main:app`) или использовать локальный uvicorn для разработки.

**D1:**
- Наполнить `macro_data` и `transport_demand` (минимальный CSV → SQL).
- Добавить `/api/advice/next-loads` и подключить скоринг к `freights_enriched_mv`.
- Настроить регламентный `REFRESH MATERIALIZED VIEW` (например, каждый час).

## 7) Команды (Docker + psql)
```powershell
# применить SQL (копируем файл внутрь контейнера → выполняем)
docker cp sql_bootstrap_business.sql foxproflow-postgres:/tmp/sql_bootstrap_business.sql
docker exec -it foxproflow-postgres psql -U admin -d foxproflow -v ON_ERROR_STOP=1 -f /tmp/sql_bootstrap_business.sql

# проверить
docker exec -it foxproflow-postgres psql -U admin -d foxproflow -c "SELECT count(*) FROM freights_enriched_mv;"
docker exec -it foxproflow-postgres psql -U admin -d foxproflow -c "REFRESH MATERIALIZED VIEW CONCURRENTLY freights_enriched_mv;"
```

## 8) Что поменять в коде (минимум)
- В `src/api/app/repo.py`: заменить `FROM freights_enriched` → `FROM freights_enriched_mv`.
- Убедиться, что `order_by=parsed_at` работает (поле есть в mv).

## 9) Наблюдаемость
- `EXPLAIN ANALYZE` на ключевые запросы `/freights` (после индексов на mv).
- Метрики API (latency, rate, error) — позже через Prometheus/Grafana.
