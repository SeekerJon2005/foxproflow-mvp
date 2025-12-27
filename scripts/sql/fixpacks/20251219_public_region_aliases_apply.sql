-- FoxProFlow • FixPack • Region aliases (alias -> canonical city_map key)
-- file: scripts/sql/fixpacks/20251219_public_region_aliases_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--   Стратегически оптимальный alias-слой для региональных ключей/строк:
--   - public.city_map остаётся каноническим словарём координат (без "мусора")
--   - public.region_aliases хранит соответствия alias_key -> canonical_key (оба нормализованы)
--   - нормализация: lower + trim + '_' => ' ' + collapse whitespace + ё=>е
--   - индексы дают быстрый lookup по alias_norm (expression) и по canonical_key
--   Используется в worker/tasks_driver_alerts.py и может быть расширен другими модулями.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1) Normalizer (stable key-space for aliases)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.ff_norm_region_key(raw text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  s text;
BEGIN
  IF raw IS NULL THEN
    RETURN NULL;
  END IF;

  s := lower(raw);
  s := replace(s, 'ё', 'е');

  -- normalize whitespace/newlines/tabs/non-breaking space
  s := regexp_replace(s, E'[\\u00A0\\r\\n\\t]+', ' ', 'g');

  -- treat underscores as spaces (common in norm_key / imported strings)
  s := regexp_replace(s, E'[_]+', ' ', 'g');

  -- collapse multiple spaces
  s := regexp_replace(s, E'\\s+', ' ', 'g');

  s := btrim(s);
  IF s = '' THEN
    RETURN NULL;
  END IF;

  RETURN s;
END;
$$;

COMMENT ON FUNCTION public.ff_norm_region_key(text) IS
'FoxProFlow: normalize region/city key (lower+trim+collapse ws, "_"->" ", ё->е). Used by region_aliases and other geo layers.';

-- ---------------------------------------------------------------------------
-- 2) Table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.region_aliases (
  alias_key       text PRIMARY KEY,
  canonical_key   text NOT NULL,
  note            text,
  source          text NOT NULL DEFAULT 'manual',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Compatibility: ensure columns exist even if table was created earlier with a different shape.
ALTER TABLE public.region_aliases ADD COLUMN IF NOT EXISTS alias_key text;
ALTER TABLE public.region_aliases ADD COLUMN IF NOT EXISTS canonical_key text;
ALTER TABLE public.region_aliases ADD COLUMN IF NOT EXISTS note text;
ALTER TABLE public.region_aliases ADD COLUMN IF NOT EXISTS source text;
ALTER TABLE public.region_aliases ADD COLUMN IF NOT EXISTS created_at timestamptz;
ALTER TABLE public.region_aliases ADD COLUMN IF NOT EXISTS updated_at timestamptz;

-- defaults (idempotent)
ALTER TABLE public.region_aliases ALTER COLUMN source SET DEFAULT 'manual';
ALTER TABLE public.region_aliases ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE public.region_aliases ALTER COLUMN updated_at SET DEFAULT now();

-- Ensure primary key exists (if table pre-existed without PK)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = 'region_aliases'
      AND c.contype = 'p'
  ) THEN
    ALTER TABLE public.region_aliases
      ADD CONSTRAINT region_aliases_pkey PRIMARY KEY (alias_key);
  END IF;
END $$;

-- Backfill defaults if NULLs exist (legacy rows)
UPDATE public.region_aliases
SET
  source     = COALESCE(source, 'manual'),
  created_at = COALESCE(created_at, now()),
  updated_at = COALESCE(updated_at, now())
WHERE source IS NULL OR created_at IS NULL OR updated_at IS NULL;

