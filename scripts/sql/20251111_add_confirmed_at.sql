ALTER TABLE public.trips
  ADD COLUMN IF NOT EXISTS confirmed_at timestamptz;

-- backfill из меты, если уже есть confirm_ts
UPDATE public.trips
SET confirmed_at = COALESCE(confirmed_at, (meta->>'autoplan'::text)::jsonb->>'confirm_ts')::timestamptz
WHERE confirmed_at IS NULL
  AND (meta->'autoplan'->>'confirm_ts') IS NOT NULL;

CREATE INDEX IF NOT EXISTS trips_confirmed_at_idx ON public.trips (confirmed_at DESC);
