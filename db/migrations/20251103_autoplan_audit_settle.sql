-- file: db/migrations/20251103_autoplan_audit_settle.sql

-- индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS ix_audit_pending
  ON public.autoplan_audit(decision, applied, ts);
CREATE INDEX IF NOT EXISTS ix_draft_truck_unpushed
  ON public.autoplan_draft_trips(truck_id, pushed, created_at DESC);

-- триггерная функция: «гасим» accept, если уже есть непушенный драфт,
-- и мягко «сквошим» дубликаты в ближнем окне (15 минут).
CREATE OR REPLACE FUNCTION public.fn_autoplan_audit_settle()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  v_draft uuid;
  v_dup   boolean;
BEGIN
  IF NEW.decision = 'accept' AND COALESCE(NEW.applied,false)=false THEN

     -- 1) если есть непушенный драфт по truck_id — сразу applied=true, привязываем draft_id
     SELECT id INTO v_draft
       FROM public.autoplan_draft_trips
      WHERE truck_id = NEW.truck_id
        AND pushed = false
      ORDER BY created_at DESC
      LIMIT 1;

     IF v_draft IS NOT NULL THEN
        NEW.applied       := TRUE;
        NEW.applied_at    := now();
        NEW.draft_id      := v_draft;
        NEW.applied_error := 'info: existing unpushed draft (trigger)';
        RETURN NEW;
     END IF;

     -- 2) если есть недавний pending-accept по этому truck_id — не плодим дубликаты
     SELECT EXISTS (
       SELECT 1
         FROM public.autoplan_audit a
        WHERE a.truck_id = NEW.truck_id
          AND a.decision = 'accept'
          AND COALESCE(a.applied,false)=false
          AND a.ts > now() - interval '15 minutes'
     ) INTO v_dup;

     IF v_dup THEN
        NEW.applied       := TRUE;
        NEW.applied_at    := now();
        NEW.applied_error := 'info: duplicate accept squashed (<=15m)';
        RETURN NEW;
     END IF;
  END IF;

  RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_autoplan_audit_settle ON public.autoplan_audit;

CREATE TRIGGER trg_autoplan_audit_settle
BEFORE INSERT ON public.autoplan_audit
FOR EACH ROW
EXECUTE FUNCTION public.fn_autoplan_audit_settle();
