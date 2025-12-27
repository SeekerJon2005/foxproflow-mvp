-- 20251206_flowmeta_devfactory_external_v1.sql
-- stack=sql
-- goal=Добавить/обновить FlowMeta-профиль devfactory.external для работы DevFactory во внешних проектах.
-- summary=Расширяет meta домена flowmeta.domain(code='devfactory') секцией external_profiles.devfactory.external, не трогая другие колонки.

DO $$
DECLARE
    v_meta   jsonb;
    v_config jsonb;
BEGIN
    -- Базовый JSON-конфиг профиля devfactory.external
    v_config := jsonb_build_object(
        'capsule_type', 'Capsule.DevFactory.Collaboration',
        'description', 'Профиль devfactory.external для работы DevFactory с внешними репозиториями по капсуле Capsule.DevFactory.Collaboration.',
        'flowsec_profile', 'devfactory.external',
        'allowed_stacks', jsonb_build_array(
            'python-backend',
            'sql-postgres',
            'docs-markdown',
            'infra-docker'
        ),
        'default_capsule_locations', jsonb_build_array(
            'FoxProFlow_AICapsule_v1.ffc',
            '.foxproflow/FoxProFlow_AICapsule_v1.ffc'
        ),
        'limits', jsonb_build_object(
            'max_tasks_per_day',        100,
            'max_changeset_files',      50,
            'max_changeset_size_kb',    512,
            'max_parallel_tasks',       8
        ),
        'review', jsonb_build_object(
            'require_human_review', true,
            'allowed_review_roles', jsonb_build_array(
                'client_architect',
                'client_senior_dev',
                'foxproflow_architect'
            )
        ),
        'enforced_policies', jsonb_build_array(
            'devfactory_ndc_only',
            'devfactory_external_no_drop',
            'devfactory_external_no_shell',
            'devfactory_external_allowed_dirs_only',
            'devfactory_external_no_prod_secrets'
        ),
        'filesystem', jsonb_build_object(
            'patch_whitelist_dirs', jsonb_build_array(
                '.',
                'src',
                'scripts',
                'docs',
                'migrations',
                'config'
            ),
            'forbidden_paths', jsonb_build_array(
                '.git',
                '.foxproflow/secrets',
                'tmp',
                'logs'
            )
        ),
        'sql', jsonb_build_object(
            'require_ndc_migrations', true,
            'forbidden_operations', jsonb_build_array(
                'DROP TABLE',
                'DROP SCHEMA',
                'ALTER TABLE DROP COLUMN',
                'ALTER TABLE ALTER COLUMN TYPE'
            ),
            'default_migration_dir', 'scripts/sql/patches'
        ),
        'runtime', jsonb_build_object(
            'allow_network_calls', false,
            'allow_shell_exec',    false,
            'allow_file_create_outside_repo', false
        )
    );

    -- Пытаемся прочитать существующий meta для домена devfactory
    SELECT d.meta
    INTO v_meta
    FROM flowmeta.domain AS d
    WHERE d.code = 'devfactory'
    FOR UPDATE;

    IF NOT FOUND THEN
        -- Если домена devfactory ещё нет, создаём минимальный meta и добавляем external-профиль
        v_meta := jsonb_build_object(
            'devfactory_spec', jsonb_build_object(
                'description', 'DevFactory core domain (орган роста FoxProFlow, генерирует патчи и код).',
                'notes', jsonb_build_array(
                    'DevFactory никогда не продаётся как платформа. Наружу отдаётся только результат (код/функции).',
                    'Изменения выполняются по принципу NDC (Non-Destructive Change).'
                )
            )
        );

        v_meta := jsonb_set(
            v_meta,
            '{external_profiles,devfactory.external}',
            v_config,
            true
        );

        EXECUTE
            'INSERT INTO flowmeta.domain (code, meta) VALUES ($1, $2)'
        USING
            'devfactory', v_meta;
    ELSE
        -- Домен есть — дописываем/обновляем external_profiles.devfactory.external
        IF v_meta IS NULL THEN
            v_meta := '{}'::jsonb;
        END IF;

        v_meta := jsonb_set(
            v_meta,
            '{external_profiles,devfactory.external}',
            v_config,
            true
        );

        EXECUTE
            'UPDATE flowmeta.domain SET meta = $1 WHERE code = $2'
        USING
            v_meta, 'devfactory';
    END IF;
END;
$$ LANGUAGE plpgsql;
