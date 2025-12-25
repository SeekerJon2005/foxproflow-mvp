CREATE INDEX IF NOT EXISTS idx_freights_ati_raw_hash
    ON raw.freights_ati_raw (hash);

CREATE INDEX IF NOT EXISTS idx_freights_ati_raw_route
    ON raw.freights_ati_raw (loading_city, unloading_city);

CREATE INDEX IF NOT EXISTS idx_freights_ati_raw_parsed_at
    ON raw.freights_ati_raw (parsed_at);
