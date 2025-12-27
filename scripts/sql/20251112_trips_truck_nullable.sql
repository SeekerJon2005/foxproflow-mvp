-- 2025-11-12 — Разрешаем NULL для truck_id на ранних стадиях и вводим условную проверку.
BEGIN;

ALTER TABLE public.trips
    ALTER COLUMN truck_id DROP NOT NULL;

-- Требуем truck_id на «рабочих» стадиях (пример: assigned/enroute/done)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'trips_truck_required_on_status'
          AND conrelid = 'public.trips'::regclass
    ) THEN
        ALTER TABLE public.trips
        ADD CONSTRAINT trips_truck_required_on_status
        CHECK ( status IN ('draft','confirmed') OR truck_id IS NOT NULL ) NOT VALID;
        ALTER TABLE public.trips VALIDATE CONSTRAINT trips_truck_required_on_status;
    END IF;
END$$;

COMMIT;
