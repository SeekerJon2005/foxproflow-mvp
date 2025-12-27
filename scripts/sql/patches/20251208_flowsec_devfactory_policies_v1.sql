-- 20251208_flowsec_devfactory_policies_v1.sql
-- FlowSec: политики и биндинги для домена devfactory.
-- Добавляем политику devfactory_view_tasks и привязываем её к роли architect.

DO $$
BEGIN
    ----------------------------------------------------------------------
    -- 1. Убеждаемся, что базовые таблицы FlowSec существуют
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'sec' AND table_name = 'policies'
    ) THEN
        RAISE EXCEPTION 'sec.policies is missing; apply sec_core_v1 first';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'sec' AND table_name = 'role_policy_bindings'
    ) THEN
        RAISE EXCEPTION 'sec.role_policy_bindings is missing; apply sec_core_v1 first';
    END IF;

    ----------------------------------------------------------------------
    -- 2. Политика devfactory_view_tasks
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sec.policies p
        WHERE p.policy_code = 'devfactory_view_tasks'
    ) THEN
        INSERT INTO sec.policies (
            policy_code,
            title,
            description,
            target_domain,
            effect,
            condition,
            is_active,
            decision,
            domain,
            action
        )
        VALUES (
            'devfactory_view_tasks',
            'DevFactory: просмотр задач',
            'Разрешает чтение и создание задач DevFactory (view_tasks) в домене devfactory.',
            'devfactory',
            'allow',
            '{}'::jsonb,
            true,
            'allow',
            'devfactory',
            'view_tasks'
        );
    END IF;

    ----------------------------------------------------------------------
    -- 3. Привязка политики к роли architect
    ----------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sec.role_policy_bindings b
        WHERE b.role_code   = 'architect'
          AND b.policy_code = 'devfactory_view_tasks'
    ) THEN
        INSERT INTO sec.role_policy_bindings (role_code, policy_code)
        VALUES ('architect', 'devfactory_view_tasks');
    END IF;

END;
$$ LANGUAGE plpgsql;
