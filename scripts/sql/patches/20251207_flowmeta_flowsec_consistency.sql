-- 20251207_flowmeta_flowsec_consistency.sql
-- FlowMeta v0.2: консистентность доменов FlowSec ↔ FlowMeta
--
-- Цель:
--   1) Дать прозрачный view sec.v_policy_domain_consistency, показывающий,
--      какие домены в sec.policies известны FlowMeta, а какие нет.
--   2) Дать функцию flowmeta.fn_check_flowsec_domains(), возвращающую только
--      проблемные политики (домены, которых нет в flowmeta.domain).
--
-- Безопасность:
--   - Ни структура sec.policies, ни её данные не изменяются.
--   - Используется только CREATE OR REPLACE VIEW/FUNCTION (идемпотентно).
--   - При отсутствии flowmeta.domain поднимаем явную ошибку.

DO $$
BEGIN
    -- Проверяем наличие flowmeta.domain (должен быть после предыдущего патча)
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'domain'
    ) THEN
        RAISE EXCEPTION 'flowmeta.domain is missing; apply FlowMeta v0.2 domains patch first';
    END IF;

    -- Проверяем наличие sec.policies (по текущей схеме)
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'sec'
          AND table_name   = 'policies'
    ) THEN
        RAISE EXCEPTION 'sec.policies is missing; cannot create consistency view';
    END IF;
END;
$$;

-- 1. View: sec.v_policy_domain_consistency
--
-- Показывает для каждой политики:
--   - известны ли target_domain и domain в FlowMeta,
--   - пустые ли поля,
--   - агрегированный флаг has_problem.

CREATE OR REPLACE VIEW sec.v_policy_domain_consistency AS
SELECT
    p.policy_code,
    p.title,
    p.target_domain,
    p."domain",
    p.action,
    p.effect,
    p.decision,
    p.is_active,
    -- флаги пустоты
    (p.target_domain IS NULL OR p.target_domain = '') AS is_target_domain_empty,
    (p."domain"    IS NULL OR p."domain"    = '') AS is_domain_empty,
    -- флаги известности домена в FlowMeta
    (d_target.code IS NOT NULL) AS is_target_domain_known,
    (d_domain.code IS NOT NULL) AS is_domain_known,
    -- удобный агрегированный статус
    CASE
        WHEN (p.target_domain IS NOT NULL AND p.target_domain <> '' AND d_target.code IS NULL)
          OR (p."domain"    IS NOT NULL AND p."domain"    <> '' AND d_domain.code IS NULL)
        THEN true
        ELSE false
    END AS has_problem
FROM sec.policies AS p
LEFT JOIN flowmeta.domain AS d_target
       ON d_target.code = p.target_domain
LEFT JOIN flowmeta.domain AS d_domain
       ON d_domain.code = p."domain";

COMMENT ON VIEW sec.v_policy_domain_consistency IS
'Консистентность доменов FlowSec ↔ FlowMeta: показывает, какие target_domain/domain из sec.policies известны в flowmeta.domain и есть ли проблемы.';

-- 2. Функция: flowmeta.fn_check_flowsec_domains()
--
-- Возвращает только те политики, у которых есть проблема:
--   - target_domain указан, но не найден в flowmeta.domain
--   - domain указан, но не найден в flowmeta.domain
--   - оба указаны, оба не найдены

CREATE OR REPLACE FUNCTION flowmeta.fn_check_flowsec_domains()
RETURNS TABLE (
    policy_code   text,
    title         text,
    target_domain text,
    "domain"      text,
    action        text,
    effect        text,
    decision      text,
    is_target_domain_known boolean,
    is_domain_known        boolean,
    problem       text
)
LANGUAGE sql
AS $FUNC$
    SELECT
        p.policy_code,
        p.title,
        p.target_domain,
        p."domain",
        p.action,
        p.effect,
        p.decision,
        (d_target.code IS NOT NULL) AS is_target_domain_known,
        (d_domain.code IS NOT NULL) AS is_domain_known,
        CASE
            WHEN (p.target_domain IS NOT NULL AND p.target_domain <> '' AND d_target.code IS NULL)
             AND (p."domain"    IS NOT NULL AND p."domain"    <> '' AND d_domain.code IS NULL)
                THEN 'unknown_target_and_domain'
            WHEN (p.target_domain IS NOT NULL AND p.target_domain <> '' AND d_target.code IS NULL)
                THEN 'unknown_target_domain'
            WHEN (p."domain"    IS NOT NULL AND p."domain"    <> '' AND d_domain.code IS NULL)
                THEN 'unknown_domain'
            ELSE 'ok'
        END AS problem
    FROM sec.policies AS p
    LEFT JOIN flowmeta.domain AS d_target
           ON d_target.code = p.target_domain
    LEFT JOIN flowmeta.domain AS d_domain
           ON d_domain.code = p."domain"
    WHERE
        (p.target_domain IS NOT NULL AND p.target_domain <> '' AND d_target.code IS NULL)
        OR
        (p."domain"    IS NOT NULL AND p."domain"    <> '' AND d_domain.code IS NULL);
$FUNC$;

COMMENT ON FUNCTION flowmeta.fn_check_flowsec_domains() IS
'Возвращает политики из sec.policies, у которых target_domain/domain не найдены в flowmeta.domain.';