-- ---------------------------------------------------------------------------
-- 3) Normalize existing data carefully (avoid breaking PK on duplicates)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  dup_cnt int;
BEGIN
  -- Normalize canonical_key always (doesn't affect PK)
  UPDATE public.region_aliases
  SET canonical_key = COALESCE(public.ff_norm_region_key(canonical_key), canonical_key)
  WHERE canonical_key IS NOT NULL
    AND public.ff_norm_region_key(canonical_key) IS NOT NULL
    AND canonical_key <> public.ff_norm_region_key(canonical_key);

  -- Normalize alias_key only if it will NOT create PK collisions
  SELECT COUNT(*) INTO dup_cnt
  FROM (
    SELECT public.ff_norm_region_key(alias_key) AS k, COUNT(*) AS c
    FROM public.region_aliases
    WHERE alias_key IS NOT NULL AND public.ff_norm_region_key(alias_key) IS NOT NULL
    GROUP BY public.ff_norm_region_key(alias_key)
    HAVING COUNT(*) > 1
  ) d;

  IF dup_cnt = 0 THEN
    UPDATE public.region_aliases
    SET alias_key = public.ff_norm_region_key(alias_key)
    WHERE alias_key IS NOT NULL
      AND public.ff_norm_region_key(alias_key) IS NOT NULL
      AND alias_key <> public.ff_norm_region_key(alias_key);
  END IF;
END $$;

-- Enforce NOT NULL on canonical_key when possible
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.region_aliases WHERE canonical_key IS NULL) THEN
    BEGIN
      ALTER TABLE public.region_aliases ALTER COLUMN canonical_key SET NOT NULL;
    EXCEPTION WHEN others THEN
      NULL;
    END;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 4) Trigger: keep updated_at and normalized keys on INSERT/UPDATE
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.tr_region_aliases_biu_norm()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  -- normalize keys
  NEW.alias_key := COALESCE(public.ff_norm_region_key(NEW.alias_key), NEW.alias_key);
  NEW.canonical_key := COALESCE(public.ff_norm_region_key(NEW.canonical_key), NEW.canonical_key);

  -- timestamps
  IF TG_OP = 'INSERT' THEN
    NEW.created_at := COALESCE(NEW.created_at, now());
  END IF;
  NEW.updated_at := now();

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS tr_region_aliases_biu_norm ON public.region_aliases;
CREATE TRIGGER tr_region_aliases_biu_norm
BEFORE INSERT OR UPDATE ON public.region_aliases
FOR EACH ROW
EXECUTE FUNCTION public.tr_region_aliases_biu_norm();

-- ---------------------------------------------------------------------------
-- 5) Indexes
-- ---------------------------------------------------------------------------
-- Fast lookup by normalized alias (works even if caller sends messy casing/spaces/underscores)
CREATE UNIQUE INDEX IF NOT EXISTS region_aliases_alias_norm_uidx
  ON public.region_aliases (public.ff_norm_region_key(alias_key));

CREATE INDEX IF NOT EXISTS region_aliases_canonical_key_idx
  ON public.region_aliases (canonical_key);

CREATE INDEX IF NOT EXISTS region_aliases_canonical_norm_idx
  ON public.region_aliases (public.ff_norm_region_key(canonical_key));

CREATE INDEX IF NOT EXISTS region_aliases_updated_at_idx
  ON public.region_aliases (updated_at);

-- ---------------------------------------------------------------------------
-- 6) Optional helper: resolve raw key to canonical key (alias -> canonical, else normalized raw)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.ff_resolve_region_key(raw text)
RETURNS text
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(
    (SELECT ra.canonical_key
     FROM public.region_aliases ra
     WHERE public.ff_norm_region_key(ra.alias_key) = public.ff_norm_region_key(raw)
     LIMIT 1),
    public.ff_norm_region_key(raw)
  );
$$;

COMMENT ON FUNCTION public.ff_resolve_region_key(text) IS
'FoxProFlow: resolve raw region/city key to canonical (uses region_aliases; fallback to ff_norm_region_key(raw)).';

-- ---------------------------------------------------------------------------
-- 7) Comments
-- ---------------------------------------------------------------------------
COMMENT ON TABLE public.region_aliases IS
'FoxProFlow: alias→canonical mapping for region keys/strings. Keeps public.city_map canonical.';

COMMENT ON COLUMN public.region_aliases.alias_key IS
'Alias key (normalized by trigger via ff_norm_region_key). PRIMARY KEY.';

COMMENT ON COLUMN public.region_aliases.canonical_key IS
'Canonical key in city_map key-space (normalized by trigger via ff_norm_region_key).';

COMMENT ON COLUMN public.region_aliases.note IS
'Optional human note about mapping rationale.';

COMMENT ON COLUMN public.region_aliases.source IS
'Source tag: manual|agent|import|...';

COMMENT ON COLUMN public.region_aliases.created_at IS 'Created timestamp.';
COMMENT ON COLUMN public.region_aliases.updated_at IS 'Updated timestamp.';

COMMIT;
