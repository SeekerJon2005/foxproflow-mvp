-- 20251207_flowmeta_v0_2_domains.sql
-- FlowMeta v0.2: базовые домены (без изменения структуры таблицы flowmeta.domain)

DO $$
BEGIN
    -- 1. Гарантируем наличие схемы flowmeta и таблицы domain (code, meta)
    PERFORM 1
    FROM information_schema.schemata
    WHERE schema_name = 'flowmeta';

    IF NOT FOUND THEN
        EXECUTE 'CREATE SCHEMA flowmeta';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'flowmeta'
          AND table_name   = 'domain'
    ) THEN
        EXECUTE $DDL$
            CREATE TABLE flowmeta.domain (
                code text PRIMARY KEY,
                meta jsonb NOT NULL DEFAULT '{}'::jsonb
            );
        $DDL$;
    END IF;

    -- 2. Функция безопасного upsert домена: только JSONB, без новых колонок
    CREATE OR REPLACE FUNCTION flowmeta.upsert_domain(
        p_code        text,
        p_title       text,
        p_tier        text,
        p_importance  text,
        p_description text
    )
    RETURNS void
    LANGUAGE plpgsql
    AS $FUNC$
    BEGIN
        -- если домена ещё нет — создаём с пустым meta
        INSERT INTO flowmeta.domain (code, meta)
        VALUES (p_code, '{}'::jsonb)
        ON CONFLICT (code) DO NOTHING;

        -- обновляем только JSON-поля внутри meta, не трогаем существующие вложенные структуры
        UPDATE flowmeta.domain
        SET meta =
            jsonb_set(
                jsonb_set(
                    jsonb_set(
                        jsonb_set(
                            meta,
                            '{title}',       to_jsonb(p_title),      true
                        ),
                        '{tier}',        to_jsonb(p_tier),       true
                    ),
                    '{importance}',  to_jsonb(p_importance), true
                ),
                '{description}', to_jsonb(p_description), true
            )
        WHERE code = p_code;
    END;
    $FUNC$;

    -- 3. Заполняем/обновляем базовые домены FlowMeta v0.2

    PERFORM flowmeta.upsert_domain(
        'organism.core',
        'Ядро организма',
        'organism',
        'core',
        'Идентичность, каноны, Master Language Genome, базовая память и непрерывность существования организма.'
    );

    PERFORM flowmeta.upsert_domain(
        'organism.cognition',
        'ERI / MindOS',
        'organism',
        'core',
        'Разум ERI, reasoning, высокоуровневые FlowLang-планы и объяснимость решений.'
    );

    PERFORM flowmeta.upsert_domain(
        'organism.topology',
        'TPM / топологический орган',
        'organism',
        'research',
        'Топологическое перемещение (TPM), сканирование метрики, когерентность и безопасные переходы.'
    );

    PERFORM flowmeta.upsert_domain(
        'organism.protection',
        'Защитный орган',
        'organism',
        'core',
        'Щиты, маскировка, иммунные реакции тела космолёта, согласованные с FlowSec.'
    );

    PERFORM flowmeta.upsert_domain(
        'organism.energy',
        'Энергетическое ядро',
        'organism',
        'core',
        'Когерентность энергии, питание TPM/ShipOS и стабильность энергетической системы.'
    );

    PERFORM flowmeta.upsert_domain(
        'organism.memory',
        'Орган памяти',
        'organism',
        'core',
        'Долговременная память, история состояний, Master Canon и история принятых решений.'
    );

    PERFORM flowmeta.upsert_domain(
        'organism.growth',
        'Орган роста (DevFactory)',
        'organism',
        'core',
        'DevFactory как орган эволюции организма: генерация кода, патчей, DSL и развитие FlowMeta/FlowLang/FlowSec.'
    );

    PERFORM flowmeta.upsert_domain(
        'organism.communication',
        'Орган коммуникаций',
        'organism',
        'support',
        'Внутренний контур связи FoxCom, интеграция ERI в рабочие и личные пространства.'
    );

    PERFORM flowmeta.upsert_domain(
        'flowmeta',
        'FlowMeta ядро',
        'earth',
        'core',
        'Онтология доменов, сущностей, связей и политик. Скелет смысла для Earth-слоя.'
    );

    PERFORM flowmeta.upsert_domain(
        'flowlang',
        'FlowLang планы и намерения',
        'earth',
        'core',
        'Декларативные планы, цели, шаги, эффекты и ограничения для Earth-операций.'
    );

    PERFORM flowmeta.upsert_domain(
        'flowsec',
        'FlowSec / sec.*',
        'earth',
        'core',
        'Земной слой безопасности: роли, политики, audit, привязка к доменам и действиям.'
    );

    PERFORM flowmeta.upsert_domain(
        'devfactory',
        'DevFactory / орган роста',
        'earth',
        'core',
        'Земная проекция органа роста: dev.dev_task, dev.dev_order, capsules и интеграция с CRM/Billing/FlowMeta.'
    );

    PERFORM flowmeta.upsert_domain(
        'logistics',
        'Логистика / Rolling Horizon',
        'earth',
        'core',
        'Парки ТС, рейсы, грузы, окна погрузки/выгрузки, планировщик и телеметрия.'
    );

    PERFORM flowmeta.upsert_domain(
        'crm',
        'CRM / SalesFox',
        'earth',
        'core',
        'Лиды, тенанты, сделки, контактные лица, профиль клиента и связь с DevFactory/Billing.'
    );

    PERFORM flowmeta.upsert_domain(
        'billing',
        'BillingFox',
        'earth',
        'core',
        'Подписки, счета, платежи и статусы оплаты, связь с DevOrders.'
    );

    PERFORM flowmeta.upsert_domain(
        'onboarding',
        'OnboardFox',
        'earth',
        'support',
        'Онбординг новых клиентов FoxProFlow (datasets, KPI, симуляции).'
    );

    PERFORM flowmeta.upsert_domain(
        'observability',
        'Observability 2.0 / ops.*',
        'earth',
        'core',
        'Единый журнал событий, routine tasks, agent events и KPI-срезы.'
    );

    PERFORM flowmeta.upsert_domain(
        'analytics',
        'Аналитические витрины / analytics.*',
        'earth',
        'support',
        'Витрины KPI, рыночные витрины и агрегаты для агентов и UI.'
    );

    PERFORM flowmeta.upsert_domain(
        'security',
        'Security Foundation / sec.*',
        'earth',
        'core',
        'Базовый модуль безопасности: sec.roles, sec.policies, sec.subject_roles, sec.audit_events и Sovereign Safety.'
    );

    PERFORM flowmeta.upsert_domain(
        'eri.edu',
        'ERI Education',
        'earth',
        'support',
        'Образовательный контур ERI, траектории обучения и метрики.'
    );

    PERFORM flowmeta.upsert_domain(
        'architecture.building',
        'Архитектура зданий и инженерных систем',
        'earth',
        'research',
        'Моделирование зданий, инженерных систем и MEP-сетей; база для модулей и баз.'
    );

    PERFORM flowmeta.upsert_domain(
        'robotics',
        'RoboticsOS',
        'earth',
        'research',
        'Мозговой слой для роботов: сенсоры, планирование, социальное взаимодействие.'
    );

    PERFORM flowmeta.upsert_domain(
        'air.urban',
        'Urban Air FlowOS',
        'earth',
        'research',
        'Орган управления городской авиацией и дрон-флотом, интегрированный с логистикой и FlowSec.'
    );

END;
$$;
