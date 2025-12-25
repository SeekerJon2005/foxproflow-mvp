-- 20251208_flowworld_v0_1_mvp.sql
-- FlowWorld v0.1 (MVP): схема world.spaces/world.objects + базовые данные
-- stack=sql-postgres
-- goal=Создать базовую схему FlowWorld (world.spaces/world.objects) и наполнить одним пространством и несколькими объектами
-- summary=Создаёт схему world, две таблицы и стартовые записи; idempotent, не изменяет существующие записи.

DO $$
BEGIN
    ----------------------------------------------------------------------
    -- 0. Схема world
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.schemata
        WHERE schema_name = 'world'
    ) THEN
        EXECUTE 'CREATE SCHEMA world';
    END IF;

    ----------------------------------------------------------------------
    -- 1. world.spaces — пространства (ферма/участок/база)
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'world'
          AND table_name   = 'spaces'
    ) THEN
        EXECUTE $DDL$
            CREATE TABLE world.spaces (
                id          bigserial PRIMARY KEY,
                code        text      NOT NULL UNIQUE,
                name        text      NOT NULL,
                description text,
                meta        jsonb     NOT NULL DEFAULT '{}'::jsonb,
                created_at  timestamptz NOT NULL DEFAULT now(),
                updated_at  timestamptz NOT NULL DEFAULT now()
            );
        $DDL$;
    END IF;

    ----------------------------------------------------------------------
    -- 2. world.objects — объекты внутри пространства
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'world'
          AND table_name   = 'objects'
    ) THEN
        EXECUTE $DDL$
            CREATE TABLE world.objects (
                id          bigserial PRIMARY KEY,
                space_id    bigint     NOT NULL REFERENCES world.spaces(id) ON DELETE CASCADE,
                code        text       NOT NULL UNIQUE,
                name        text       NOT NULL,
                kind        text       NOT NULL,
                lat         double precision,
                lon         double precision,
                meta        jsonb      NOT NULL DEFAULT '{}'::jsonb,
                created_at  timestamptz NOT NULL DEFAULT now(),
                updated_at  timestamptz NOT NULL DEFAULT now()
            );
        $DDL$;
    END IF;

    ----------------------------------------------------------------------
    -- 3. Базовое пространство и объекты (MVP)
    ----------------------------------------------------------------------
    -- Пространство: базовый участок/двор/ферма
    IF NOT EXISTS (
        SELECT 1 FROM world.spaces WHERE code = 'primorsk_base'
    ) THEN
        INSERT INTO world.spaces (code, name, description, meta)
        VALUES (
            'primorsk_base',
            'Приморск: базовая площадка FoxProFlow',
            'Участок/двор/ферма, на котором будут находиться дом, ворота, техника, роботы.',
            jsonb_build_object(
                'region', 'Приморск',
                'note',   'MVP-пространство FlowWorld; далее можно расширять.'
            )
        );
    END IF;

    -- Объекты в пространстве primorsk_base
    -- Дом
    IF NOT EXISTS (
        SELECT 1 FROM world.objects WHERE code = 'primorsk_house'
    ) THEN
        INSERT INTO world.objects (space_id, code, name, kind, lat, lon, meta)
        SELECT
            s.id,
            'primorsk_house',
            'Жилой дом',
            'building.house',
            NULL::double precision,
            NULL::double precision,
            jsonb_build_object(
                'floors', 2,
                'usage',  'residential'
            )
        FROM world.spaces s
        WHERE s.code = 'primorsk_base';
    END IF;

    -- Ворота/въезд
    IF NOT EXISTS (
        SELECT 1 FROM world.objects WHERE code = 'primorsk_gate'
    ) THEN
        INSERT INTO world.objects (space_id, code, name, kind, lat, lon, meta)
        SELECT
            s.id,
            'primorsk_gate',
            'Основные ворота',
            'infrastructure.gate',
            NULL::double precision,
            NULL::double precision,
            jsonb_build_object(
                'access', 'vehicles+people',
                'note',   'Точка входа на территорию'
            )
        FROM world.spaces s
        WHERE s.code = 'primorsk_base';
    END IF;

    -- Площадка под технику
    IF NOT EXISTS (
        SELECT 1 FROM world.objects WHERE code = 'primorsk_yard'
    ) THEN
        INSERT INTO world.objects (space_id, code, name, kind, lat, lon, meta)
        SELECT
            s.id,
            'primorsk_yard',
            'Технический двор/стоянка',
            'area.yard',
            NULL::double precision,
            NULL::double precision,
            jsonb_build_object(
                'capacity', '2-3 ТС/робота',
                'usage',    'parking+work'
            )
        FROM world.spaces s
        WHERE s.code = 'primorsk_base';
    END IF;

    -- Условный робот/агрегат
    IF NOT EXISTS (
        SELECT 1 FROM world.objects WHERE code = 'primorsk_robot_helper'
    ) THEN
        INSERT INTO world.objects (space_id, code, name, kind, lat, lon, meta)
        SELECT
            s.id,
            'primorsk_robot_helper',
            'Робот-помощник (виртуальный MVP)',
            'robot.helper',
            NULL::double precision,
            NULL::double precision,
            jsonb_build_object(
                'status', 'virtual',
                'note',   'Прототип для будущих реальных роботов.'
            )
        FROM world.spaces s
        WHERE s.code = 'primorsk_base';
    END IF;

END;
$$ LANGUAGE plpgsql;
