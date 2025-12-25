-- 20251205_flowmeta_devfactory_domain_fix.sql
-- FoxProFlow / FlowMeta
-- Назначение: гарантировать наличие домена `devfactory` в flowmeta.domain.
-- Патч идемпотентен: при повторном запуске только пишет NOTICE.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM flowmeta.domain d
        WHERE d.code = 'devfactory'
    ) THEN
        INSERT INTO flowmeta.domain (code, description, meta)
        VALUES (
            'devfactory',
            'DevFactory domain (software factory / agents / FlowMeta integration)',
            '{}'::jsonb
        );

        RAISE NOTICE 'FlowMeta: domain devfactory inserted';
    ELSE
        RAISE NOTICE 'FlowMeta: domain devfactory already exists, skip insert';
    END IF;
END;
$$ LANGUAGE plpgsql;
