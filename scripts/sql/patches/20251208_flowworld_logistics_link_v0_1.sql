-- 20251208_flowworld_logistics_link_v0_1.sql
-- FlowWorld ↔ Logistics link: таблица world.trip_links
-- stack=sql-postgres
-- goal=Создать таблицу world.trip_links для связи рейсов/ТС с пространствами/объектами FlowWorld
-- summary=Создаёт таблицу world.trip_links; не добавляет жёстких FK к logistics.*, если их нет; idempotent.

DO $$
BEGIN
    ----------------------------------------------------------------------
    -- 0. Убеждаемся, что схема world уже существует
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.schemata
        WHERE schema_name = 'world'
    ) THEN
        EXECUTE 'CREATE SCHEMA world';
    END IF;

    ----------------------------------------------------------------------
    -- 1. Таблица world.trip_links
    --
    -- Связывает:
    --   - логистический объект (рейс/ТС) через числовые id и тип,
    --   - пространство/объект FlowWorld (space_id/object_id),
    --   - тип связи (origin/destination/parking/base/other).
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'world'
          AND table_name   = 'trip_links'
    ) THEN
        EXECUTE $DDL$
            CREATE TABLE world.trip_links (
                id           bigserial PRIMARY KEY,
                -- Логистический объект
                entity_type  text      NOT NULL,  -- 'trip' | 'vehicle' | 'load' | 'other'
                entity_id    bigint    NOT NULL,
                -- Привязка к FlowWorld
                space_id     bigint    NOT NULL REFERENCES world.spaces(id) ON DELETE CASCADE,
                object_id    bigint        NULL REFERENCES world.objects(id) ON DELETE SET NULL,
                relation     text      NOT NULL DEFAULT 'origin', -- 'origin' | 'destination' | 'parking' | 'base' | ...
                meta         jsonb     NOT NULL DEFAULT '{}'::jsonb,
                created_at   timestamptz NOT NULL DEFAULT now(),
                updated_at   timestamptz NOT NULL DEFAULT now()
            );
        $DDL$;
    END IF;

    ----------------------------------------------------------------------
    -- 2. Триггер updated_at для world.trip_links (опционально)
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'world'
          AND p.proname = 'set_updated_at'
    ) THEN
        EXECUTE $FN$
            CREATE OR REPLACE FUNCTION world.set_updated_at()
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
        WHERE event_object_schema = 'world'
          AND event_object_table  = 'trip_links'
          AND trigger_name        = 'trg_world_trip_links_set_updated_at'
    ) THEN
        EXECUTE $TRG$
            CREATE TRIGGER trg_world_trip_links_set_updated_at
            BEFORE UPDATE ON world.trip_links
            FOR EACH ROW
            EXECUTE PROCEDURE world.set_updated_at();
        $TRG$;
    END IF;

END;
$$ LANGUAGE plpgsql;
