CREATE OR REPLACE VIEW public.trip_segments_active AS
SELECT *
FROM public.trip_segments
WHERE COALESCE(status,'active') <> 'archived';
