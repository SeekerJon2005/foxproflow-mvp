-- 2025-12-11
-- Link DevFactory DevOrder tasks to FlowMind DF-3 + Logistics 3-week plan
-- Target DevOrder: dev_order_id = 1a710838-bd2a-4679-98d9-611877fecbca
-- FlowMind plan:   plan_id = 54236a99-7afc-45f9-bc2e-fe45d281ffe9 (devfactory+logistics/3week)

DO $$
BEGIN
    -- Обновляем только те задачи, где:
    --  - meta.dev_order_id = заданному DevOrder;
    --  - нет ещё flowmind_plan_id (чтобы не перезатирать существующие связи).
    UPDATE dev.dev_task t
    SET meta = jsonb_set(
                  jsonb_set(
                      COALESCE(t.meta, '{}'::jsonb),
                      '{flowmind_plan_id}',
                      to_jsonb('54236a99-7afc-45f9-bc2e-fe45d281ffe9'::text),
                      true
                  ),
                  '{flowmind_plan_domain}',
                  to_jsonb('devfactory+logistics/3week'::text),
                  true
              )
    WHERE t.meta ->> 'dev_order_id' = '1a710838-bd2a-4679-98d9-611877fecbca'
      AND (t.meta ->> 'flowmind_plan_id') IS NULL;

    -- При желании можно позже добавить логику для обновления plan_id (numeric),
    -- но сейчас основным источником правды для FlowMind является meta.flowmind_*.
END;
$$;
