-- 20251120_raw_freights_ati_raw.sql
-- NDC-скрипт: создание схемы raw и сырой таблицы freights_ati_raw
-- Источник данных: ATI (ежедневный парсер:
--   C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\src\parsers\ati_parser.py)
-- Потребитель: ETL CLI:
--   python -m src.cli.ati_etl daily --since-hours N --dsn %ATI_ETL_DSN%
-- Таблица по умолчанию: raw.freights_ati_raw

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.freights_ati_raw (
    source          text                     NOT NULL,
    source_uid      text                     NOT NULL,
    hash            text,
    loading_city    text,
    unloading_city  text,
    cargo           text,
    body_type       text,
    loading_date    text,
    weight          text,
    volume          text,
    price           text,
    parsed_at       timestamptz,
    payload         jsonb                    NOT NULL,
    PRIMARY KEY (source, source_uid)
);

-- Дополнительный индекс по hash можно включить, если будем активно искать
-- /агрегировать по hash (например, для дедупликации вне PK).
-- Пока оставляем закомментированным, чтобы не плодить лишние индексы.

-- CREATE INDEX IF NOT EXISTS freights_ati_raw_hash_idx
--     ON raw.freights_ati_raw (hash);
