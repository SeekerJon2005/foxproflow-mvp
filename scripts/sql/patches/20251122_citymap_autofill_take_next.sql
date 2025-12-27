-- 20251122_citymap_autofill_take_next.sql
-- Функция: атомарно забрать одну pending-запись из очереди ops.citymap_autofill_queue
-- и перевести её в статус 'processing', с учётом стороны (src/dst) и инкрементом attempts.

SET search_path = public, ops, pg_catalog;

CREATE OR REPLACE FUNCTION ops.fn_citymap_autofill_take_next(
    p_side text DEFAULT NULL  -- 'src' / 'dst' или NULL, если не фильтруем по стороне
)
RETURNS SETOF ops.citymap_autofill_queue
LANGUAGE plpgsql
AS $$
DECLARE
    v_row ops.citymap_autofill_queue;
BEGIN
    -- Берём одну старейшую pending-запись с учётом стороны.
    -- SKIP LOCKED защищает от гонок при параллельных воркерах.
    WITH next_row AS (
        SELECT q.id
        FROM ops.citymap_autofill_queue AS q
        WHERE q.status = 'pending'
          AND (p_side IS NULL OR q.side = p_side)
        ORDER BY q.created_at, q.id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE ops.citymap_autofill_queue AS q
    SET status   = 'processing',
        attempts = COALESCE(q.attempts, 0) + 1
    FROM next_row nr
    WHERE q.id = nr.id
    RETURNING q.* INTO v_row;

    -- Если подходящих записей не оказалось — возвращаем 0 строк.
    IF NOT FOUND THEN
        RETURN;
    END IF;

    -- Возвращаем одну обновлённую строку.
    RETURN NEXT v_row;
    RETURN;
END;
$$;

COMMENT ON FUNCTION ops.fn_citymap_autofill_take_next(text) IS
'Атомарно выбирает одну запись из ops.citymap_autofill_queue со статусом pending (с опциональным фильтром по side), переводит её в статус processing, увеличивает attempts и возвращает обновлённую строку (или 0 строк, если очереди нет).';
