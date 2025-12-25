-- 2025-11-24 — FoxProFlow
-- Тестовый микрорынок вокруг Москвы для автоплана msk_day.
-- NDC: только INSERT + ON CONFLICT DO NOTHING, без ALTER/DROP и лишних полей.

INSERT INTO public.freights (
    id,
    source,
    source_uid,
    loading_region,
    unloading_region,
    loading_date,
    created_at,
    parsed_at
)
VALUES
    -- Москва → Санкт-Петербург (3 заявки)
    (2000001, 'TEST', 'TEST-2000001', 'RU-MOW', 'RU-SPE', CURRENT_DATE,      now(), now()),
    (2000002, 'TEST', 'TEST-2000002', 'RU-MOW', 'RU-SPE', CURRENT_DATE + 1,  now(), now()),
    (2000003, 'TEST', 'TEST-2000003', 'RU-MOW', 'RU-SPE', CURRENT_DATE + 2,  now(), now()),

    -- Москва → Владивосток (2 заявки, дальняк)
    (2000004, 'TEST', 'TEST-2000004', 'RU-MOW', 'RU-VLA', CURRENT_DATE,      now(), now()),
    (2000005, 'TEST', 'TEST-2000005', 'RU-MOW', 'RU-VLA', CURRENT_DATE + 1,  now(), now()),

    -- Обратки: СПб → Москва, Владивосток → Москва
    (2000006, 'TEST', 'TEST-2000006', 'RU-SPE', 'RU-MOW', CURRENT_DATE + 1,  now(), now()),
    (2000007, 'TEST', 'TEST-2000007', 'RU-VLA', 'RU-MOW', CURRENT_DATE + 3,  now(), now())
ON CONFLICT (id) DO NOTHING;
