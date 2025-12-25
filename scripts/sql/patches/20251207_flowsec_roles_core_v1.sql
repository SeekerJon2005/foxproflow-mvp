-- 20251207_flowsec_roles_core_v1.sql
-- Базовый справочник ролей FlowSec: sec.roles.
-- Минимум, необходимый для работы FlowSec middleware и seed-патчей.

DO $$
BEGIN
    ----------------------------------------------------------------------
    -- Убеждаемся, что схема sec существует (на случай, если патчи применяются вразнобой)
    ----------------------------------------------------------------------
    PERFORM 1
    FROM pg_namespace
    WHERE nspname = 'sec';

    IF NOT FOUND THEN
        EXECUTE 'CREATE SCHEMA sec AUTHORIZATION admin';
    END IF;

    ----------------------------------------------------------------------
    -- Таблица sec.roles
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'sec'
          AND table_name   = 'roles'
    ) THEN
        EXECUTE $DDL$
        CREATE TABLE sec.roles (
            role_code   text        PRIMARY KEY,
            title       text        NOT NULL,
            description text        NULL,
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        $DDL$;
    END IF;

END;
$$ LANGUAGE plpgsql;
