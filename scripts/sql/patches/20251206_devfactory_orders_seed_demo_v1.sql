-- 20251206_devfactory_orders_seed_demo_v1.sql
-- NDC-патч: добавить уникальность external_ref для dev.dev_order
-- и создать внутренний демо-заказ DevFactory, связанный с существующей задачей.
-- stack=sql
-- domain=devfactory
-- goal=Ввести внутренний demo-заказ DevFactory и связать его с dev.dev_task.

-- 1. Обеспечиваем доступность gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Уникальность external_ref для dev.dev_order (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'dev_order_external_ref_uniq'
          AND conrelid = 'dev.dev_order'::regclass
    ) THEN
        ALTER TABLE dev.dev_order
        ADD CONSTRAINT dev_order_external_ref_uniq UNIQUE(external_ref);
    END IF;
END;
$$;

-- 3. Внутренний демо-заказ DevFactory
--    external_ref = 'DEVF-DEMO-001'
WITH new_order AS (
    INSERT INTO dev.dev_order(
        dev_order_id,
        created_at,
        updated_at,
        tenant_id,
        customer_name,
        external_ref,
        title,
        description,
        status,
        total_amount,
        currency_code,
        meta
    )
    VALUES (
        gen_random_uuid(),
        now(),
        now(),
        NULL, -- tenant_id (внутренний заказ)
        'Internal Demo',
        'DEVF-DEMO-001',
        'DevFactory demo order 001',
        'Внутренний демонстрационный заказ DevFactory для проверки портала, FlowSec и связки dev_order → dev_task.',
        'in_progress',
        NULL,
        NULL,
        '{"kind":"internal_demo","scope":"devfactory"}'::jsonb
    )
    ON CONFLICT (external_ref) DO UPDATE
        SET updated_at = EXCLUDED.updated_at
    RETURNING dev_order_id
)

-- 4. Привязка демо-заказа к конкретной dev.dev_task
--    Используем уже существующую задачу:
--    "Пример: внутренний dev-task для демонстрации DevFactory"
--    id = b2e84e28-b1ee-4a0d-8af9-e91ff830d64c
INSERT INTO dev.dev_order_tasks(dev_order_id, dev_task_id, relation_kind)
SELECT
    new_order.dev_order_id,
    t.id,
    'primary'
FROM new_order
JOIN dev.dev_task t
  ON t.id = 'b2e84e28-b1ee-4a0d-8af9-e91ff830d64c'::uuid
ON CONFLICT (dev_order_id, dev_task_id) DO NOTHING;
