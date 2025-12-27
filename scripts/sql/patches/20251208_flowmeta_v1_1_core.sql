-- 20251208_flowmeta_v1_1_core.sql
-- FlowMeta v1.1: домены и сущности ядра FoxProFlow
-- stack=sql-postgres
-- goal=Загрузить домены и сущности FlowMeta v1.1 (devfactory, logistics, flowworld, eri, robots, crm, security, observability, analytics, flowmeta)
-- summary=Использует flowmeta.upsert_entity и idempotent INSERT в flowmeta.domain; не меняет структуру таблиц.

DO $$
DECLARE
    v_func_exists boolean;
BEGIN
    ----------------------------------------------------------------------
    -- 0. Проверяем наличие базовых таблиц и функции upsert_entity
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'domain'
    ) THEN
        RAISE EXCEPTION 'flowmeta.domain is missing; apply FlowMeta v0.2 base patch first';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'entity'
    ) THEN
        RAISE EXCEPTION 'flowmeta.entity is missing; apply FlowMeta v0.2 entities patch first';
    END IF;

    SELECT TRUE
    INTO v_func_exists
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'flowmeta'
      AND p.proname = 'upsert_entity';

    IF NOT v_func_exists THEN
        RAISE EXCEPTION 'flowmeta.upsert_entity() is missing; apply FlowMeta v0.2 entities patch first';
    END IF;

    ----------------------------------------------------------------------
    -- 1. Домены FlowMeta v1.1 (боевой минимум)
    ----------------------------------------------------------------------
    -- Если домен уже есть, meta не меняем (ON CONFLICT DO NOTHING).
    INSERT INTO flowmeta.domain (code)
    VALUES
        ('devfactory'),
        ('logistics'),
        ('flowworld'),
        ('eri'),
        ('robots'),
        ('crm'),
        ('billing'),
        ('security'),
        ('observability'),
        ('analytics'),
        ('flowmeta')
    ON CONFLICT (code) DO NOTHING;

    ----------------------------------------------------------------------
    -- 2. Сущности devfactory.*
    ----------------------------------------------------------------------
    PERFORM flowmeta.upsert_entity(
        'devfactory',
        'task',
        'Задача DevFactory',
        'Единица работы DevFactory (dev.dev_task): цель, стек, ограничения, result_spec.'
    );

    PERFORM flowmeta.upsert_entity(
        'devfactory',
        'order',
        'DevFactory Order',
        'Коммерческий заказ (dev.dev_order), объединяющий задачи и денежные отношения.'
    );

    PERFORM flowmeta.upsert_entity(
        'devfactory',
        'project',
        'DevFactory ProjectRef',
        'Логический проект (project_ref), объединяющий связанные задачи/патчи.'
    );

    PERFORM flowmeta.upsert_entity(
        'devfactory',
        'task_results_mv',
        'DevFactory Task Results MV',
        'Витрина результатов задач DevFactory (dev.devfactory_task_results_mv).'
    );

    PERFORM flowmeta.upsert_entity(
        'devfactory',
        'kpi_daily',
        'DevFactory KPI Daily',
        'Ежедневные KPI DevFactory (analytics.devfactory_daily или аналогичная витрина).'
    );

    PERFORM flowmeta.upsert_entity(
        'devfactory',
        'operator_ui',
        'DevFactory Operator UI',
        'Операторский портал DevFactory (static/devfactory_operator.html).'
    );

    PERFORM flowmeta.upsert_entity(
        'devfactory',
        'intent_parser',
        'DevFactory Intent Parser',
        'Модуль анализа намерений задач DevFactory (src/core/devfactory/intent_parser.py).'
    );

    PERFORM flowmeta.upsert_entity(
        'devfactory',
        'question_engine',
        'DevFactory Question Engine',
        'Модуль генерации уточняющих вопросов по IntentSpec (src/core/devfactory/question_engine.py).'
    );

    ----------------------------------------------------------------------
    -- 3. Сущности logistics.*
    ----------------------------------------------------------------------
    PERFORM flowmeta.upsert_entity(
        'logistics',
        'vehicle',
        'Транспортное средство',
        'ТС в парке (id, capacity, регион, ограничения по эксплуатации).'
    );

    PERFORM flowmeta.upsert_entity(
        'logistics',
        'load',
        'Груз/заявка',
        'Груз с временными окнами погрузки/выгрузки и SLA.'
    );

    PERFORM flowmeta.upsert_entity(
        'logistics',
        'trip',
        'Рейс',
        'Маршрут ТС с набором грузов, статусами и окнами.'
    );

    PERFORM flowmeta.upsert_entity(
        'logistics',
        'trip_segment',
        'Сегмент рейса',
        'Участок пути рейса между двумя точками, с ETA и атрибутами.'
    );

    PERFORM flowmeta.upsert_entity(
        'logistics',
        'route_mv',
        'Витрины маршрутов и доступности',
        'Материализованные представления маршрутов/доступности ТС (vehicle_availability_mv и др.).'
    );

    PERFORM flowmeta.upsert_entity(
        'logistics',
        'kpi_daily',
        'Logistics KPI Daily',
        'Ежедневные KPI логистики (planner_kpi_daily).'
    );

    ----------------------------------------------------------------------
    -- 4. Сущности flowworld.*
    ----------------------------------------------------------------------
    PERFORM flowmeta.upsert_entity(
        'flowworld',
        'space',
        'Пространство FlowWorld',
        'Локация/пространство (ферма, база, участок), со своим набором объектов.'
    );

    PERFORM flowmeta.upsert_entity(
        'flowworld',
        'object',
        'Объект FlowWorld',
        'Объект в пространстве (дом, ворота, техника, робот).'
    );

    PERFORM flowmeta.upsert_entity(
        'flowworld',
        'state_api',
        'FlowWorld State API',
        'API получения среза мира (GET /api/flowworld/state).'
    );

    PERFORM flowmeta.upsert_entity(
        'flowworld',
        'link_trip',
        'Связь рейса с пространством',
        'Логическая привязка рейса/ТС к пространству/объекту FlowWorld.'
    );

    ----------------------------------------------------------------------
    -- 5. Сущности eri.*
    ----------------------------------------------------------------------
    PERFORM flowmeta.upsert_entity(
        'eri',
        'session',
        'Сессия ERI',
        'Сеанс ERI с пользователем/семьёй (eri.session).'
    );

    PERFORM flowmeta.upsert_entity(
        'eri',
        'mode',
        'Режим ERI',
        'Режимы ERI (детский/семейный/рабочий/организм и т.п.) (eri.mode).'
    );

    PERFORM flowmeta.upsert_entity(
        'eri',
        'context_layer',
        'Контекстный слой ERI',
        'Слои контекста ERI (семья, задачи организма, FlowWorld, здоровье).'
    );

    PERFORM flowmeta.upsert_entity(
        'eri',
        'api_talk',
        'ERI Talk API',
        'Диалоговый вход ERI (POST /api/eri/talk).'
    );

    PERFORM flowmeta.upsert_entity(
        'eri',
        'api_context',
        'ERI Context API',
        'API получения контекста для ERI (например /api/eri/context).'
    );

    ----------------------------------------------------------------------
    -- 6. Сущности robots.*
    ----------------------------------------------------------------------
    PERFORM flowmeta.upsert_entity(
        'robots',
        'instance',
        'Экземпляр робота',
        'Конкретный робот (Optimus-1, Helper-A и т.п.).'
    );

    PERFORM flowmeta.upsert_entity(
        'robots',
        'role',
        'Роль робота',
        'Роль/назначение робота (агроном, техник, логист).'
    );

    PERFORM flowmeta.upsert_entity(
        'robots',
        'assignment',
        'Назначенная задача робота',
        'Связка робота с задачей/рейсом/объектом FlowWorld.'
    );

    PERFORM flowmeta.upsert_entity(
        'robots',
        'api_control',
        'Robots Control API',
        'API управления и мониторинга роботов (/api/robots/*).'
    );

    ----------------------------------------------------------------------
    -- 7. CRM / Security / Observability / Analytics (подтверждаем базовый слой)
    ----------------------------------------------------------------------
    PERFORM flowmeta.upsert_entity(
        'crm',
        'tenant',
        'Тенант FoxProFlow',
        'Клиент FoxProFlow: компания/организация, в чьём контуре работают остальные сущности.'
    );

    PERFORM flowmeta.upsert_entity(
        'crm',
        'contact',
        'Контактное лицо',
        'Контакт в рамках tenant (роль, контакты, связь с DevFactory/Logistics).'
    );

    PERFORM flowmeta.upsert_entity(
        'security',
        'role',
        'Роль безопасности',
        'Роль в sec.roles: код, название, системность.'
    );

    PERFORM flowmeta.upsert_entity(
        'security',
        'policy',
        'Политика безопасности',
        'Правило sec.policies: target_domain, action, effect, decision.'
    );

    PERFORM flowmeta.upsert_entity(
        'security',
        'subject_role',
        'Связь субъект↔роль',
        'Назначение ролей субъектам (user/service/tenant).'
    );

    PERFORM flowmeta.upsert_entity(
        'security',
        'audit_event',
        'Событие аудита безопасности',
        'Запись в sec.audit_events (actor, action, domain, severity).'
    );

    PERFORM flowmeta.upsert_entity(
        'observability',
        'event',
        'Событие Observability',
        'Событие ops.event_log с domain/source/payload.'
    );

    PERFORM flowmeta.upsert_entity(
        'observability',
        'routine_task',
        'Рутинная задача',
        'Регулярная задача (scheduler/beat), контролируемая Observability.'
    );

    PERFORM flowmeta.upsert_entity(
        'analytics',
        'metric_view',
        'Аналитическая витрина',
        'Агрегированная витрина KPI или метрик для агентов и UI.'
    );

END;
$$ LANGUAGE plpgsql;
