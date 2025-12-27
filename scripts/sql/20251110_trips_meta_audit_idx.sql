CREATE INDEX IF NOT EXISTS trips_meta_audit_id_idx
  ON public.trips ((meta->'autoplan'->>'audit_id'));
CREATE INDEX IF NOT EXISTS trips_created_at_idx
  ON public.trips (created_at DESC);
