BEGIN;

ALTER TABLE dev.dev_task
  ADD COLUMN IF NOT EXISTS autofix_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE dev.dev_task
  ADD COLUMN IF NOT EXISTS autofix_status text NOT NULL DEFAULT 'disabled';

COMMENT ON COLUMN dev.dev_task.autofix_enabled IS
  'Флаг: задача допускает автоматический фикс (DevFactory autofix / code swarm) перед ручным review';

COMMENT ON COLUMN dev.dev_task.autofix_status IS
  'Текущее состояние автоматического фикса: disabled | pending | running | ok | failed';

COMMIT;
