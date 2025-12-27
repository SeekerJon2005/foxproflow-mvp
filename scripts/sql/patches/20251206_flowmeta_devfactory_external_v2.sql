-- 20251206_flowmeta_devfactory_external_v2.sql
-- stack=sql
-- goal=Жёстко задать meta для домена devfactory с профилем external_profiles.devfactory.external.
-- summary=Формирует meta с devfactory_spec и external_profiles.devfactory.external и записывает его для code='devfactory'.

DO $$
DECLARE
    v_meta   jsonb;
    v_config jsonb;
BEGIN
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

    v_meta := jsonb_build_object(
        'devfactory_spec', jsonb_build_object(
            'description', 'DevFactory core domain (орган роста FoxProFlow, генерирует патчи и код).',
            'notes', jsonb_build_array(
                'DevFactory никогда не продаётся как платформа. Наружу отдаётся только результат (код/функции).',
                'Изменения выполняются по принципу NDC (Non-Destructive Change).'
            )
        ),
        'external_profiles', jsonb_build_object(
            'devfactory.external', v_config
        )
    );

    UPDATE flowmeta.domain
    SET meta = v_meta
    WHERE code = 'devfactory';

    IF NOT FOUND THEN
        INSERT INTO flowmeta.domain (code, meta)
        VALUES ('devfactory', v_meta);
    END IF;

    RAISE NOTICE 'flowmeta.domain[devfactory].meta updated with external_profiles.devfactory.external';
END;
$$ LANGUAGE plpgsql;
