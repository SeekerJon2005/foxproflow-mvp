-- 20251208_flowmeta_v0_2_base.sql
-- FlowMeta v0.2: базовая схема (schema + domain/entity) и функция upsert_entity()
-- stack=sql-postgres
-- goal=Создать базовую схему flowmeta (domain/entity) и функцию flowmeta.upsert_entity() для дальнейших патчей v1.1
-- summary=Создаёт схему flowmeta, таблицы domain/entity и функцию upsert_entity(); idempotent, не ломает существующие объекты.

DO $$
BEGIN
    ----------------------------------------------------------------------
    -- 0. Схема flowmeta
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.schemata
        WHERE schema_name = 'flowmeta'
    ) THEN
        EXECUTE 'CREATE SCHEMA flowmeta';
    END IF;

    ----------------------------------------------------------------------
    -- 1. Таблица flowmeta.domain (id, code, name, description, meta)
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'domain'
    ) THEN
        EXECUTE $DDL$
            CREATE TABLE flowmeta.domain (
                id          bigserial PRIMARY KEY,
                code        text      NOT NULL UNIQUE,
                name        text,
                description text,
                meta        jsonb     NOT NULL DEFAULT '{}'::jsonb,
                created_at  timestamptz NOT NULL DEFAULT now(),
                updated_at  timestamptz NOT NULL DEFAULT now()
            );
        $DDL$;
    END IF;

    ----------------------------------------------------------------------
    -- 2. Таблица flowmeta.entity (id, domain_code, code, name, description, kind, ref, meta)
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'entity'
    ) THEN
        EXECUTE $DDL$
            CREATE TABLE flowmeta.entity (
                id           bigserial PRIMARY KEY,
                domain_code  text      NOT NULL REFERENCES flowmeta.domain(code)
                                            ON UPDATE CASCADE ON DELETE CASCADE,
                code         text      NOT NULL,
                name         text,
                description  text,
                kind         text,
                ref          text,
                meta         jsonb     NOT NULL DEFAULT '{}'::jsonb,
                created_at   timestamptz NOT NULL DEFAULT now(),
                updated_at   timestamptz NOT NULL DEFAULT now(),
                UNIQUE (domain_code, code)
            );
        $DDL$;
    END IF;

    ----------------------------------------------------------------------
    -- 3. Функция для обновления updated_at (set_updated_at) + триггеры
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'flowmeta'
          AND p.proname = 'set_updated_at'
    ) THEN
        EXECUTE $FN$
            CREATE OR REPLACE FUNCTION flowmeta.set_updated_at()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $BODY$
            BEGIN
                NEW.updated_at := now();
                RETURN NEW;
            END;
            $BODY$;
        $FN$;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.triggers
        WHERE event_object_schema = 'flowmeta'
          AND event_object_table  = 'domain'
          AND trigger_name        = 'trg_flowmeta_domain_set_updated_at'
    ) THEN
        EXECUTE $TRG$
            CREATE TRIGGER trg_flowmeta_domain_set_updated_at
            BEFORE UPDATE ON flowmeta.domain
            FOR EACH ROW
            EXECUTE PROCEDURE flowmeta.set_updated_at();
        $TRG$;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.triggers
        WHERE event_object_schema = 'flowmeta'
          AND event_object_table  = 'entity'
          AND trigger_name        = 'trg_flowmeta_entity_set_updated_at'
    ) THEN
        EXECUTE $TRG$
            CREATE TRIGGER trg_flowmeta_entity_set_updated_at
            BEFORE UPDATE ON flowmeta.entity
            FOR EACH ROW
            EXECUTE PROCEDURE flowmeta.set_updated_at();
        $TRG$;
    END IF;

    ----------------------------------------------------------------------
    -- 4. Функция flowmeta.upsert_entity(domain_code, entity_code, name, description)
    ----------------------------------------------------------------------
    EXECUTE $FN$
        CREATE OR REPLACE FUNCTION flowmeta.upsert_entity(
            p_domain_code text,
            p_entity_code text,
            p_name        text,
            p_description text
        )
        RETURNS void
        LANGUAGE plpgsql
        AS $BODY$
        DECLARE
            v_domain_exists boolean;
        BEGIN
            -- гарантируем наличие домена
            SELECT TRUE
            INTO v_domain_exists
            FROM flowmeta.domain
            WHERE code = p_domain_code;

            IF NOT v_domain_exists THEN
                INSERT INTO flowmeta.domain (code, name, description)
                VALUES (p_domain_code, p_domain_code, NULL)
                ON CONFLICT (code) DO NOTHING;
            END IF;

            -- upsert сущности
            INSERT INTO flowmeta.entity (domain_code, code, name, description)
            VALUES (p_domain_code, p_entity_code, p_name, p_description)
            ON CONFLICT (domain_code, code)
            DO UPDATE
               SET name        = EXCLUDED.name,
                   description = EXCLUDED.description,
                   updated_at  = now();
        END;
        $BODY$;
    $FN$;

END;
$$ LANGUAGE plpgsql;
