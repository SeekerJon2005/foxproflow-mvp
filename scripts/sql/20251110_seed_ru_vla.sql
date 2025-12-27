DO psql -U admin -d foxproflow
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.region_centroids WHERE UPPER(code)='RU-VLA') THEN
    INSERT INTO public.region_centroids (code, region, name, lat, lon)
    VALUES ('RU-VLA', 'VLADIMIR OBLAST', 'Владимирская область', 56.129000, 40.406000);
  END IF;
ENDpsql -U admin -d foxproflow;
