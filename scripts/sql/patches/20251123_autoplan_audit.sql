-- 2025-11-23: стабилизация индексов для public.autoplan_audit
-- Таблица создаётся основными миграциями/патчами ядра.
-- Данный патч недеструктивный: он только гарантирует наличие нужных индексов.

-- Быстрый отбор по времени событий автоплана
CREATE INDEX IF NOT EXISTS autoplan_audit_ts_idx
    ON public.autoplan_audit (ts DESC);

-- Быстрый отбор по плану + времени (для аналитики по конкретным FlowLang-планам)
CREATE INDEX IF NOT EXISTS autoplan_audit_plan_ts_idx
    ON public.autoplan_audit (plan_name, ts DESC);
