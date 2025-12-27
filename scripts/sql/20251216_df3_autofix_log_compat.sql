-- file: scripts/sql/20251216_df3_autofix_log_compat.sql
-- purpose: Make dev.dev_autofix_event_df3_log accept DF-3 API inserts that pass
--          (dev_task_id uuid, resource_kind, action, status, dev_order_id, flowmind_plan_id, resource_path, duration_ms, engine, notes, payload)
-- NDC-safe: only ADD COLUMN + trigger + indexes + small backfill.

BEGIN;

ALTER TABLE dev.dev_autofix_event_df3_log
  ADD COLUMN IF NOT EXISTS dev_task_id uuid,
  ADD COLUMN IF NOT EXISTS resource_kind text,
  ADD COLUMN IF NOT EXISTS action text,
  ADD COLUMN IF NOT EXISTS status text,
  ADD COLUMN IF NOT EXISTS dev_order_id uuid,
  ADD COLUMN IF NOT EXISTS flowmind_plan_id uuid,
  ADD COLUMN IF NOT EXISTS resource_path text,
  ADD COLUMN IF NOT EXISTS duration_ms integer,
  ADD COLUMN IF NOT EXISTS engine text,
  ADD COLUMN IF NOT EXISTS notes text,
  ADD COLUMN IF NOT EXISTS payload jsonb;

CREATE OR REPLACE FUNCTION dev.fn_autofix_df3_log_compat_bi()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  _task_id bigint;
  _task_pub uuid;
  _stack text;
  _st text;
BEGIN
  -- Fill dev_task_id from devtask_id (old-style inserts)
  IF NEW.devtask_id IS NOT NULL AND NEW.dev_task_id IS NULL THEN
    SELECT public_id, stack INTO _task_pub, _stack
      FROM dev.dev_task
     WHERE id = NEW.devtask_id
     LIMIT 1;

    IF _task_pub IS NOT NULL THEN
      NEW.dev_task_id := _task_pub;
    END IF;

    IF (NEW.stack IS NULL OR btrim(NEW.stack) = '') AND _stack IS NOT NULL THEN
      NEW.stack := _stack;
    END IF;
  END IF;

  -- Fill devtask_id + stack from dev_task_id (DF-3 API style inserts)
  IF NEW.devtask_id IS NULL AND NEW.dev_task_id IS NOT NULL THEN
    SELECT id, stack INTO _task_id, _stack
      FROM dev.dev_task
     WHERE public_id = NEW.dev_task_id
     LIMIT 1;

    IF _task_id IS NOT NULL THEN
      NEW.devtask_id := _task_id;
    END IF;

    IF NEW.stack IS NULL OR btrim(NEW.stack) = '' THEN
      NEW.stack := COALESCE(_stack, 'unknown');
    END IF;
  END IF;

  -- Ensure stack (NOT NULL)
  IF NEW.stack IS NULL OR btrim(NEW.stack) = '' THEN
    NEW.stack := 'unknown';
  END IF;

  -- Normalize status
  _st := lower(COALESCE(NULLIF(btrim(NEW.status), ''), NULLIF(btrim(NEW.decision), ''), 'ok'));
  IF NEW.status IS NULL OR btrim(NEW.status) = '' THEN
    NEW.status := _st;
  END IF;

  -- Ensure started_at (NOT NULL) and finished_at
  IF NEW.started_at IS NULL THEN
    NEW.started_at := now();
  END IF;
  IF NEW.finished_at IS NULL THEN
    NEW.finished_at := NEW.started_at;
  END IF;

  -- Map duration_ms -> latency_ms
  IF NEW.latency_ms IS NULL AND NEW.duration_ms IS NOT NULL THEN
    NEW.latency_ms := NEW.duration_ms;
  END IF;

  -- Derive ok/decision/final_stage if missing
  IF NEW.ok IS NULL THEN
    NEW.ok := (_st NOT IN ('error','failed','fail'));
  END IF;

  IF NEW.decision IS NULL OR btrim(NEW.decision) = '' THEN
    IF _st IN ('error','failed','fail') THEN
      NEW.decision := 'error';
    ELSIF _st = 'skipped' THEN
      NEW.decision := 'skipped';
    ELSE
      NEW.decision := 'applied';
    END IF;
  END IF;

  IF NEW.final_stage IS NULL OR btrim(NEW.final_stage) = '' THEN
    IF _st IN ('error','failed','fail') THEN
      NEW.final_stage := 'failed';
    ELSE
      NEW.final_stage := 'completed';
    END IF;
  END IF;

  -- Merge into legacy metadata jsonb
  NEW.metadata := COALESCE(NEW.metadata, '{}'::jsonb)
    || jsonb_strip_nulls(
         jsonb_build_object(
           'dev_task_id', NEW.dev_task_id,
           'resource_kind', NEW.resource_kind,
           'action', NEW.action,
           'status', NEW.status,
           'dev_order_id', NEW.dev_order_id,
           'flowmind_plan_id', NEW.flowmind_plan_id,
           'resource_path', NEW.resource_path,
           'duration_ms', NEW.duration_ms,
           'engine', NEW.engine,
           'notes', NEW.notes,
           'payload', NEW.payload
         )
       );

  -- Best-effort error text
  IF NEW.error IS NULL AND _st IN ('error','failed','fail') THEN
    NEW.error := NULLIF(NEW.notes, '');
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_autofix_df3_log_compat_bi ON dev.dev_autofix_event_df3_log;
CREATE TRIGGER trg_autofix_df3_log_compat_bi
BEFORE INSERT ON dev.dev_autofix_event_df3_log
FOR EACH ROW
EXECUTE FUNCTION dev.fn_autofix_df3_log_compat_bi();

-- Backfill small (safe): populate dev_task_id/status for old rows
UPDATE dev.dev_autofix_event_df3_log l
   SET dev_task_id = t.public_id
  FROM dev.dev_task t
 WHERE l.dev_task_id IS NULL
   AND l.devtask_id = t.id;

UPDATE dev.dev_autofix_event_df3_log
   SET status = CASE
                  WHEN ok IS FALSE OR lower(coalesce(decision,'')) = 'error' THEN 'error'
                  WHEN lower(coalesce(decision,'')) = 'skipped' THEN 'skipped'
                  ELSE 'ok'
                END
 WHERE status IS NULL OR btrim(status) = '';

CREATE INDEX IF NOT EXISTS dev_autofix_event_df3_log_dev_task_id_idx
  ON dev.dev_autofix_event_df3_log (dev_task_id);

CREATE INDEX IF NOT EXISTS dev_autofix_event_df3_log_status_idx
  ON dev.dev_autofix_event_df3_log (status);

COMMIT;
