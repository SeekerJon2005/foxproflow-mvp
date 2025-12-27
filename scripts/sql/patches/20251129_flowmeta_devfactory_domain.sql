-- DevFactory domain & agent classes in FlowMeta
-- NDC: только add-only, без DROP/ALTER.

BEGIN;

INSERT INTO flowmeta.domain (code, title, description)
VALUES (
    'devfactory',
    'DevFactory',
    'Внутренний орган разработки FoxProFlow / FlowMind (роевая фабрика кода)'
)
ON CONFLICT (code) DO NOTHING;

INSERT INTO flowmeta.agent_class (code, domain, role, description, config)
VALUES 
  ('devfactory.analyser',    'devfactory', 'Analyser',    'Разбор задач DevFactory', '{}'::jsonb),
  ('devfactory.coder',       'devfactory', 'Coder',       'Генерация кода/патчей', '{}'::jsonb),
  ('devfactory.migrator',    'devfactory', 'Migrator',    'Генерация SQL-миграций (NDC)', '{}'::jsonb),
  ('devfactory.tester',      'devfactory', 'Tester',      'Запуск тестов/линтеров', '{}'::jsonb),
  ('devfactory.docwriter',   'devfactory', 'DocWriter',   'Обновление документации', '{}'::jsonb),
  ('devfactory.coordinator', 'devfactory', 'Coordinator', 'Оркестрация пайплайнов DevFactory', '{}'::jsonb)
ON CONFLICT (code) DO NOTHING;

COMMIT;
