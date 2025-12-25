-- 20251208_dev_dev_order_core_v1.sql
-- Базовая таблица dev.dev_order для DevFactory DevOrders API.
-- Ненарушающая миграция (NDC): только CREATE IF NOT EXISTS.

BEGIN;

CREATE SCHEMA IF NOT EXISTS dev;

CREATE TABLE IF NOT EXISTS dev.dev_order (
    dev_order_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),

    status       text NOT NULL,
    title        text NOT NULL,
    description  text,
    customer_name text,

    total_amount   numeric(18,2),
    currency_code  text,

    -- внешний идентификатор заказчика/тенанта (строка, связывается через link-функции)
    tenant_id      text,

    CONSTRAINT dev_order_status_not_empty CHECK (length(status) > 0),
    CONSTRAINT dev_order_title_not_empty  CHECK (length(title)  > 0)
);

-- автообновление updated_at при UPDATE
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_dev_order_set_updated_at'
    ) THEN
        CREATE OR REPLACE FUNCTION dev.fn_dev_order_set_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $f$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $f$;

        CREATE TRIGGER trg_dev_order_set_updated_at
        BEFORE UPDATE ON dev.dev_order
        FOR EACH ROW
        EXECUTE FUNCTION dev.fn_dev_order_set_updated_at();
    END IF;
END;
$$;

COMMIT;
