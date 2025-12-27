-- 20251210_devfactory_billing_minimal_v1.sql
-- DevFactory Billing: минимальный биллинговый конвейер (инвойсы + импорт банковской выписки + матчинг)

BEGIN;

-- 1. Схема billing (на случай, если ещё не создана)
CREATE SCHEMA IF NOT EXISTS billing;

-- 2. Таблица инвойсов DevFactory
CREATE TABLE IF NOT EXISTS billing.devfactory_invoice (
    id              BIGSERIAL PRIMARY KEY,
    number          TEXT        NOT NULL,                       -- номер счёта (например, DF-2025-0001)
    client_name     TEXT        NOT NULL,                       -- имя/название клиента
    service_desc    TEXT        NOT NULL,                       -- описание услуги / пакета задач
    amount          NUMERIC(18,2) NOT NULL,                     -- сумма счёта
    currency        TEXT        NOT NULL DEFAULT 'RUB',         -- валюта
    due_date        DATE,                                       -- срок оплаты (опционально)
    status          TEXT        NOT NULL DEFAULT 'draft',       -- draft / sent / partially_paid / paid / cancelled
    devtask_ids     INT[]       DEFAULT '{}'::INT[],            -- связанные dev.dev_task.id (массив)
    meta            JSONB       NOT NULL DEFAULT '{}'::JSONB,   -- метаданные (канал, тариф, примечания)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ограничение на статус (idempotent через pg_constraint)
DO $$
BEGIN
  IF NOT EXISTS (
      SELECT 1
      FROM pg_constraint
      WHERE conname = 'devfactory_invoice_status_chk'
        AND conrelid = 'billing.devfactory_invoice'::regclass
  ) THEN
    ALTER TABLE billing.devfactory_invoice
      ADD CONSTRAINT devfactory_invoice_status_chk
      CHECK (status IN ('draft','sent','partially_paid','paid','cancelled'));
  END IF;
END;
$$;

-- Уникальный индекс по номеру счёта
CREATE UNIQUE INDEX IF NOT EXISTS devfactory_invoice_number_uidx
  ON billing.devfactory_invoice (number);

-- Индекс по статусу и сумме (для быстрого поиска кандидатов на матчинг)
CREATE INDEX IF NOT EXISTS devfactory_invoice_status_amount_idx
  ON billing.devfactory_invoice (status, amount);

-- 3. Таблица для импорта банковских операций (упрощённый формат)
CREATE TABLE IF NOT EXISTS billing.devfactory_bank_tx_import (
    id                  BIGSERIAL PRIMARY KEY,
    external_id         TEXT,                                  -- внешний идентификатор строки выписки (если есть)
    operation_date      DATE        NOT NULL,                  -- дата операции
    amount              NUMERIC(18,2) NOT NULL,                -- сумма платежа (для входящих платежей > 0)
    currency            TEXT        NOT NULL DEFAULT 'RUB',
    description         TEXT,                                  -- назначение платежа / комментарий банка
    payer_name          TEXT,                                  -- плательщик (ФИО/организация)
    raw_payload         JSONB       DEFAULT NULL,              -- исходная строка/объект (как есть из CSV/Excel/JSON)
    matched_invoice_id  BIGINT      REFERENCES billing.devfactory_invoice(id),
    match_status        TEXT        NOT NULL DEFAULT 'unmatched', -- unmatched / matched / ignored
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ограничение на статус матчинга (idempotent)
DO $$
BEGIN
  IF NOT EXISTS (
      SELECT 1
      FROM pg_constraint
      WHERE conname = 'devfactory_bank_tx_import_match_status_chk'
        AND conrelid = 'billing.devfactory_bank_tx_import'::regclass
  ) THEN
    ALTER TABLE billing.devfactory_bank_tx_import
      ADD CONSTRAINT devfactory_bank_tx_import_match_status_chk
      CHECK (match_status IN ('unmatched','matched','ignored'));
  END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS devfactory_bank_tx_import_match_status_idx
  ON billing.devfactory_bank_tx_import (match_status);

CREATE INDEX IF NOT EXISTS devfactory_bank_tx_import_amount_idx
  ON billing.devfactory_bank_tx_import (amount);

-- 4. Функция матчинг-прохода:
--    - ищет для входящих платежей (unmatched) единственного кандидата-инвойс:
--      * invoice.status IN ('sent','partially_paid')
--      * invoice.currency = tx.currency
--      * invoice.amount = tx.amount
--      * invoice.number встречается в description (ILIKE)
--    - при матче:
--      * обновляет tx: matched_invoice_id, match_status='matched'
--      * обновляет invoice.status='paid' (для v0.1 без частичных оплат)
--    - возвращает JSONB с кратким отчётом.

CREATE OR REPLACE FUNCTION billing.devfactory_match_payments()
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_matched_count      INT    := 0;
    v_skipped_no_invoice INT    := 0;
    v_tx_id              BIGINT;
    v_inv_id             BIGINT;
BEGIN
    -- проходим по всем нематчёным платежам и ищем под них инвойс
    FOR v_tx_id, v_inv_id IN
        SELECT
            tx.id  AS tx_id,
            inv.id AS inv_id
        FROM billing.devfactory_bank_tx_import tx
        LEFT JOIN LATERAL (
            SELECT i.id
            FROM billing.devfactory_invoice i
            WHERE i.status IN ('sent','partially_paid')
              AND i.currency = tx.currency
              AND i.amount   = tx.amount
              AND COALESCE(tx.description,'') ILIKE '%' || i.number || '%'
            ORDER BY i.id
            LIMIT 1
        ) AS inv ON TRUE
        WHERE tx.match_status = 'unmatched'
    LOOP
        IF v_inv_id IS NULL THEN
            v_skipped_no_invoice := v_skipped_no_invoice + 1;
        ELSE
            UPDATE billing.devfactory_bank_tx_import
               SET matched_invoice_id = v_inv_id,
                   match_status      = 'matched',
                   updated_at        = NOW()
             WHERE id = v_tx_id;

            UPDATE billing.devfactory_invoice
               SET status     = 'paid',
                   updated_at = NOW()
             WHERE id = v_inv_id;

            v_matched_count := v_matched_count + 1;
        END IF;
    END LOOP;

    RETURN jsonb_build_object(
        'ok', TRUE,
        'matched', v_matched_count,
        'skipped_no_invoice', v_skipped_no_invoice,
        'ts', NOW()
    );
END;
$$;

COMMIT;
