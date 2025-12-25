-- 20251206_devfactory_orders_core_v1.sql
-- NDC-патч: ядро заказов DevFactory и связь "заказ → dev.dev_task".
-- stack=sql
-- domain=devfactory
-- goal=Ввести dev.dev_order и dev.dev_order_tasks для привязки задач DevFactory к рыночным заказам.

CREATE SCHEMA IF NOT EXISTS dev;

-- 1. Таблица dev.dev_order — заказ DevFactory (рыночный уровень)
CREATE TABLE IF NOT EXISTS dev.dev_order (
    dev_order_id   uuid PRIMARY KEY,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    -- Привязка к клиенту/tenant (если заказ идёт от конкретного клиента SaaS)
    tenant_id      text,
    customer_name  text,

    -- Внешняя ссылка на CRM/Billing:
    -- deal_id, invoice_number, payment_id или любой другой внешний идентификатор
    external_ref   text,

    -- Человеческое описание заказа
    title          text NOT NULL,
    description    text,

    -- Статус жизненного цикла заказа DevFactory:
    -- draft            — черновик, ещё не выставлен счёт
    -- awaiting_payment — счёт выставлен, ждём оплаты
    -- paid             — заказ оплачен
    -- in_progress      — DevFactory выполняет задачи
    -- done             — все задачи выполнены и приняты
    -- cancelled        — заказ отменён
    status         text NOT NULL CHECK (
        status IN (
            'draft',
            'awaiting_payment',
            'paid',
            'in_progress',
            'done',
            'cancelled'
        )
    ),

    -- Финансовые параметры (опционально, можно заполнять позже)
    total_amount   numeric(18,2),
    currency_code  text, -- 'RUB','USD','EUR', ...

    -- Дополнительные метаданные (теги, приоритет, канал продажи, и т.п.)
    meta           jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_dev_order_status
    ON dev.dev_order(status);

CREATE INDEX IF NOT EXISTS idx_dev_order_tenant
    ON dev.dev_order(tenant_id);

CREATE INDEX IF NOT EXISTS idx_dev_order_external_ref
    ON dev.dev_order(external_ref);

-- 2. Связка "заказ → задачи DevFactory"
CREATE TABLE IF NOT EXISTS dev.dev_order_tasks (
    dev_order_id uuid NOT NULL REFERENCES dev.dev_order(dev_order_id) ON DELETE CASCADE,
    dev_task_id  uuid NOT NULL REFERENCES dev.dev_task(id)           ON DELETE CASCADE,

    added_at     timestamptz NOT NULL DEFAULT now(),
    relation_kind text, -- например: 'primary', 'support', 'bugfix', ...

    PRIMARY KEY (dev_order_id, dev_task_id)
);

CREATE INDEX IF NOT EXISTS idx_dev_order_tasks_task
    ON dev.dev_order_tasks(dev_task_id);
