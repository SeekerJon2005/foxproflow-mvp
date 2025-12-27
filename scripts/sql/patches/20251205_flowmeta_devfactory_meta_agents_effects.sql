/*
  Патч: 20251205_flowmeta_devfactory_meta_agents_effects.sql

  Назначение:
  - Обновить поле meta для домена 'devfactory' в flowmeta.domain.
  - Зафиксировать в meta перечень классов агентов и эффектов DevFactory.
  - Не ломать существующие ключи meta (слияние jsonb).

  Идемпотентность:
  - Если домен 'devfactory' не найден — выходим с NOTICE.
  - Если ключ 'devfactory_spec' уже присутствует — ничего не меняем.
*/

DO $$
DECLARE
    v_domain_id integer;
    v_meta      jsonb;
    v_has_key   boolean;
BEGIN
    -- Найти домен devfactory
    SELECT id, meta
    INTO v_domain_id, v_meta
    FROM flowmeta.domain
    WHERE code = 'devfactory';

    IF NOT FOUND THEN
        RAISE NOTICE '[devfactory meta] domain=devfactory not found, skipping patch';
        RETURN;
    END IF;

    -- Инициализируем meta, если null
    v_meta := COALESCE(v_meta, '{}'::jsonb);

    -- Проверяем, нет ли уже ключа devfactory_spec
    v_has_key := v_meta ? 'devfactory_spec';

    IF v_has_key THEN
        RAISE NOTICE '[devfactory meta] devfactory_spec already present, nothing to do';
        RETURN;
    END IF;

    -- Собираем блок devfactory_spec через jsonb_build_object/jsonb_build_array
    v_meta := v_meta || jsonb_build_object(
        'devfactory_spec',
        jsonb_build_object(
            'description', 'DevFactory domain: программная фабрика, агенты, эффекты и политики',
            'agent_classes', jsonb_build_array(
                jsonb_build_object(
                    'code', 'devfactory.analyser',
                    'description', 'Анализ кода, схем БД, данных и логов; формирование понимания задачи, рисков и зависимостей.',
                    'effects', jsonb_build_array('devfactory.propose_patch', 'devfactory.generate_migration_plan')
                ),
                jsonb_build_object(
                    'code', 'devfactory.coder',
                    'description', 'Генерация кодовых и SQL-изменений в безопасном формате (патчи, SQL-патчи NDC).',
                    'effects', jsonb_build_array('devfactory.propose_patch', 'devfactory.add_sql_patch')
                ),
                jsonb_build_object(
                    'code', 'devfactory.migrator',
                    'description', 'Подготовка и описание миграций данных и схем (планы, SQL, проверки, откаты).',
                    'effects', jsonb_build_array('devfactory.generate_migration_plan', 'devfactory.add_sql_patch')
                ),
                jsonb_build_object(
                    'code', 'devfactory.tester',
                    'description', 'Генерация и обновление тестов, проверочных скриптов и сценариев симуляции.',
                    'effects', jsonb_build_array('devfactory.generate_tests', 'devfactory.propose_patch')
                ),
                jsonb_build_object(
                    'code', 'devfactory.docwriter',
                    'description', 'Создание и обновление документации, спецификаций, планов и отчётов.',
                    'effects', jsonb_build_array('devfactory.update_docs')
                ),
                jsonb_build_object(
                    'code', 'devfactory.coordinator',
                    'description', 'Координация цепочек задач DevFactory, сбор результатов, ведение "дела" изменения.',
                    'effects', jsonb_build_array('devfactory.propose_patch', 'devfactory.update_docs', 'devfactory.generate_tests')
                )
            ),
            'effects', jsonb_build_array(
                jsonb_build_object(
                    'code', 'devfactory.propose_patch',
                    'description', 'Предложить патч к файлу в формате unified diff или текстового stub.',
                    'allowed_targets', jsonb_build_array('src/**', 'scripts/sql/patches/**', 'docs/**', 'devfactory/**'),
                    'notes', 'Патч не применяется автоматически; требуется явное применение через DevFactory-утилиты.'
                ),
                jsonb_build_object(
                    'code', 'devfactory.add_sql_patch',
                    'description', 'Создать новый SQL-патч в scripts/sql/patches/** в стиле NDC (идемпотентная миграция).',
                    'allowed_targets', jsonb_build_array('scripts/sql/patches/**'),
                    'constraints', jsonb_build_array('NDC-only', 'DROP/ALTER без безопасного паттерна запрещены')
                ),
                jsonb_build_object(
                    'code', 'devfactory.update_docs',
                    'description', 'Обновить документацию (Markdown/текст) через diff или полный текст.',
                    'allowed_targets', jsonb_build_array('docs/**', 'devfactory/**')
                ),
                jsonb_build_object(
                    'code', 'devfactory.generate_tests',
                    'description', 'Сгенерировать или обновить тесты для указанного модуля/функции/схемы.',
                    'allowed_targets', jsonb_build_array('src/**', 'tests/**')
                ),
                jsonb_build_object(
                    'code', 'devfactory.generate_migration_plan',
                    'description', 'Сформировать план миграции данных/схем (шаги, SQL, проверки, откаты).',
                    'allowed_targets', jsonb_build_array('scripts/sql/patches/**', 'docs/**'),
                    'notes', 'Применение миграции — отдельный контролируемый этап; сама миграция не выполняется автоматически.'
                )
            ),
            'boundaries', jsonb_build_object(
                'allowed_code_dirs', jsonb_build_array('src/**', 'scripts/sql/patches/**', 'docs/**', 'devfactory/**'),
                'allowed_schemas',   jsonb_build_array('dev', 'logistics', 'crm', 'observability', 'flowmeta', 'sec'),
                'forbidden_operations', jsonb_build_array(
                    'DROP TABLE',
                    'ALTER TABLE ... DROP COLUMN',
                    'UPDATE/DELETE без явного плана миграции'
                )
            )
        )
    );

    UPDATE flowmeta.domain
    SET meta       = v_meta,
        updated_at = NOW()
    WHERE id = v_domain_id;

    RAISE NOTICE '[devfactory meta] devfactory_spec added to flowmeta.domain.meta for domain=devfactory (id=%)', v_domain_id;
END $$;
