-- 20251212_logistics_autoplan_engine_v0_2.sql
-- DevTask: 92
-- Создал Архитектор: Яцков Евгений Анатольевич
-- Назначение: DB-engine автоплана v0.2 (advisory-only) + история прогонов
-- NDC: add-only таблицы; function replace допустим (сигнатура сохраняется)
-- FIX: reserved keyword "window" -> используем plan_window (и делаем compat-rename для старых черновиков)

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS logistics;

-- Опционально: реальные ТС (движок умеет работать и без них — через virtual vehicles)
CREATE TABLE IF NOT EXISTS logistics.vehicles (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    vehicle_code    text NOT NULL UNIQUE,
    region          text,
    available_from  timestamptz,
    is_active       boolean NOT NULL DEFAULT true,
    meta            jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_logistics_vehicles_available_from
    ON logistics.vehicles (available_from);

CREATE INDEX IF NOT EXISTS idx_logistics_vehicles_is_active
    ON logistics.vehicles (is_active);

-- Лог прогонов автоплана
CREATE TABLE IF NOT EXISTS logistics.autoplan_run (
    run_id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),

    requested_date      date,
    plan_window         text NOT NULL DEFAULT 'day',
    window_start        timestamptz,
    window_end          timestamptz,

    ok                  boolean NOT NULL DEFAULT false,
    loads_considered    integer NOT NULL DEFAULT 0,
    vehicles_count      integer NOT NULL DEFAULT 0,
    assignments_count   integer NOT NULL DEFAULT 0,
    delayed_assignments integer NOT NULL DEFAULT 0,
    avg_start_delay_min numeric(12,2),

    error               text,
    payload             jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Compat: если где-то ранее успели создать колонку "window" (в кавычках) — переименуем в plan_window
DO $$
BEGIN
    IF to_regclass('logistics.autoplan_run') IS NOT NULL THEN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'logistics'
              AND table_name   = 'autoplan_run'
              AND column_name  = 'window'
        )
        AND NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'logistics'
              AND table_name   = 'autoplan_run'
              AND column_name  = 'plan_window'
        )
        THEN
            EXECUTE 'ALTER TABLE logistics.autoplan_run RENAME COLUMN "window" TO plan_window';
        END IF;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_autoplan_run_created_at
    ON logistics.autoplan_run (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_autoplan_run_requested_date
    ON logistics.autoplan_run (requested_date);

-- Результат назначений автоплана
CREATE TABLE IF NOT EXISTS logistics.autoplan_assignment (
    id                   bigserial PRIMARY KEY,
    run_id               uuid NOT NULL REFERENCES logistics.autoplan_run(run_id) ON DELETE CASCADE,

    vehicle_id           uuid NULL REFERENCES logistics.vehicles(id),
    vehicle_code         text NOT NULL,

    load_id              uuid NOT NULL,
    seq                  integer NOT NULL,

    planned_pickup_at    timestamptz,
    planned_delivery_at  timestamptz,

    start_delay_min      integer NOT NULL DEFAULT 0,
    note                 text,
    payload              jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_autoplan_assignment_run
    ON logistics.autoplan_assignment (run_id);

CREATE INDEX IF NOT EXISTS idx_autoplan_assignment_vehicle_seq
    ON logistics.autoplan_assignment (vehicle_code, seq);

CREATE INDEX IF NOT EXISTS idx_autoplan_assignment_load
    ON logistics.autoplan_assignment (load_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'autoplan_assignment_run_vehicle_seq_uniq'
          AND conrelid = 'logistics.autoplan_assignment'::regclass
    ) THEN
        ALTER TABLE logistics.autoplan_assignment
            ADD CONSTRAINT autoplan_assignment_run_vehicle_seq_uniq
            UNIQUE (run_id, vehicle_code, seq);
    END IF;
END;
$$;

-- DB-engine v0.2: greedy assignment (advisory-only, НЕ пишет в public.trips)
CREATE OR REPLACE FUNCTION logistics.logistics_apply_autoplan(
    p_date   date,
    p_window text DEFAULT 'day'::text
)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_window   text := COALESCE(NULLIF(trim(both from p_window), ''), 'day');
    v_now      timestamptz := now();
    v_start    timestamptz;
    v_end      timestamptz;

    v_run_id   uuid := gen_random_uuid();

    v_vehicle_count int := 0;
    v_virtual_count int := 0;

    v_load_count int := 0;
    v_assignments int := 0;

    v_delayed int := 0;
    v_delay_sum int := 0;

    r_load    record;
    r_vehicle record;

    v_pickup   timestamptz;
    v_delivery timestamptz;

    v_delay_min int;
    v_seq int;
    v_next_available timestamptz;
BEGIN
    -- окно планирования
    IF v_window = 'rolling24' THEN
        v_start := date_trunc('minute', v_now);
        v_end   := v_start + interval '24 hours';
    ELSIF v_window = 'rolling48' THEN
        v_start := date_trunc('minute', v_now);
        v_end   := v_start + interval '48 hours';
    ELSE
        v_start := (p_date::timestamptz);
        v_end   := v_start + interval '1 day';
    END IF;

    INSERT INTO logistics.autoplan_run(
        run_id, requested_date, plan_window, window_start, window_end, ok
    )
    VALUES (
        v_run_id, p_date, v_window, v_start, v_end, false
    );

    -- состояние доступности ТС (реальные или виртуальные)
    CREATE TEMP TABLE tmp_vehicle_state (
        vehicle_id     uuid,
        vehicle_code   text,
        available_from timestamptz
    ) ON COMMIT DROP;

    INSERT INTO tmp_vehicle_state(vehicle_id, vehicle_code, available_from)
    SELECT
        v.id,
        v.vehicle_code,
        COALESCE(v.available_from, v_start)
    FROM logistics.vehicles v
    WHERE v.is_active
    ORDER BY COALESCE(v.available_from, v_start), v.vehicle_code;

    GET DIAGNOSTICS v_vehicle_count = ROW_COUNT;

    IF v_vehicle_count = 0 THEN
        v_virtual_count := 5;

        INSERT INTO tmp_vehicle_state(vehicle_id, vehicle_code, available_from)
        SELECT
            NULL::uuid,
            ('VIRTUAL-' || lpad(gs::text, 3, '0'))::text,
            v_start
        FROM generate_series(1, v_virtual_count) gs;

        v_vehicle_count := v_virtual_count;
    END IF;

    -- greedy assignment: loads -> vehicles
    FOR r_load IN
        SELECT
            l.id AS load_id,
            l.pickup_planned_at,
            l.delivery_planned_at,
            l.status
        FROM logistics.loads l
        WHERE l.pickup_planned_at IS NOT NULL
          AND l.delivery_planned_at IS NOT NULL
          AND l.pickup_planned_at >= v_start
          AND l.pickup_planned_at <  v_end
          AND l.status NOT IN ('delivered', 'cancelled')
        ORDER BY l.pickup_planned_at, l.delivery_planned_at, l.id
        LIMIT 500
    LOOP
        v_load_count := v_load_count + 1;

        v_pickup   := r_load.pickup_planned_at;
        v_delivery := r_load.delivery_planned_at;

        -- выбираем ТС: сначала те, кто уже доступен к pickup, иначе — кто станет доступен раньше
        SELECT vehicle_id, vehicle_code, available_from
        INTO r_vehicle
        FROM tmp_vehicle_state
        ORDER BY (available_from > v_pickup) ASC, available_from ASC, vehicle_code ASC
        LIMIT 1;

        IF NOT FOUND THEN
            CONTINUE;
        END IF;

        v_delay_min := GREATEST(
            0,
            floor(extract(epoch from (r_vehicle.available_from - v_pickup)) / 60)::int
        );

        IF v_delay_min > 0 THEN
            v_delayed := v_delayed + 1;
            v_delay_sum := v_delay_sum + v_delay_min;
        END IF;

        SELECT COALESCE(MAX(a.seq), 0) + 1
        INTO v_seq
        FROM logistics.autoplan_assignment a
        WHERE a.run_id = v_run_id
          AND a.vehicle_code = r_vehicle.vehicle_code;

        INSERT INTO logistics.autoplan_assignment(
            run_id, vehicle_id, vehicle_code,
            load_id, seq,
            planned_pickup_at, planned_delivery_at,
            start_delay_min,
            note
        )
        VALUES (
            v_run_id,
            r_vehicle.vehicle_id,
            r_vehicle.vehicle_code,
            r_load.load_id,
            v_seq,
            v_pickup,
            v_delivery,
            v_delay_min,
            CASE WHEN v_delay_min > 0 THEN 'vehicle_not_ready_by_pickup' ELSE NULL END
        );

        v_assignments := v_assignments + 1;

        -- апдейт доступности ТС: delivery + небольшой буфер
        v_next_available := v_delivery + interval '30 minutes';

        UPDATE tmp_vehicle_state
        SET available_from = v_next_available
        WHERE vehicle_code = r_vehicle.vehicle_code;
    END LOOP;

    UPDATE logistics.autoplan_run
    SET
        ok = true,
        loads_considered = v_load_count,
        vehicles_count = v_vehicle_count,
        assignments_count = v_assignments,
        delayed_assignments = v_delayed,
        avg_start_delay_min = CASE
            WHEN v_delayed > 0 THEN round((v_delay_sum::numeric / v_delayed::numeric), 2)
            ELSE 0
        END,
        payload = jsonb_build_object(
            'virtual_vehicles_used', (v_virtual_count > 0),
            'virtual_vehicles_count', v_virtual_count,
            'limit_loads', 500
        )
    WHERE run_id = v_run_id;

    RETURN jsonb_build_object(
        'ok', true,
        'mode', 'autoplan_db_v0_2',
        'date', to_char(p_date, 'YYYY-MM-DD'),
        'window', v_window,
        'run_id', v_run_id,
        'summary', jsonb_build_object(
            'window_start', v_start,
            'window_end', v_end,
            'loads_considered', v_load_count,
            'vehicles_count', v_vehicle_count,
            'assignments_count', v_assignments,
            'delayed_assignments', v_delayed,
            'avg_start_delay_min', CASE
                WHEN v_delayed > 0 THEN round((v_delay_sum::numeric / v_delayed::numeric), 2)
                ELSE 0
            END
        ),
        'assignments_sample', (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'vehicle_code', a.vehicle_code,
                        'seq', a.seq,
                        'load_id', a.load_id,
                        'pickup_planned_at', a.planned_pickup_at,
                        'delivery_planned_at', a.planned_delivery_at,
                        'start_delay_min', a.start_delay_min
                    )
                    ORDER BY a.vehicle_code, a.seq
                ),
                '[]'::jsonb
            )
            FROM (
                SELECT *
                FROM logistics.autoplan_assignment
                WHERE run_id = v_run_id
                ORDER BY vehicle_code, seq
                LIMIT 100
            ) a
        )
    );

EXCEPTION WHEN OTHERS THEN
    UPDATE logistics.autoplan_run
    SET ok = false,
        error = SQLSTATE || ': ' || SQLERRM
    WHERE run_id = v_run_id;

    RETURN jsonb_build_object(
        'ok', false,
        'mode', 'autoplan_db_v0_2',
        'date', to_char(p_date, 'YYYY-MM-DD'),
        'window', v_window,
        'run_id', v_run_id,
        'error', SQLSTATE || ': ' || SQLERRM
    );
END;
$$;

COMMIT;
