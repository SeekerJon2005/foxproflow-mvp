-- 20251207_flowsec_core_schema_v1.sql
-- Базовый скелет FlowSec: схема sec + таблица sec.subject_roles.
-- Минимум, необходимый для работы FlowSec middleware и seed-патча Architect.

DO $$
BEGIN
    ----------------------------------------------------------------------
    -- 0. Схема sec
    ----------------------------------------------------------------------
    PERFORM 1
    FROM pg_namespace
    WHERE nspname = 'sec';

    IF NOT FOUND THEN
        EXECUTE 'CREATE SCHEMA sec AUTHORIZATION admin';
    END IF;

    ----------------------------------------------------------------------
    -- 1. Таблица sec.subject_roles
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'sec'
          AND table_name   = 'subject_roles'
    ) THEN
        EXECUTE $DDL$
        CREATE TABLE sec.subject_roles (
            id           bigserial      PRIMARY KEY,
            -- тип субъекта (user / service / agent / tenant / api_key / ...)
            subject_type text           NOT NULL,
            -- идентификатор субъекта (login / uuid / service code / ...)
            subject_id   text           NOT NULL,
            -- код роли (devfactory_architect, devfactory_operator, system_admin, ...)
            role_code    text           NOT NULL,
            -- флаг активности связи субъект↔роль
            is_active    boolean        NOT NULL DEFAULT true,
            created_at   timestamptz    NOT NULL DEFAULT now()
        );
        $DDL$;
    END IF;

    ----------------------------------------------------------------------
    -- 2. Индексы для subject_roles
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'sec'
          AND c.relname = 'subject_roles_subject_idx'
    ) THEN
        EXECUTE '
            CREATE INDEX subject_roles_subject_idx
                ON sec.subject_roles (subject_type, subject_id);
        ';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'sec'
          AND c.relname = 'subject_roles_role_idx'
    ) THEN
        EXECUTE '
            CREATE INDEX subject_roles_role_idx
                ON sec.subject_roles (role_code)
                WHERE is_active = true;
        ';
    END IF;

END;
$$ LANGUAGE plpgsql;
