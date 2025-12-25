-- 20251207_flowmind_flowmeta_v0_1.sql
-- FlowMind v0.1 — домены, сущности и связи в FlowMeta.

DO $$
BEGIN
    ----------------------------------------------------------------------
    -- 0. Проверяем, что FlowMeta v0.2 установлен
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'domain'
    ) THEN
        RAISE EXCEPTION 'flowmeta.domain is missing; apply FlowMeta base patch first';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'entity'
    ) THEN
        RAISE EXCEPTION 'flowmeta.entity is missing; apply FlowMeta entities patch first';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'relation'
    ) THEN
        RAISE EXCEPTION 'flowmeta.relation is missing; apply FlowMeta relations patch first';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'flowmeta'
          AND p.proname = 'upsert_domain'
    ) THEN
        RAISE EXCEPTION 'flowmeta.upsert_domain is missing; apply FlowMeta v0.2 domains/entities patch first';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'flowmeta'
          AND p.proname = 'upsert_entity'
    ) THEN
        RAISE EXCEPTION 'flowmeta.upsert_entity is missing; apply FlowMeta v0.2 entities patch first';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'flowmeta'
          AND p.proname = 'insert_relation_if_not_exists'
    ) THEN
        RAISE EXCEPTION 'flowmeta.insert_relation_if_not_exists is missing; apply FlowMeta v0.2 relations patch first';
    END IF;

    ----------------------------------------------------------------------
    -- 1. Домены FlowMind
    ----------------------------------------------------------------------

    PERFORM flowmeta.upsert_domain(
        'flowmind.core',
        'FlowMind Core',
        'organism',
        'core',
        'Операционный мозг организма: собирает состояние DevFactory, логистики, CRM, Observability и безопасности и готовит осмысленные планы.'
    );

    PERFORM flowmeta.upsert_domain(
        'flowmind.plan',
        'FlowMind Planning',
        'organism',
        'core',
        'Слой планов FlowMind (FlowLang-подобные планы, сценарии, цели и шаги для органов организма).'
    );

    PERFORM flowmeta.upsert_domain(
        'flowmind.context',
        'FlowMind Context',
        'organism',
        'supporting',
        'Контекстные профили по доменам (DevFactory, логистика, CRM, FlowSec, Observability, Analytics).'
    );

    PERFORM flowmeta.upsert_domain(
        'flowmind.advice',
        'FlowMind Advice',
        'organism',
        'supporting',
        'Советы и рекомендации FlowMind для Архитектора и операторов (какие задачи запускать, что в приоритете, где риск).'
    );

    ----------------------------------------------------------------------
    -- 2. Сущности FlowMind
    ----------------------------------------------------------------------

    -- 2.1. flowmind.core
    PERFORM flowmeta.upsert_entity(
        'flowmind.core',
        'mind_snapshot',
        'Снимок состояния организма',
        'Агрегированное состояние DevFactory, логистики, CRM, Observability, FlowSec и других доменов на момент времени.'
    );

    PERFORM flowmeta.upsert_entity(
        'flowmind.core',
        'mind_metric',
        'Метрика FlowMind',
        'Агрегированные метрики, которые FlowMind использует для reasoning (нагрузка DevFactory, SLA логистики, здоровье FlowSec и т.п.).'
    );

    -- 2.2. flowmind.plan
    PERFORM flowmeta.upsert_entity(
        'flowmind.plan',
        'plan',
        'План FlowMind',
        'FlowLang-подобный план: цель, домен, шаги, ограничения, ссылки на DevFactory-задачи.'
    );

    PERFORM flowmeta.upsert_entity(
        'flowmind.plan',
        'plan_step',
        'Шаг плана FlowMind',
        'Отдельный шаг плана (что сделать, каким органом, в какой последовательности).'
    );

    -- 2.3. flowmind.context
    PERFORM flowmeta.upsert_entity(
        'flowmind.context',
        'context_profile',
        'Контекстный профиль FlowMind',
        'Профиль контекста для конкретного домена/tenant/проекта (DevFactory, логистика, CRM и т.п.).'
    );

    PERFORM flowmeta.upsert_entity(
        'flowmind.context',
        'kpi_snapshot_ref',
        'Ссылка на KPI-снимок',
        'Связь FlowMind-контекста с конкретными KPI-витринами и снимками (DevFactory, логистика, CRM).'
    );

    -- 2.4. flowmind.advice
    PERFORM flowmeta.upsert_entity(
        'flowmind.advice',
        'advice',
        'Совет FlowMind',
        'Совет/рекомендация FlowMind: что нужно сделать, в каком домене, с какой важностью.'
    );

    PERFORM flowmeta.upsert_entity(
        'flowmind.advice',
        'advice_ack',
        'Подтверждение совета FlowMind',
        'Факт принятия, выполнения или игнорирования совета FlowMind человеком или системой.'
    );

    ----------------------------------------------------------------------
    -- 3. Связи FlowMind с другими доменами
    ----------------------------------------------------------------------

    -- 3.1. FlowMind Core ↔ FlowMeta / Observability / Analytics

    PERFORM flowmeta.insert_relation_if_not_exists(
        'flowmind.core', 'mind_snapshot',
        'flowmeta',      'domain',
        'depends_on',
        'FlowMind читает структуру доменов/сущностей из FlowMeta и не может работать без актуального скелета организма.'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'flowmind.core', 'mind_snapshot',
        'observability', 'event',
        'depends_on',
        'Каждый снимок состояния FlowMind базируется на событиях Observability (ops.event_log) по ключевым доменам.'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'flowmind.core', 'mind_snapshot',
        'analytics',     'metric_view',
        'depends_on',
        'FlowMind использует аналитические витрины KPI как входные метрики для reasoning.'
    );

    -- 3.2. FlowMind Context ↔ DevFactory Capsule Profile

    PERFORM flowmeta.insert_relation_if_not_exists(
        'flowmind.context', 'context_profile',
        'devfactory',       'capsule_profile',
        'depends_on',
        'Контекстные профили FlowMind опираются на DevFactory Capsule Profile для понимания границ капсул/realm.'
    );

    -- 3.3. FlowMind Plans ↔ DevFactory Tasks

    PERFORM flowmeta.insert_relation_if_not_exists(
        'flowmind.plan', 'plan',
        'devfactory',   'task',
        'produces',
        'Планы FlowMind порождают задачи DevFactory (dev.dev_task) как материализацию шагов плана.'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'flowmind.plan', 'plan_step',
        'devfactory',   'task',
        'refines',
        'Шаги плана FlowMind детализируют, какие именно DevFactory-задачи нужно создать или доработать.'
    );

    -- 3.4. FlowMind Advice ↔ DevFactory Orders / Tasks

    PERFORM flowmeta.insert_relation_if_not_exists(
        'flowmind.advice', 'advice',
        'devfactory',      'order',
        'governs',
        'Советы FlowMind помогают приоритизировать DevFactory-orders и решать, какие коммерческие запросы выполнять первыми.'
    );

    PERFORM flowmeta.insert_relation_if_not_exists(
        'flowmind.advice', 'advice',
        'devfactory',      'task',
        'governs',
        'Советы FlowMind помогают решать, какие DevFactory-задачи запускать, замораживать или переупорядочивать.'
    );

END;
$$ LANGUAGE plpgsql;
