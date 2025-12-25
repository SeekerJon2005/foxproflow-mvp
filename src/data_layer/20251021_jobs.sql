-- file: src/data_layer/20251021_jobs.sql
BEGIN;

CREATE TABLE IF NOT EXISTS public.jobs (
  job_id       bigserial PRIMARY KEY,
  job_name     text UNIQUE NOT NULL,
  enabled      boolean NOT NULL DEFAULT true,
  schedule_cron text,              -- опционально: cron-выражение
  payload      jsonb,              -- параметры
  last_run_at  timestamptz,
  next_run_at  timestamptz,
  updated_at   timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_jobs_enabled ON public.jobs(enabled);

COMMIT;
