-- devfactory_billing_match_and_summary_v1.sql
-- DevFactory Billing v0.1 — матчинг платежей и сводка по инвойсам

-- 1. Запуск функции матчинга (один проход по unmatched)
SELECT billing.devfactory_match_payments() AS match_result;

-- 2. Сводка по инвойсам DevFactory
SELECT
    inv.id,
    inv.number,
    inv.client_name,
    inv.service_desc,
    inv.amount,
    inv.currency,
    inv.due_date,
    inv.status,
    COALESCE(array_length(inv.devtask_ids, 1), 0) AS devtask_count,
    pay.matched_payments,
    pay.matched_amount,
    inv.created_at,
    inv.updated_at
FROM billing.devfactory_invoice AS inv
LEFT JOIN LATERAL (
    SELECT
        COUNT(*)             AS matched_payments,
        COALESCE(SUM(amount), 0)::NUMERIC(18,2) AS matched_amount
    FROM billing.devfactory_bank_tx_import tx
    WHERE tx.matched_invoice_id = inv.id
) AS pay ON TRUE
ORDER BY inv.id DESC;

-- 3. Нематчёные платежи (для ручного разбора)
SELECT
    tx.id,
    tx.external_id,
    tx.operation_date,
    tx.amount,
    tx.currency,
    tx.description,
    tx.payer_name,
    tx.match_status,
    tx.matched_invoice_id,
    tx.created_at,
    tx.updated_at
FROM billing.devfactory_bank_tx_import tx
WHERE tx.match_status = 'unmatched'
ORDER BY tx.operation_date DESC, tx.id DESC;
