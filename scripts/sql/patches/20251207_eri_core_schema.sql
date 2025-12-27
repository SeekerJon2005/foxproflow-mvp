-- scripts/sql/patches/20251207_eri_core_schema.sql
-- ERI Core v0.1 — базовая схема БД: сессии, режимы, профили политик.

BEGIN;

-- 0. Схема eri
CREATE SCHEMA IF NOT EXISTS eri;

-- 1. Режимы ERI (eri.mode)
--    Здесь мы фиксируем коды режимов и базовые флаги (child_safe, workspace и т.п.).
CREATE TABLE IF NOT EXISTS eri.mode (
    mode_code        text PRIMARY KEY,        -- 'adult', 'child', 'workspace', 'family', ...
    is_child_safe    boolean NOT NULL DEFAULT false,
    is_workspace     boolean NOT NULL DEFAULT false,
    is_system_mode   boolean NOT NULL DEFAULT false,
    meta             jsonb    NOT NULL DEFAULT '{}'::jsonb
);

-- 2. Профиль политик ERI (eri.policy_profile)
--    Профиль связывает режим с набором политик/ограничений в meta.
CREATE TABLE IF NOT EXISTS eri.policy_profile (
    policy_profile_id uuid PRIMARY KEY,
    name              text    NOT NULL,
    mode_code         text    NOT NULL,
    meta              jsonb   NOT NULL DEFAULT '{}'::jsonb
);

-- Простая FK-связь на eri.mode (без каскадов, чтобы не уронить ссылки случайно)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.table_constraints
        WHERE  constraint_schema = 'eri'
        AND    table_name        = 'policy_profile'
        AND    constraint_name   = 'eri_policy_profile_mode_fk'
    ) THEN
        ALTER TABLE eri.policy_profile
            ADD CONSTRAINT eri_policy_profile_mode_fk
            FOREIGN KEY (mode_code) REFERENCES eri.mode (mode_code);
    END IF;
END$$;

-- 3. Сессия ERI (eri.session)
--    Обезличенный сеанс: к какому tenant/каналу относится, какой режим и профиль политик.
CREATE TABLE IF NOT EXISTS eri.session (
    session_id        uuid PRIMARY KEY,
    created_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz NULL,

    -- контекст
    tenant_id         uuid        NULL,      -- ссылка на crm.tenant (логическая)
    channel_ref       text        NULL,      -- идентификатор канала FoxCom / внешнего чата

    -- режим и профиль политик
    mode_code         text        NOT NULL,
    policy_profile_id uuid        NULL,

    -- вспомогательное поле для гибкого расширения
    meta              jsonb       NOT NULL DEFAULT '{}'::jsonb
);

-- FK на eri.mode
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.table_constraints
        WHERE  constraint_schema = 'eri'
        AND    table_name        = 'session'
        AND    constraint_name   = 'eri_session_mode_fk'
    ) THEN
        ALTER TABLE eri.session
            ADD CONSTRAINT eri_session_mode_fk
            FOREIGN KEY (mode_code) REFERENCES eri.mode (mode_code);
    END IF;
END$$;

-- FK на eri.policy_profile (опционально, может быть NULL)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.table_constraints
        WHERE  constraint_schema = 'eri'
        AND    table_name        = 'session'
        AND    constraint_name   = 'eri_session_policy_profile_fk'
    ) THEN
        ALTER TABLE eri.session
            ADD CONSTRAINT eri_session_policy_profile_fk
            FOREIGN KEY (policy_profile_id) REFERENCES eri.policy_profile (policy_profile_id);
    END IF;
END$$;

-- Индексы для быстрых выборок по tenant/каналу
CREATE INDEX IF NOT EXISTS eri_session_tenant_idx
    ON eri.session (tenant_id);

CREATE INDEX IF NOT EXISTS eri_session_channel_idx
    ON eri.session (channel_ref);

CREATE INDEX IF NOT EXISTS eri_session_mode_idx
    ON eri.session (mode_code);

COMMIT;
