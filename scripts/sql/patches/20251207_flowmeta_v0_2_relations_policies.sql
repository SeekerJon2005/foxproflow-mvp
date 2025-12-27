-- 20251207_flowmeta_v0_2_relations_policies.sql
-- FlowMeta v0.2: загрузка связей (flowmeta.relation) и мета-политик (flowmeta.policy)

DO $$
BEGIN
    ------------------------------------------------------------------
    -- 0. Гарантируем корректную структуру flowmeta.relation/policy
    ------------------------------------------------------------------

    -- flowmeta.relation должен существовать (создавался в entities-патче)
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'relation'
    ) THEN
        RAISE EXCEPTION 'flowmeta.relation is missing; apply FlowMeta v0.2 entities patch first';
    END IF;

    -- Если flowmeta.policy ещё нет — создаём базовую таблицу
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'policy'
    ) THEN
        EXECUTE $DDL$
            CREATE TABLE flowmeta.policy (
                code text PRIMARY KEY,
                type text NOT NULL,
                meta jsonb NOT NULL DEFAULT '{}'::jsonb
            );
        $DDL$;
    END IF;

    -- Гарантируем наличие колонки type
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'policy'
          AND column_name  = 'type'
    ) THEN
        EXECUTE 'ALTER TABLE flowmeta.policy ADD COLUMN type text';
    END IF;

    -- Гарантируем наличие колонки meta (и что она jsonb)
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'policy'
          AND column_name  = 'meta'
    ) THEN
        EXECUTE 'ALTER TABLE flowmeta.policy ADD COLUMN meta jsonb NOT NULL DEFAULT ''{}''::jsonb';
    ELSE
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'flowmeta'
              AND table_name   = 'policy'
              AND column_name  = 'meta'
              AND data_type   <> 'jsonb'
        ) THEN
            EXECUTE 'ALTER TABLE flowmeta.policy ALTER COLUMN meta TYPE jsonb USING meta::jsonb';
        END IF;
    END IF;

    -- Если есть колонка kind NOT NULL — ставим дефолт и заполняем NULL
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'policy'
          AND column_name  = 'kind'
    ) THEN
        -- дефолт для новых строк
        EXECUTE 'ALTER TABLE flowmeta.policy ALTER COLUMN kind SET DEFAULT ''meta_policy''';
        -- заполняем всё, что уже NULL
        EXECUTE 'UPDATE flowmeta.policy SET kind = COALESCE(kind, ''meta_policy'')';
    END IF;

    -- Для существующих строк нормализуем type (если где-то NULL)
    UPDATE flowmeta.policy
    SET type = COALESCE(type, 'invariant');

    ----------------------------------------------------------------------
    -- 1. upsert-помощник для мета-политик FlowMeta
    ----------------------------------------------------------------------
    CREATE OR REPLACE FUNCTION flowmeta.upsert_policy(
        p_code        text,
        p_type        text,
        p_description text,
        p_applies_to  text[] DEFAULT NULL
    )
    RETURNS void
    LANGUAGE plpgsql
    AS $FUNC$
    BEGIN
        INSERT INTO flowmeta.policy (code, type, meta)
        VALUES (p_code, p_type, '{}'::jsonb)
        ON CONFLICT (code) DO UPDATE
        SET type = EXCLUDED.type;

        UPDATE flowmeta.policy
        SET meta =
            jsonb_set(
                jsonb_set(
                    meta,
                    '{description}',
                    to_jsonb(p_description),
                    true
                ),
                '{applies_to}',
                COALESCE(to_jsonb(p_applies_to), '[]'::jsonb),
                true
            )
        WHERE code = p_code;
    END;
    $FUNC$;

    ----------------------------------------------------------------------
    -- 2. Загрузка мета-политик FlowMeta (Blueprint v0.2)
    ----------------------------------------------------------------------

    PERFORM flowmeta.upsert_policy(
        'meta.domain_must_exist',
        'invariant',
        'Ни один код домена не может появиться в sec.policies.target_domain или ops.event_log.domain, если он не зарегистрирован в flowmeta.domain.',
        ARRAY['security.policy', 'observability.event']
    );

    PERFORM flowmeta.upsert_policy(
        'meta.entity_must_have_domain',
        'invariant',
        'Любая сущность FlowMeta должна быть привязана к существующему домену flowmeta.domain.',
        ARRAY['flowmeta.entity']
    );

    PERFORM flowmeta.upsert_policy(
        'devfactory.must_use_flowmeta',
        'generation',
        'DevFactory не имеет права создавать новые домены/сущности на лету — он обязан сначала расширить FlowMeta, а затем генерировать код/SQL для этих доменов.',
        ARRAY['devfactory.task']
    );

    PERFORM flowmeta.upsert_policy(
        'security.policy_must_match_domain',
        'safety',
        'Политики безопасности для доменов devfactory/logistics/crm/billing/security допускаются только если домен присутствует в FlowMeta и не помечен как deprecated.',
        ARRAY['security.policy']
    );

    PERFORM flowmeta.upsert_policy(
        'analytics.view_must_reference_known_domain',
        'observability',
        'Любая аналитическая витрина должна иметь domain_code, который существует в flowmeta.domain; иначе витрина помечается как invalid и не должна использоваться агентами/ERI.',
        ARRAY['analytics.metric_view']
    );

    ----------------------------------------------------------------------
    -- 3. Загрузка связей FlowMeta (flowmeta.relation)
    ----------------------------------------------------------------------

    CREATE OR REPLACE FUNCTION flowmeta.insert_relation_if_not_exists(
        p_from_domain_code text,
        p_from_entity_code text,
        p_to_domain_code   text,
        p_to_entity_code   text,
        p_type             text,
        p_description      text
    )
    RETURNS void
    LANGUAGE plpgsql
    AS $R$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM flowmeta.relation r
            WHERE r.from_domain_code = p_from_domain_code
              AND r.from_entity_code = p_from_entity_code
              AND r.to_domain_code   = p_to_domain_code
              AND r.to_entity_code   = p_to_entity_code
              AND r.type             = p_type
        ) THEN
            INSERT INTO flowmeta.relation (
                from_domain_code,
                from_entity_code,
                to_domain_code,
                to_entity_code,
                type,
                meta
            )
            VALUES (
                p_from_domain_code,
                p_from_entity_code,
                p_to_domain_code,
                p_to_entity_code,
                p_type,
                jsonb_build_object('description', p_description)
            );
        END IF;
    END;
    $R$;

    -- 3.1. DevFactory как орган роста

    PERFORM flowmeta.insert_relation_if_not_exists(
        'devfactory', 'task',
        'flowmeta',   'entity',
        'produces',
        'Задачи DevFactory вносят изменения в сущности FlowMeta (domain/entity/relation/policy) через SQL-патчи и код.'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'devfactory', 'task',
        'logistics',  '*',
        'produces',
        'DevFactory генерирует и эволюционирует схему и код логистического домена (vehicles/loads/trips/trip_segments, KPI-вьюхи).'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'devfactory', 'task',
        'security',   '*',
        'produces',
        'DevFactory создаёт/изменяет FlowSec-патчи (sec.roles/sec.policies/sec.subject_roles) для домена security.'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'devfactory', 'order',
        'devfactory', 'task',
        'governs',
        'DevOrder объединяет задачи DevFactory и задаёт коммерческий контекст для набора задач.'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'devfactory', 'order',
        'crm',        'tenant',
        'depends_on',
        'Каждый DevOrder связан с конкретным tenant, для которого выполняется работа.'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'devfactory', 'order',
        'billing',    'subscription',
        'depends_on',
        'DevOrder опирается на подписку BillingFox, определяющую тариф и условия оплаты.'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'devfactory', 'order',
        'billing',    'invoice',
        'produces',
        'По DevOrder формируются счета billing.invoice; статусы заказов и счетов должны быть согласованы.'
    );

    -- 3.2. FlowSec ↔ домены

    PERFORM flowmeta.insert_relation_if_not_exists(
        'security', 'policy',
        'flowmeta', 'domain',
        'governs',
        'Политики безопасности управляют доступом к доменам, описанным в FlowMeta.'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'security',     'audit_event',
        'devfactory',   '*',
        'observes',
        'События аудита безопасности фиксируют операции в домене devfactory (tasks/orders).'
    );

    -- 3.3. Observability / Analytics ↔ DevFactory

    PERFORM flowmeta.insert_relation_if_not_exists(
        'observability', 'event',
        'devfactory',    'task',
        'enriches',
        'События Observability фиксируют жизненный цикл задач DevFactory и обогащают их контекстом.'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'analytics', 'metric_view',
        'devfactory','task',
        'depends_on',
        'Аналитические витрины DevFactory KPI опираются на задачи DevFactory как первичный факт.'
    );

    -- 3.4. Logistics ↔ CRM/Billing/Analytics

    PERFORM flowmeta.insert_relation_if_not_exists(
        'logistics', 'trip',
        'crm',       'tenant',
        'depends_on',
        'Каждый рейс логистики привязан к tenant (клиенту).'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'logistics', 'trip',
        'analytics', 'metric_view',
        'produces',
        'Фактические рейсы становятся основой для витрин KPI (загрузка ТС, выручка, SLA).'
    );

END;
$$;
