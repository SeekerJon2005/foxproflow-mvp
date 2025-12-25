-- 20251207_flowmeta_v0_2_entities.sql
-- FlowMeta v0.2: слой сущностей, связей и мета-политик

DO $$
BEGIN
    -- 0. Проверяем, что flowmeta.domain уже есть
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'domain'
    ) THEN
        RAISE EXCEPTION 'flowmeta.domain is missing; apply FlowMeta v0.2 domains patch first';
    END IF;

    ----------------------------------------------------------------------
    -- 1. Таблица flowmeta.entity
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'entity'
    ) THEN
        EXECUTE $DDL$
            CREATE TABLE flowmeta.entity (
                id          bigserial PRIMARY KEY,
                domain_code text    NOT NULL REFERENCES flowmeta.domain(code) ON DELETE CASCADE,
                entity_code text    NOT NULL,
                meta        jsonb   NOT NULL DEFAULT '{}'::jsonb,
                CONSTRAINT flowmeta_entity_uq UNIQUE (domain_code, entity_code)
            );
        $DDL$;
    END IF;

    ----------------------------------------------------------------------
    -- 2. Таблица flowmeta.relation
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'relation'
    ) THEN
        EXECUTE $DDL$
            CREATE TABLE flowmeta.relation (
                id               bigserial PRIMARY KEY,
                from_domain_code text    NOT NULL,
                from_entity_code text    NOT NULL,
                to_domain_code   text    NOT NULL,
                to_entity_code   text    NOT NULL,
                type             text    NOT NULL,
                meta             jsonb   NOT NULL DEFAULT '{}'::jsonb
            );
        $DDL$;
    END IF;

    ----------------------------------------------------------------------
    -- 3. Таблица flowmeta.policy
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'policy'
    ) THEN
        EXECUTE $DDL$
            CREATE TABLE flowmeta.policy (
                code text  PRIMARY KEY,
                type text  NOT NULL,
                meta jsonb NOT NULL DEFAULT '{}'::jsonb
            );
        $DDL$;
    END IF;

    ----------------------------------------------------------------------
    -- 4. Функция upsert для сущностей
    ----------------------------------------------------------------------
    CREATE OR REPLACE FUNCTION flowmeta.upsert_entity(
        p_domain_code text,
        p_entity_code text,
        p_title       text,
        p_description text DEFAULT NULL
    )
    RETURNS void
    LANGUAGE plpgsql
    AS $FUNC$
    BEGIN
        -- Проверяем, что домен существует
        IF NOT EXISTS (
            SELECT 1
            FROM flowmeta.domain d
            WHERE d.code = p_domain_code
        ) THEN
            RAISE EXCEPTION 'FlowMeta domain % does not exist (call upsert_domain first)', p_domain_code;
        END IF;

        -- Если сущности ещё нет — создаём
        INSERT INTO flowmeta.entity (domain_code, entity_code, meta)
        VALUES (p_domain_code, p_entity_code, '{}'::jsonb)
        ON CONFLICT (domain_code, entity_code) DO NOTHING;

        -- Обновляем JSON-поля meta (title / description)
        UPDATE flowmeta.entity
        SET meta =
            CASE
                WHEN p_description IS NULL THEN
                    jsonb_set(
                        meta,
                        '{title}',
                        to_jsonb(p_title),
                        true
                    )
                ELSE
                    jsonb_set(
                        jsonb_set(
                            meta,
                            '{title}',
                            to_jsonb(p_title),
                            true
                        ),
                        '{description}',
                        to_jsonb(p_description),
                        true
                    )
            END
        WHERE domain_code = p_domain_code
          AND entity_code = p_entity_code;
    END;
    $FUNC$;

    ----------------------------------------------------------------------
    -- 5. Базовые сущности для ключевых доменов (Blueprint v0.2)
    ----------------------------------------------------------------------

    -- 5.1. FlowMeta
    PERFORM flowmeta.upsert_entity(
        'flowmeta',
        'domain',
        'Домен FlowMeta',
        'Описание доменов (code, meta) — скелет смысловых областей.'
    );

    PERFORM flowmeta.upsert_entity(
        'flowmeta',
        'entity',
        'Сущность FlowMeta',
        'Описание сущностей внутри доменов (domain_code, entity_code, meta).'
    );

    PERFORM flowmeta.upsert_entity(
        'flowmeta',
        'relation',
        'Связь FlowMeta',
        'Описание связей между сущностями/доменами (зависимости, обогащения, ограничения).'
    );

    PERFORM flowmeta.upsert_entity(
        'flowmeta',
        'policy',
        'Мета-политика FlowMeta',
        'Мета-правила и инварианты (invariant/safety/planning/generation/observability).'
    );

    -- 5.2. DevFactory
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
        'capsule_profile',
        'DevFactory Capsule Profile',
        'Профиль капсулы (collab/realm), привязывающий FlowMeta/FlowSec к конкретной зоне работы.'
    );

    -- 5.3. Logistics
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

    -- 5.4. CRM
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

    -- 5.5. Billing
    PERFORM flowmeta.upsert_entity(
        'billing',
        'subscription',
        'Подписка',
        'Подписка BillingFox (план, статус, объём услуг).'
    );

    PERFORM flowmeta.upsert_entity(
        'billing',
        'invoice',
        'Счёт',
        'Счёт на оплату (amount, currency, статус).'
    );

    -- 5.6. Security
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

    -- 5.7. Observability
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

    -- 5.8. Analytics
    PERFORM flowmeta.upsert_entity(
        'analytics',
        'metric_view',
        'Аналитическая витрина',
        'Агрегированная витрина KPI или метрик для агентов и UI.'
    );

END;
$$;

COMMENT ON TABLE flowmeta.entity IS
'Сущности FlowMeta: entity_code + meta внутри доменов (flowmeta.domain).';

COMMENT ON TABLE flowmeta.relation IS
'Связи FlowMeta между сущностями/доменами (зависимости, обогащения, ограничения).';

COMMENT ON TABLE flowmeta.policy IS
'Мета-политики FlowMeta: инварианты и правила для доменов/сущностей.';
