-- 20251207_flowmeta_v0_2_view_domain_entities.sql
-- FlowMeta v0.2: агрегированный view и JSON-функция для доменов и сущностей

DO $$
BEGIN
    -- Проверяем, что базовые таблицы уже есть
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'domain'
    ) THEN
        RAISE EXCEPTION 'flowmeta.domain is missing; apply FlowMeta v0.2 domains patch first';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'entity'
    ) THEN
        RAISE EXCEPTION 'flowmeta.entity is missing; apply FlowMeta v0.2 entities patch first';
    END IF;
END;
$$;

----------------------------------------------------------------------
-- 1. View: flowmeta.v_domain_entities
--
-- Плоский срез: каждая строка = (домен, сущность).
-- Удобно для прямых SELECT и аналитики.
----------------------------------------------------------------------

CREATE OR REPLACE VIEW flowmeta.v_domain_entities AS
SELECT
    d.code                           AS domain_code,
    d.meta->>'title'                 AS domain_title,
    d.meta->>'tier'                  AS domain_tier,
    d.meta->>'importance'            AS domain_importance,
    e.entity_code,
    e.meta->>'title'                 AS entity_title,
    e.meta->>'description'           AS entity_description
FROM flowmeta.domain AS d
LEFT JOIN flowmeta.entity AS e
       ON e.domain_code = d.code
ORDER BY d.code, e.entity_code;

COMMENT ON VIEW flowmeta.v_domain_entities IS
'Плоский срез FlowMeta: домены + сущности (domain_code, domain_title, tier, importance, entity_code, entity_title, entity_description).';

----------------------------------------------------------------------
-- 2. Функция: flowmeta.fn_get_domain_entities_json()
--
-- Возвращает JSON-массив:
-- [
--   {
--     "code": "devfactory",
--     "title": "...",
--     "tier": "earth",
--     "importance": "core",
--     "entities": [
--       { "entity_code": "task", "title": "...", "description": "..." },
--       ...
--     ]
--   },
--   ...
-- ]
--
-- Это удобно отдавать в API / агентам без дополнительной агрегации.
----------------------------------------------------------------------

CREATE OR REPLACE FUNCTION flowmeta.fn_get_domain_entities_json()
RETURNS jsonb
LANGUAGE plpgsql
AS $FUNC$
DECLARE
    result jsonb;
BEGIN
    SELECT jsonb_agg(domain_obj ORDER BY domain_code)
    INTO result
    FROM (
        SELECT
            d.code                    AS domain_code,
            jsonb_build_object(
                'code',        d.code,
                'title',       d.meta->>'title',
                'tier',        d.meta->>'tier',
                'importance',  d.meta->>'importance',
                'entities',    COALESCE(
                    (
                        SELECT jsonb_agg(
                                   jsonb_build_object(
                                       'entity_code', e.entity_code,
                                       'title',       e.meta->>'title',
                                       'description', e.meta->>'description'
                                   )
                                   ORDER BY e.entity_code
                               )
                        FROM flowmeta.entity e
                        WHERE e.domain_code = d.code
                    ),
                    '[]'::jsonb
                )
            ) AS domain_obj
        FROM flowmeta.domain d
    ) AS t;

    RETURN COALESCE(result, '[]'::jsonb);
END;
$FUNC$;

COMMENT ON FUNCTION flowmeta.fn_get_domain_entities_json() IS
'Возвращает JSONB-массив доменов с вложенными сущностями (code/title/tier/importance + entities[]).';
