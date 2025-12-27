CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.city_resolve_queue (
  key         text PRIMARY KEY,
  first_seen  timestamptz NOT NULL DEFAULT now(),
  last_seen   timestamptz NOT NULL DEFAULT now(),
  total_hits  int NOT NULL DEFAULT 1,
  sample_type text,
  sample_trip uuid
);

CREATE INDEX IF NOT EXISTS city_resolve_queue_last_seen_idx ON ops.city_resolve_queue (last_seen DESC);
