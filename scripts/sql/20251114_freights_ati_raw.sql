CREATE TABLE IF NOT EXISTS public.freights_ati_raw (
    id           bigserial PRIMARY KEY,
    src          text        NOT NULL DEFAULT 'ati_html',
    external_id  text        NOT NULL,
    payload      jsonb       NOT NULL,
    parsed_at    timestamptz NOT NULL DEFAULT now(),
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS freights_ati_raw_src_extid_idx
  ON public.freights_ati_raw (src, external_id);
