-- 20251125_flowmeta_schema.sql
-- FoxProFlow — FlowMeta: базовая схема мета-языка поведения систем.
-- NDC: только CREATE SCHEMA/TABLE/INDEX IF NOT EXISTS + INSERT ... ON CONFLICT,
--      никаких DROP/ALTER COLUMN/DELETE.
--
-- Структура:
--  0) Схема flowmeta
--  1) Таблицы: domain, dsl, effect_type, agent_class, plan_class, policy
--  2) Индексы
--  3) Идемпотентный сидинг базовых доменов/DSL/эффектов/классов/политик

CREATE SCHEMA IF NOT EXISTS flowmeta;

-- =====================================================================
-- 0. Domain (логические домены систем: logistics, dev, security, ...)
-- =====================================================================

CREATE TABLE IF NOT EXISTS flowmeta.domain (
    id           bigserial PRIMARY KEY,
    code         text        NOT NULL,              -- 'logistics','dev','security','accounting',...
    description  text,
    meta         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_flowmeta_domain_code
    ON flowmeta.domain (code);

COMMENT ON TABLE flowmeta.domain IS
    'FlowMeta: логические домены (logistics, dev, security, accounting, legal, observability, citymap, ...).';
COMMENT ON COLUMN flowmeta.domain.code IS
    'Короткий код домена (primary business area): logistics/dev/security/accounting/legal/observability/citymap/...';
COMMENT ON COLUMN flowmeta.domain.meta IS
    'Дополнительные атрибуты домена (JSON, свободная форма).';

-- =====================================================================
-- 1. DSL (доменные языки: 'autoplan', 'dev', 'flowsec', 'etl', 'kpi', ...)
-- =====================================================================

CREATE TABLE IF NOT EXISTS flowmeta.dsl (
    id            bigserial PRIMARY KEY,
    code          text        NOT NULL,         -- код DSL: 'autoplan','dev','flowsec',...
    domain        text        NOT NULL,         -- домен: 'logistics','dev','security',...
    description   text,
    files_pattern text,                         -- паттерн файлов (glob), например: 'flow/autoplan/*.flow'
    enabled       boolean     NOT NULL DEFAULT TRUE,
    meta          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_flowmeta_dsl_code
    ON flowmeta.dsl (code);

COMMENT ON TABLE flowmeta.dsl IS
    'FlowMeta: зарегистрированные DSL внутри доменов (autoplan, dev, flowsec, etl, kpi, agents, citymap, ...).';
COMMENT ON COLUMN flowmeta.dsl.code IS
    'Код DSL: autoplan/dev/flowsec/etl/kpi/agents/citymap/...';
COMMENT ON COLUMN flowmeta.dsl.domain IS
    'Код домена (flowmeta.domain.code), к которому относится DSL.';
COMMENT ON COLUMN flowmeta.dsl.files_pattern IS
    'Glob-паттерн файлов .flow, относящихся к данному DSL.';
COMMENT ON COLUMN flowmeta.dsl.enabled IS
    'Флаг активности DSL (можно мягко отключать язык, не трогая данные).';

-- =====================================================================
-- 2. EffectType (DbRead/DbWrite/FSWrite/NetExternal/OSRMRoute/MLCall/GitOp/CIRun, ...)
-- =====================================================================

CREATE TABLE IF NOT EXISTS flowmeta.effect_type (
    id           bigserial PRIMARY KEY,
    code         text        NOT NULL,         -- 'DbRead','DbWrite','FSWrite','NetExt',...
    kind         text        NOT NULL,         -- 'db','fs','net','osrm','ml','git','ci',...
    description  text,
    scope        text[]      NOT NULL DEFAULT '{}'::text[], -- список паттернов ресурсов (например 'public.*')
    meta         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_flowmeta_effect_type_code
    ON flowmeta.effect_type (code);

COMMENT ON TABLE flowmeta.effect_type IS
    'FlowMeta: типы эффектов (операции над БД, FS, сетью, OSRM, ML, Git, CI/CD и др.).';
COMMENT ON COLUMN flowmeta.effect_type.code IS
    'Короткий код эффекта: DbRead/DbWrite/FSRead/FSWrite/NetInternal/NetExternal/OSRMRoute/MLCall/GitOp/CIRun/...';
COMMENT ON COLUMN flowmeta.effect_type.kind IS
    'Грубый тип эффекта: db/fs/net/osrm/ml/git/ci/... (для высокоуровневой фильтрации и политик).';
COMMENT ON COLUMN flowmeta.effect_type.scope IS
    'Список паттернов ресурсов (например, списки таблиц/схем, URL, директории), на которые распространяется эффект.';
COMMENT ON COLUMN flowmeta.effect_type.meta IS
    'Дополнительное описание/атрибуты эффекта (JSON).';

-- =====================================================================
-- 3. AgentClass (типы агентов: AutoplanAgent, DevAgent, SecFox, GuardFox, DocFox, CityMapAgent, ...)
-- =====================================================================

CREATE TABLE IF NOT EXISTS flowmeta.agent_class (
    id             bigserial PRIMARY KEY,
    code           text        NOT NULL,          -- 'AutoplanAgent','DevAgent','SecFox',...
    domain         text        NOT NULL,          -- 'logistics','dev','security',...
    dsl_code       text,                          -- какой DSL основой (например 'autoplan')
    description    text,
    allow_effects  text[]      NOT NULL DEFAULT '{}'::text[], -- список effect_type.code, которые разрешены
    deny_effects   text[]      NOT NULL DEFAULT '{}'::text[], -- список effect_type.code, которые запрещены
    meta           jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_flowmeta_agent_class_code
    ON flowmeta.agent_class (code);

CREATE INDEX IF NOT EXISTS ix_flowmeta_agent_class_domain
    ON flowmeta.agent_class (domain);

COMMENT ON TABLE flowmeta.agent_class IS
    'FlowMeta: классы агентов и их разрешённые/запрещённые эффекты (AutoplanAgent, DevAgent, SecFox, GuardFox, ...).';
COMMENT ON COLUMN flowmeta.agent_class.code IS
    'Уникальный код класса агента: AutoplanAgent/DevAgent/SecFox/GuardFox/DocFox/CityMapAgent/...';
COMMENT ON COLUMN flowmeta.agent_class.domain IS
    'Домен (flowmeta.domain.code), к которому относится агент.';
COMMENT ON COLUMN flowmeta.agent_class.dsl_code IS
    'Основной DSL (flowmeta.dsl.code), на котором описываются планы этого агента.';
COMMENT ON COLUMN flowmeta.agent_class.allow_effects IS
    'Белый список эффектов (effect_type.code), которые агент может использовать.';
COMMENT ON COLUMN flowmeta.agent_class.deny_effects IS
    'Чёрный список эффектов (effect_type.code), которые агенту явно запрещены.';
COMMENT ON COLUMN flowmeta.agent_class.meta IS
    'Дополнительные атрибуты класса агента (JSON).';

-- =====================================================================
-- 4. PlanClass (типы планов: AutoplanPlan, DevPlan, SecurityPolicy, ETLPlan, KPIPlan, ...)
-- =====================================================================

CREATE TABLE IF NOT EXISTS flowmeta.plan_class (
    id              bigserial PRIMARY KEY,
    code            text        NOT NULL,          -- 'AutoplanPlan','DevPlan','SecurityPolicy',...
    dsl_code        text        NOT NULL,          -- DSL, к которому относится план: 'autoplan','dev','flowsec',...
    description     text,
    default_effects text[]      NOT NULL DEFAULT '{}'::text[], -- базовый набор effect_type.code для планов этого класса
    meta            jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_flowmeta_plan_class_code
    ON flowmeta.plan_class (code);

CREATE INDEX IF NOT EXISTS ix_flowmeta_plan_class_dsl
    ON flowmeta.plan_class (dsl_code);

COMMENT ON TABLE flowmeta.plan_class IS
    'FlowMeta: классы планов (AutoplanPlan, DevPlan, SecurityPolicy, ETLPlan, KPIPlan, ...).';
COMMENT ON COLUMN flowmeta.plan_class.code IS
    'Уникальный код класса плана: AutoplanPlan/DevPlan/SecurityPolicy/ETLPlan/KPIPlan/...';
COMMENT ON COLUMN flowmeta.plan_class.dsl_code IS
    'Имя DSL (flowmeta.dsl.code), к которому относится данный класс планов.';
COMMENT ON COLUMN flowmeta.plan_class.default_effects IS
    'Набор effect_type.code по умолчанию для планов этого класса.';
COMMENT ON COLUMN flowmeta.plan_class.meta IS
    'Дополнительные атрибуты класса плана (JSON).';

-- =====================================================================
-- 5. Policy/Invariant (глобальные и локальные правила FlowMeta)
-- =====================================================================

CREATE TABLE IF NOT EXISTS flowmeta.policy (
    id           bigserial PRIMARY KEY,
    code         text        NOT NULL,          -- 'NoRawPublicWrite','NoExternalNetInCore',...
    kind         text        NOT NULL,          -- 'invariant','allow','deny','constraint',...
    description  text,
    definition   jsonb       NOT NULL DEFAULT '{}'::jsonb, -- нормализованное представление политики (AST/JSON)
    enabled      boolean     NOT NULL DEFAULT TRUE,
    meta         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_flowmeta_policy_code
    ON flowmeta.policy (code);

CREATE INDEX IF NOT EXISTS ix_flowmeta_policy_kind
    ON flowmeta.policy (kind);

COMMENT ON TABLE flowmeta.policy IS
    'FlowMeta: политики и инварианты (глобальные/локальные правила для доменов, DSL, агентов и планов).';
COMMENT ON COLUMN flowmeta.policy.code IS
    'Код политики/инварианта: NoExternalNetInCore/GuardRequiresReadOnly/...';
COMMENT ON COLUMN flowmeta.policy.kind IS
    'Тип политики: invariant/allow/deny/constraint/...';
COMMENT ON COLUMN flowmeta.policy.definition IS
    'Нормализованное представление правила (AST/JSON), которое будет интерпретировать FlowMeta/FlowSec.';
COMMENT ON COLUMN flowmeta.policy.enabled IS
    'Флаг активности политики.';
COMMENT ON COLUMN flowmeta.policy.meta IS
    'Дополнительные атрибуты/метаданные политики (JSON).';

-- (Опционально: в будущем можно добавить триггер обновления updated_at,
--  аналогичный ops.tg_set_updated_at, но для Этапа 1 это не обязательно.)

-- =====================================================================
-- 6. Идемпотентный сидинг базовых доменов и сущностей FlowMeta
-- =====================================================================

-- 6.1. Домены
INSERT INTO flowmeta.domain (code, description)
VALUES
    ('logistics',    'Логистика и автоплан'),
    ('dev',          'Разработка и DevFactory'),
    ('security',     'Безопасность и FlowSec'),
    ('accounting',   'Бухгалтерия и налоговый контур'),
    ('legal',        'Юридический контур'),
    ('observability','Наблюдаемость, метрики и события'),
    ('citymap',      'Геоданные, города и регионы')
ON CONFLICT (code) DO UPDATE
SET description = EXCLUDED.description;

-- 6.2. DSL
INSERT INTO flowmeta.dsl (code, domain, description, files_pattern, enabled)
VALUES
    ('autoplan', 'logistics',
        'Планы автопланировщика (оконные профили, economics, scoring)',
        'flow/autoplan/*.flow',
        TRUE),
    ('etl', 'logistics',
        'ETL и пайплайны данных (ATI, GEO, OSRM)',
        'flow/etl/*.flow',
        TRUE),
    ('kpi', 'observability',
        'Определения KPI, витрин, ежедневных срезов',
        'flow/kpi/*.flow',
        TRUE),
    ('dev', 'dev',
        'DevFactory/FlowDev — описание микросервисов, API и агентов разработки',
        'flow/dev/*.flow',
        TRUE),
    ('flowsec', 'security',
        'FlowSec DSL — политики безопасности, эффекты и self-healing',
        'flow/security/*.flow',
        TRUE),
    ('agents', 'dev',
        'Определения агентов и их расписаний (рои LogFox, AutoplanGuard, DocFox, ...)',
        'flow/agents/*.flow',
        TRUE),
    ('citymap', 'citymap',
        'Правила обогащения геоданных, city_map и регионов',
        'flow/citymap/*.flow',
        TRUE)
ON CONFLICT (code) DO UPDATE
SET
    domain        = EXCLUDED.domain,
    description   = EXCLUDED.description,
    files_pattern = EXCLUDED.files_pattern,
    enabled       = EXCLUDED.enabled;

-- 6.3. EffectType
INSERT INTO flowmeta.effect_type (code, kind, description, scope)
VALUES
    ('DbRead',       'db',   'Чтение из БД',                       '{}'::text[]),
    ('DbWrite',      'db',   'Запись/изменение в БД',              '{}'::text[]),
    ('FSRead',       'fs',   'Чтение файловой системы',           '{}'::text[]),
    ('FSWrite',      'fs',   'Запись/изменение файловой системы', '{}'::text[]),
    ('NetInternal',  'net',  'Сетевые вызовы внутри кластера',    '{}'::text[]),
    ('NetExternal',  'net',  'Сетевые вызовы наружу',             '{}'::text[]),
    ('OSRMRoute',    'osrm', 'Маршрутизация/OSRM',                '{}'::text[]),
    ('MLCall',       'ml',   'Вызов ML/LLM моделей',              '{}'::text[]),
    ('GitOp',        'git',  'Операции с Git-репозиториями',      '{}'::text[]),
    ('CIRun',        'ci',   'CI/CD задачи и пайплайны',          '{}'::text[])
ON CONFLICT (code) DO UPDATE
SET
    kind        = EXCLUDED.kind,
    description = EXCLUDED.description,
    scope       = EXCLUDED.scope;

-- 6.4. AgentClass
INSERT INTO flowmeta.agent_class (code, domain, dsl_code, description, allow_effects, deny_effects)
VALUES
    ('AutoplanAgent', 'logistics', 'autoplan',
        'Агенты автопланировщика: генерация, аудит и guard-паттерны для рейсов',
        ARRAY['DbRead','DbWrite','OSRMRoute','NetInternal'],
        ARRAY['NetExternal']),
    ('DevAgent', 'dev', 'dev',
        'DevFactory-агенты (DevFox/CodeFox/TestFox/MigrateFox)',
        ARRAY['DbRead','DbWrite','GitOp','CIRun'],
        ARRAY['NetExternal']),
    ('SecFox', 'security', 'flowsec',
        'Агенты безопасности: анализ логов, политик и аномалий',
        ARRAY['DbRead','MLCall'],
        ARRAY['NetExternal','FSWrite']),
    ('GuardFox', 'security', 'flowsec',
        'Guard-агенты, которые проверяют эффекты планов и агентов перед применением',
        ARRAY['DbRead'],
        ARRAY['DbWrite','NetExternal','FSWrite']),
    ('DocFox', 'legal', 'agents',
        'Агенты документооборота и юридического контура',
        ARRAY['DbRead','DbWrite','MLCall'],
        ARRAY['NetExternal']),
    ('CityMapAgent', 'citymap', 'citymap',
        'Агенты автоподбора и обогащения city_map/регионов',
        ARRAY['DbRead','DbWrite','OSRMRoute'],
        ARRAY['NetExternal'])
ON CONFLICT (code) DO UPDATE
SET
    domain        = EXCLUDED.domain,
    dsl_code      = EXCLUDED.dsl_code,
    description   = EXCLUDED.description,
    allow_effects = EXCLUDED.allow_effects,
    deny_effects  = EXCLUDED.deny_effects;

-- 6.5. PlanClass
INSERT INTO flowmeta.plan_class (code, dsl_code, description, default_effects)
VALUES
    ('AutoplanPlan', 'autoplan',
        'Планы автопланировщика: окна, scoring, economics и SLA',
        ARRAY['DbRead','DbWrite','OSRMRoute']),
    ('DevPlan', 'dev',
        'DevFactory-планы: генерация микросервисов, миграций, тестов',
        ARRAY['DbRead','DbWrite','GitOp','CIRun']),
    ('SecurityPolicy', 'flowsec',
        'Политики безопасности и эффекты FlowSec',
        ARRAY['DbRead']),
    ('ETLPlan', 'etl',
        'Планы ETL/ingest-процессов (ATI, GEO, OSRM, аналитика)',
        ARRAY['DbRead','DbWrite','NetInternal']),
    ('KPIPlan', 'kpi',
        'Определения витрин KPI и ежедневных отчётов',
        ARRAY['DbRead','DbWrite'])
ON CONFLICT (code) DO UPDATE
SET
    dsl_code        = EXCLUDED.dsl_code,
    description     = EXCLUDED.description,
    default_effects = EXCLUDED.default_effects;

-- 6.6. Базовые политики FlowMeta (черновые)
INSERT INTO flowmeta.policy (code, kind, description, definition, enabled)
VALUES
    ('NoExternalNetInCore', 'invariant',
        'Запрет внешних сетевых вызовов для core-планов и агентов без явного разрешения',
        '{"rule":"no_net_external_without_explicit_allow"}'::jsonb,
        TRUE),
    ('GuardRequiresReadOnly', 'constraint',
        'Guard-агенты по умолчанию только читают данные (DbRead) и не могут писать в прод',
        '{"rule":"guard_agents_read_only_by_default"}'::jsonb,
        TRUE)
ON CONFLICT (code) DO UPDATE
SET
    kind        = EXCLUDED.kind,
    description = EXCLUDED.description,
    definition  = EXCLUDED.definition,
    enabled     = EXCLUDED.enabled;
