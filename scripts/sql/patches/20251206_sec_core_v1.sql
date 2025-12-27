-- 20251206_sec_core_v1.sql
-- NDC-патч: создаёт и инициализирует ядро схемы sec.* (roles/policies/audit).
-- FlowSec Core v1.0
-- stack=sql
-- domain=security
-- goal=Ввести базовый модуль безопасности и политики для DevFactory/логистики/CRM.
-- summary=FlowSec ядро: sec.roles, sec.policies, sec.role_policy_bindings, sec.subject_roles, sec.audit_events, sec.log_event, представления эффективных политик.

CREATE SCHEMA IF NOT EXISTS sec;

-- ------------------------------------------------------------
-- 1. Роли безопасности
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sec.roles (
    role_code      text PRIMARY KEY,
    title          text NOT NULL,
    description    text,
    is_system      boolean NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- 2. Политики (policy = правило для домена)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sec.policies (
    policy_code    text PRIMARY KEY,
    title          text NOT NULL,
    description    text,
    target_domain  text NOT NULL, -- 'devfactory','logistics','crm','security', ...
    effect         text NOT NULL CHECK (effect IN ('allow','deny','audit')),
    condition      jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- 3. Связка ролей и политик
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sec.role_policy_bindings (
    role_code   text NOT NULL REFERENCES sec.roles(role_code) ON DELETE CASCADE,
    policy_code text NOT NULL REFERENCES sec.policies(policy_code) ON DELETE CASCADE,
    granted_at  timestamptz NOT NULL DEFAULT now(),
    granted_by  text,
    PRIMARY KEY (role_code, policy_code)
);

-- ------------------------------------------------------------
-- 4. Связка «субъект ↔ роль»
--    subject_type: 'user','service','ai_agent','tenant', ...
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sec.subject_roles (
    subject_type text NOT NULL, -- тип субъекта
    subject_id   text NOT NULL, -- идентификатор субъекта (user_id, service name, agent_id, ...)
    role_code    text NOT NULL REFERENCES sec.roles(role_code) ON DELETE CASCADE,
    tenant_id    text,          -- при необходимости: tenant, в пределах которого действует роль
    assigned_at  timestamptz NOT NULL DEFAULT now(),
    assigned_by  text,
    PRIMARY KEY(subject_type, subject_id, role_code)
);

CREATE INDEX IF NOT EXISTS idx_sec_subject_roles_role
    ON sec.subject_roles(role_code);

CREATE INDEX IF NOT EXISTS idx_sec_subject_roles_tenant
    ON sec.subject_roles(tenant_id);

-- ------------------------------------------------------------
-- 5. Аудит событий безопасности
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sec.audit_events (
    audit_id     bigserial PRIMARY KEY,
    ts           timestamptz NOT NULL DEFAULT now(),
    actor_type   text NOT NULL, -- 'user', 'system', 'ai_agent'
    actor_id     text NOT NULL, -- user_id, service name, etc.
    actor_role   text,          -- sec.roles.role_code
    domain       text NOT NULL, -- 'devfactory','logistics','crm','security',...
    action       text NOT NULL, -- 'dev_task_apply_patch', 'trip_plan_confirm', etc.
    object_type  text,          -- 'dev.dev_task','logistics.trip','crm.lead', ...
    object_id    text,
    success      boolean NOT NULL,
    severity     text,          -- 'info','warning','error','critical'
    request_id   uuid,
    remote_addr  text,
    user_agent   text,
    extra        jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (severity IS NULL OR severity IN ('info','warning','error','critical'))
);

CREATE INDEX IF NOT EXISTS idx_sec_audit_ts
    ON sec.audit_events(ts DESC);

CREATE INDEX IF NOT EXISTS idx_sec_audit_domain
    ON sec.audit_events(domain);

CREATE INDEX IF NOT EXISTS idx_sec_audit_actor
    ON sec.audit_events(actor_id);

CREATE INDEX IF NOT EXISTS idx_sec_audit_request
    ON sec.audit_events(request_id);

-- ------------------------------------------------------------
-- 6. Функция логирования события безопасности
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION sec.log_event(
    p_actor_type   text,
    p_actor_id     text,
    p_actor_role   text,
    p_domain       text,
    p_action       text,
    p_object_type  text,
    p_object_id    text,
    p_success      boolean,
    p_severity     text,
    p_request_id   uuid,
    p_remote_addr  text,
    p_user_agent   text,
    p_extra        jsonb DEFAULT '{}'::jsonb
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO sec.audit_events(
        actor_type, actor_id, actor_role, domain, action,
        object_type, object_id, success, severity,
        request_id, remote_addr, user_agent, extra
    )
    VALUES (
        p_actor_type, p_actor_id, p_actor_role, p_domain, p_action,
        p_object_type, p_object_id, p_success, p_severity,
        p_request_id, p_remote_addr, p_user_agent, COALESCE(p_extra, '{}'::jsonb)
    );
END;
$$;

-- ------------------------------------------------------------
-- 7. Базовые роли организма
-- ------------------------------------------------------------
INSERT INTO sec.roles(role_code, title, description, is_system)
VALUES
    ('architect','Architect','Главный архитектор организма; полный доступ к Earth/FlowMeta/FlowSec', true),
    ('eri_core','ERI Core','Ядро ERI/организма человека и семьи; специальные полномочия в домене eri', true),
    ('devfactory_core','DevFactory Core','Внутренние DevFactory-агенты и сервисы', true),
    ('devfactory_external_operator','DevFactory External Operator','Оператор, работающий с внешними задачами DevFactory через человека', false),
    ('logistics_planner','Logistics Planner','Оператор логистики и планировщика поездок', false),
    ('logistics_viewer','Logistics Readonly','Просмотрщик логистики и KPI без права изменений', false),
    ('crm_manager','CRM Manager','Работа с лидами, сделками и онбордингом клиентов', false),
    ('tenant_operator','Tenant Operator','Оператор со стороны клиента, ограниченный своим tenant', false),
    ('foxshell_operator','FoxShell Operator','Внутренний оператор foxctl/FoxShell', false)
ON CONFLICT (role_code) DO NOTHING;

-- ------------------------------------------------------------
-- 8. Базовые политики FlowSec для DevFactory / Logistics / CRM / Security
-- ------------------------------------------------------------
INSERT INTO sec.policies(policy_code, title, description, target_domain, effect, condition)
VALUES
    (
        'devfactory_internal_full',
        'DevFactory internal full access',
        'Полный доступ к внутренним DevFactory-проектам с NDC и FlowSec-проверками',
        'devfactory',
        'allow',
        jsonb_build_object(
            'scope','internal',
            'ndc_only', true,
            'forbidden_domains', jsonb_build_array('physics','tpm','interplane','sec'),
            'allowed_actions', jsonb_build_array('create_task','plan','generate_patch','apply_patch','kpi_read')
        )
    ),
    (
        'devfactory_external_limited',
        'DevFactory external limited',
        'Работа с внешними проектами только через разрешённые стеки/директории без доступа к ядру организма',
        'devfactory',
        'allow',
        jsonb_build_object(
            'scope','external',
            'ndc_only', true,
            'allowed_stacks', jsonb_build_array('sql','python','js'),
            'forbidden_domains', jsonb_build_array('flowmeta','sec','physics','tpm','interplane','billing','crm','logistics'),
            'allowed_actions', jsonb_build_array('create_task','plan','generate_patch','kpi_read')
        )
    ),
    (
        'devfactory_no_physics',
        'DevFactory cannot patch physics',
        'Жёсткий запрет DevFactory на патчинг доменов physics/tpm/interplane',
        'devfactory',
        'deny',
        jsonb_build_object(
            'forbidden_domains', jsonb_build_array('physics','tpm','interplane')
        )
    ),
    (
        'logistics_tenant_scoped_rw',
        'Logistics tenant-scoped read/write',
        'Работа с логистическими данными в пределах одного tenant',
        'logistics',
        'allow',
        jsonb_build_object(
            'tenant_scope','own',
            'allowed_actions', jsonb_build_array('read','plan','confirm','kpi_read')
        )
    ),
    (
        'logistics_readonly',
        'Logistics readonly',
        'Только просмотр логистики и KPI',
        'logistics',
        'allow',
        jsonb_build_object(
            'allowed_actions', jsonb_build_array('read','kpi_read'),
            'readonly', true
        )
    ),
    (
        'crm_tenant_scoped_rw',
        'CRM tenant-scoped read/write',
        'Работа с лидами, сделками и онбордингом в пределах одного tenant',
        'crm',
        'allow',
        jsonb_build_object(
            'tenant_scope','own',
            'allowed_actions', jsonb_build_array('read','create','update','kpi_read')
        )
    ),
    (
        'security_observe_everything',
        'Security can observe everything',
        'Полный доступ FlowSec к аудиту и чтению любых доменов без права изменения',
        'security',
        'allow',
        jsonb_build_object(
            'allowed_actions', jsonb_build_array('audit_read','kpi_read'),
            'readonly', true
        )
    )
ON CONFLICT (policy_code) DO NOTHING;

-- ------------------------------------------------------------
-- 9. Привязка политик к ролям
-- ------------------------------------------------------------
INSERT INTO sec.role_policy_bindings(role_code, policy_code, granted_by)
VALUES
    -- Architect: всё, плюс наблюдение безопасности
    ('architect','devfactory_internal_full','seed'),
    ('architect','devfactory_external_limited','seed'),
    ('architect','devfactory_no_physics','seed'),
    ('architect','logistics_tenant_scoped_rw','seed'),
    ('architect','crm_tenant_scoped_rw','seed'),
    ('architect','security_observe_everything','seed'),

    -- DevFactory core: внутренние проекты + запрет физики
    ('devfactory_core','devfactory_internal_full','seed'),
    ('devfactory_core','devfactory_no_physics','seed'),

    -- Оператор DevFactory external
    ('devfactory_external_operator','devfactory_external_limited','seed'),

    -- Логистика
    ('logistics_planner','logistics_tenant_scoped_rw','seed'),
    ('logistics_viewer','logistics_readonly','seed'),

    -- CRM
    ('crm_manager','crm_tenant_scoped_rw','seed'),

    -- FoxShell: может наблюдать аудит
    ('foxshell_operator','security_observe_everything','seed')
ON CONFLICT DO NOTHING;

-- ------------------------------------------------------------
-- 10. Представления эффективных политик
-- ------------------------------------------------------------

-- Роль → какие активные политики на ней висят
CREATE OR REPLACE VIEW sec.v_role_policies_effective AS
SELECT
    r.role_code,
    r.title       AS role_title,
    p.policy_code,
    p.title       AS policy_title,
    p.target_domain,
    p.effect,
    p.condition,
    p.is_active
FROM sec.role_policy_bindings b
JOIN sec.roles    r ON r.role_code    = b.role_code
JOIN sec.policies p ON p.policy_code  = b.policy_code
WHERE p.is_active;

-- Субъект → какие активные политики у него есть (через роли)
CREATE OR REPLACE VIEW sec.v_subject_policies_effective AS
SELECT
    sr.subject_type,
    sr.subject_id,
    sr.tenant_id,
    v.role_code,
    v.role_title,
    v.policy_code,
    v.policy_title,
    v.target_domain,
    v.effect,
    v.condition
FROM sec.subject_roles sr
JOIN sec.v_role_policies_effective v
  ON v.role_code = sr.role_code;

-- END OF 20251206_sec_core_v1.sql
