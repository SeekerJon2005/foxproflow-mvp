-- 20251125_flowmeta_status_view.sql
-- FoxProFlow — агрегированный статус FlowMeta по последнему событию на мир.
-- NDC: только создание схемы и VIEW, причём VIEW создаём через проверку в catalog
--      (если уже есть, оставляем в покое).

CREATE SCHEMA IF NOT EXISTS ops;

-- Удалять/переделывать VIEW мы не хотим (NDC),
-- поэтому через DO-блок проверяем наличие в системном каталоге
-- и создаём ops.flowmeta_status_v только если её ещё нет.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n
            ON n.oid = c.relnamespace
        WHERE n.nspname = 'ops'
          AND c.relname = 'flowmeta_status_v'
          AND c.relkind IN ('v','m')  -- view / matview
    ) THEN
        EXECUTE $v$
        CREATE VIEW ops.flowmeta_status_v AS
        WITH last_events AS (
            SELECT DISTINCT ON (world_name)
                world_name,
                id,
                ts,
                ok,
                n_violations,
                severity_max,
                payload
            FROM ops.flowmeta_events
            ORDER BY world_name, ts DESC, id DESC
        )
        SELECT
            world_name,
            ts                AS last_check_ts,
            ok,
            n_violations,
            severity_max,
            payload
        FROM last_events;
        $v$;
    END IF;
END;
$$;
