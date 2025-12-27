-- 20251206_flowsec_devfactory_external_v1.sql
-- stack=sql
-- goal=Добавить FlowSec-политики для профиля devfactory.external, если уже развернут модуль sec.policies.
-- summary=Если sec.policies нет, патч печатает NOTICE и ничего не делает (ожидает базовый security-патч).

DO $$
DECLARE
    v_now          timestamptz := now();
    v_has_policies boolean;
BEGIN
    -- Проверяем, есть ли таблица sec.policies
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'sec'
          AND table_name   = 'policies'
    )
    INTO v_has_policies;

    IF NOT v_has_policies THEN
        RAISE NOTICE 'sec.policies not found, skipping devfactory.external FlowSec policies. Apply base security schema first.';
        RETURN;
    END IF;

    /*
      Предполагаем, что таблица sec.policies имеет столбцы:
        - code text PRIMARY KEY
        - title text
        - description text
        - is_enabled boolean
        - meta jsonb
    */

    -- 1. Только NDC-миграции для внешних проектов DevFactory
    INSERT INTO sec.policies (code, title, description, is_enabled, meta)
    VALUES (
        'devfactory_ndc_only',
        'DevFactory external — только NDC-миграции',
        'Запрещает опасные DDL-операции во внешних проектах DevFactory (DROP, опасный ALTER). Разрешает только NDC-миграции (add-only / безопасные изменения).',
        true,
        jsonb_build_object(
            'domain', 'devfactory',
            'profile', 'devfactory.external',
            'category', 'sql',
            'forbidden_operations', jsonb_build_array(
                'DROP TABLE',
                'DROP SCHEMA',
                'ALTER TABLE DROP COLUMN',
                'ALTER TABLE ALTER COLUMN TYPE'
            ),
            'require_ndc_migrations', true,
            'enforced', true,
            'created_at', v_now
        )
    )
    ON CONFLICT (code) DO UPDATE
        SET title       = EXCLUDED.title,
            description = EXCLUDED.description,
            is_enabled  = true,
            meta        = sec.policies.meta || EXCLUDED.meta;

    -- 2. Прямой запрет DROP/опасного ALTER
    INSERT INTO sec.policies (code, title, description, is_enabled, meta)
    VALUES (
        'devfactory_external_no_drop',
        'DevFactory external — запрет DROP/опасного ALTER',
        'Прямо запрещает SQL-операции DROP/опасный ALTER во внешних проектах DevFactory, даже если они попытались пройти через NDC.',
        true,
        jsonb_build_object(
            'domain', 'devfactory',
            'profile', 'devfactory.external',
            'category', 'sql',
            'forbidden_operations', jsonb_build_array(
                'DROP TABLE',
                'DROP SCHEMA',
                'ALTER TABLE DROP COLUMN',
                'ALTER TABLE ALTER COLUMN TYPE'
            ),
            'enforced', true,
            'created_at', v_now
        )
    )
    ON CONFLICT (code) DO UPDATE
        SET title       = EXCLUDED.title,
            description = EXCLUDED.description,
            is_enabled  = true,
            meta        = sec.policies.meta || EXCLUDED.meta;

    -- 3. Запрет shell/exec и сетевых вызовов
    INSERT INTO sec.policies (code, title, description, is_enabled, meta)
    VALUES (
        'devfactory_external_no_shell',
        'DevFactory external — запрет shell/exec',
        'Запрещает любые shell-вызовы и произвольное исполнение команд из DevFactory при работе с внешними проектами.',
        true,
        jsonb_build_object(
            'domain', 'devfactory',
            'profile', 'devfactory.external',
            'category', 'runtime',
            'allow_shell_exec', false,
            'allow_network_calls', false,
            'enforced', true,
            'created_at', v_now
        )
    )
    ON CONFLICT (code) DO UPDATE
        SET title       = EXCLUDED.title,
            description = EXCLUDED.description,
            is_enabled  = true,
            meta        = sec.policies.meta || EXCLUDED.meta;

    -- 4. Ограничение директорий (только белый список)
    INSERT INTO sec.policies (code, title, description, is_enabled, meta)
    VALUES (
        'devfactory_external_allowed_dirs_only',
        'DevFactory external — изменение только в разрешённых директориях',
        'Разрешает DevFactory изменять файлы только в белом списке директорий (src, scripts, docs, migrations, config и корень проекта).',
        true,
        jsonb_build_object(
            'domain', 'devfactory',
            'profile', 'devfactory.external',
            'category', 'filesystem',
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
            ),
            'enforced', true,
            'created_at', v_now
        )
    )
    ON CONFLICT (code) DO UPDATE
        SET title       = EXCLUDED.title,
            description = EXCLUDED.description,
            is_enabled  = true,
            meta        = sec.policies.meta || EXCLUDED.meta;

    -- 5. Запрет доступа к прод-секретам
    INSERT INTO sec.policies (code, title, description, is_enabled, meta)
    VALUES (
        'devfactory_external_no_prod_secrets',
        'DevFactory external — запрет доступа к прод-секретам',
        'Запрещает DevFactory читать/изменять файлы и значения, содержащие прод-секреты во внешних проектах.',
        true,
        jsonb_build_object(
            'domain', 'devfactory',
            'profile', 'devfactory.external',
            'category', 'secrets',
            'forbidden_paths', jsonb_build_array(
                '.foxproflow/secrets',
                'config/prod',
                'config/secrets',
                'secrets'
            ),
            'enforced', true,
            'created_at', v_now
        )
    )
    ON CONFLICT (code) DO UPDATE
        SET title       = EXCLUDED.title,
            description = EXCLUDED.description,
            is_enabled  = true,
            meta        = sec.policies.meta || EXCLUDED.meta;

END;
$$ LANGUAGE plpgsql;
