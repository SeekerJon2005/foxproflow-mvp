-- 20251206_sec_subjects_seed_v1.sql
-- NDC-патч: первичная привязка субъектов к ролям FlowSec.
-- goal=Зафиксировать, кто является Архитектором и какими ролями обладают базовые сервисы.
-- stack=sql
-- domain=security

-- Архитектор организма:
-- Используем реальный e-mail Архитектора как subject_id.
INSERT INTO sec.subject_roles (
    subject_type,
    subject_id,
    role_code,
    tenant_id,
    assigned_at,
    assigned_by
)
VALUES
    (
        'user',
        'e.yatskov@foxproflow.ru',
        'architect',
        NULL,
        now(),
        'seed:2025-12-06'
    )
ON CONFLICT (subject_type, subject_id, role_code) DO NOTHING;

-- Внутренний DevFactory-core (Celery/worker, который исполняет devfactory-задачи).
-- subject_id задаём как стабильный сервисный идентификатор.
INSERT INTO sec.subject_roles (
    subject_type,
    subject_id,
    role_code,
    tenant_id,
    assigned_at,
    assigned_by
)
VALUES
    (
        'service',
        'svc.devfactory.core',
        'devfactory_core',
        NULL,
        now(),
        'seed:2025-12-06'
    )
ON CONFLICT (subject_type, subject_id, role_code) DO NOTHING;

-- FoxShell / foxctl оператор (внутренний интерфейс управления).
INSERT INTO sec.subject_roles (
    subject_type,
    subject_id,
    role_code,
    tenant_id,
    assigned_at,
    assigned_by
)
VALUES
    (
        'service',
        'svc.foxshell',
        'foxshell_operator',
        NULL,
        now(),
        'seed:2025-12-06'
    )
ON CONFLICT (subject_type, subject_id, role_code) DO NOTHING;

-- При необходимости сюда же можно добавлять:
-- - внешних DevFactory-операторов (subject_type='user', role_code='devfactory_external_operator'),
-- - логистов (role_code='logistics_planner'),
-- - CRM-менеджеров (role_code='crm_manager'),
-- - операторов клиентов (role_code='tenant_operator', с заполненным tenant_id).
