-- scripts/sql/patches/20251207_flowmeta_eri_skeleton.sql
-- FlowMeta v0.2 — добавление ERI-доменов и минимального набора сущностей (skeleton).
-- ВАЖНО:
--  • Патч не опирается на колонки title/tier/importance/description,
--    так как в фактической схеме flowmeta.domain/flowmeta.entity они могут отсутствовать.
--  • Мы регистрируем только коды доменов и сущностей.
--    Семантику (названия, описания) добавим в отдельном патче, подстроившись под реальную схему.

BEGIN;

-- 1. Домены ERI / organism.cognition
-- Если домен уже существует, ON CONFLICT DO NOTHING оставит его как есть.
INSERT INTO flowmeta.domain (code)
VALUES
    -- MindOS / слой рассуждений организма
    ('organism.cognition'),

    -- Ядро ERI (сессии, режимы, профили политик)
    ('eri.core'),

    -- Образовательный слой ERI (может уже существовать)
    ('eri.edu'),

    -- Немедицинский слой подсказок ERI.Health
    ('eri.health'),

    -- Социальная навигация и паттерны
    ('eri.society'),

    -- Этическое ядро ERI
    ('eri.ethics'),

    -- Конфигурация режимов, политик и профилей поведения
    ('eri.config')
ON CONFLICT (code) DO NOTHING;


-- 2. Сущности ERI — минимальный skeleton для DevFactory и ERI
-- Здесь сознательно не пишем title/description, только (domain_code, entity_code).
-- Остальные поля/метаданные будут заданы последующими патчами.

-- eri.core
INSERT INTO flowmeta.entity (domain_code, entity_code)
VALUES
    ('eri.core', 'session'),        -- Сеанс ERI
    ('eri.core', 'mode'),           -- Режим ERI
    ('eri.core', 'policy_profile')  -- Профиль политик ERI
ON CONFLICT DO NOTHING;

-- eri.edu
INSERT INTO flowmeta.entity (domain_code, entity_code)
VALUES
    ('eri.edu', 'course'),          -- Образовательный курс
    ('eri.edu', 'lesson'),          -- Урок
    ('eri.edu', 'learning_track')   -- Траектория обучения
ON CONFLICT DO NOTHING;

-- eri.health
INSERT INTO flowmeta.entity (domain_code, entity_code)
VALUES
    ('eri.health', 'health_signal'),   -- Сигнал состояния
    ('eri.health', 'recommendation')   -- Рекомендация ERI.Health
ON CONFLICT DO NOTHING;

-- eri.society
INSERT INTO flowmeta.entity (domain_code, entity_code)
VALUES
    ('eri.society', 'pattern'),        -- Социальный паттерн
    ('eri.society', 'interaction')     -- Тип взаимодействия
ON CONFLICT DO NOTHING;

-- eri.ethics
INSERT INTO flowmeta.entity (domain_code, entity_code)
VALUES
    ('eri.ethics', 'ethics_rule'),     -- Этическое правило
    ('eri.ethics', 'ethics_case')      -- Этический кейс
ON CONFLICT DO NOTHING;

-- eri.config
INSERT INTO flowmeta.entity (domain_code, entity_code)
VALUES
    ('eri.config', 'mode_preset'),     -- Пресет режима ERI
    ('eri.config', 'channel_profile')  -- Профиль канала ERI
ON CONFLICT DO NOTHING;

COMMIT;
