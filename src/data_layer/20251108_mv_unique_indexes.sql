-- 2025-11-08 — Unique Indexes for CONCURRENT REFRESH (safe & adaptive)
-- Цель: подготовить уникальные индексы на materialized views, чтобы
--       REFRESH MATERIALIZED VIEW CONCURRENTLY работал без ошибок.

----------------------------------------------------------------------
-- 0) Защита от долгих lock'ов (опционально, можно убрать)
----------------------------------------------------------------------
DO $$
BEGIN
  PERFORM set_config('lock_timeout',      '5s',  true);
  PERFORM set_config('statement_timeout', '0',   true); -- без ограничения на создание индексов
END $$;

----------------------------------------------------------------------
-- 1) freights_enriched_mv: предпочитаем уникальный ключ (id).
--    Если id нет — пробуем (source, source_uid) при отсутствии дублей.
----------------------------------------------------------------------
DO $$
DECLARE
  has_id         boolean;
  has_source     boolean;
  has_source_uid boolean;
  dup_pair       boolean;
BEGIN
  -- Если уже есть ЛЮБОЙ уникальный индекс на MV — ничего не делаем.
  IF EXISTS (
       SELECT 1
         FROM pg_indexes i
         JOIN pg_class c ON c.relname = i.tablename
        WHERE i.schemaname='public'
          AND i.tablename='freights_enriched_mv'
          AND EXISTS (
                SELECT 1
                  FROM pg_constraint cn
                 WHERE cn.conindid = (SELECT indrelid FROM pg_class WHERE relname = i.indexname LIMIT 1)
               )
     )
  THEN
    RAISE NOTICE 'freights_enriched_mv: unique index already present, skipping.';
    RETURN;
  END IF;

  SELECT EXISTS (
           SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='freights_enriched_mv'
              AND column_name='id'
         ) INTO has_id;

  IF has_id THEN
    -- Создадим уникальный индекс по id, если его нет.
    IF NOT EXISTS (
         SELECT 1 FROM pg_indexes
          WHERE schemaname='public' AND tablename='freights_enriched_mv'
            AND indexname='ux_fe_mv_id'
       )
    THEN
      EXECUTE 'CREATE UNIQUE INDEX ux_fe_mv_id ON public.freights_enriched_mv (id)';
      RAISE NOTICE 'freights_enriched_mv: created unique index ux_fe_mv_id on (id).';
    ELSE
      RAISE NOTICE 'freights_enriched_mv: ux_fe_mv_id already exists.';
    END IF;
    RETURN;
  END IF;

  -- Fallback: (source, source_uid) — только если оба столбца есть и дублей нет.
  SELECT EXISTS (
           SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='freights_enriched_mv'
              AND column_name='source'
         ) INTO has_source;

  SELECT EXISTS (
           SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='freights_enriched_mv'
              AND column_name='source_uid'
         ) INTO has_source_uid;

  IF has_source AND has_source_uid THEN
    -- Проверка дублей по паре (source, source_uid)
    SELECT EXISTS (
             SELECT 1
               FROM public.freights_enriched_mv
              GROUP BY source, source_uid
             HAVING COUNT(*) > 1
           ) INTO dup_pair;

    IF dup_pair THEN
      RAISE NOTICE 'freights_enriched_mv: duplicates found for (source, source_uid) — unique index on this pair is impossible.';
      RETURN;
    END IF;

    IF NOT EXISTS (
         SELECT 1 FROM pg_indexes
          WHERE schemaname='public' AND tablename='freights_enriched_mv'
            AND indexname='ux_fe_mv_pair'
       )
    THEN
      EXECUTE 'CREATE UNIQUE INDEX ux_fe_mv_pair ON public.freights_enriched_mv (source, source_uid)';
      RAISE NOTICE 'freights_enriched_mv: created unique index ux_fe_mv_pair on (source, source_uid).';
    ELSE
      RAISE NOTICE 'freights_enriched_mv: ux_fe_mv_pair already exists.';
    END IF;
  ELSE
    RAISE NOTICE 'freights_enriched_mv: no (id) and no (source, source_uid) — skip unique index.';
  END IF;
END $$;

----------------------------------------------------------------------
-- 2) vehicle_availability_mv:
--    1-й кандидат: (truck_id, available_from)
--    2-й fallback: (truck_id, available_from, available_region, next_region)
--    Если и это не уникально — сообщаем, что нужна дедупликация/правка MV.
----------------------------------------------------------------------
DO $$
DECLARE
  has_truck_id        boolean;
  has_available_from  boolean;
  has_available_region boolean;
  has_next_region     boolean;
  dup_pair            boolean;
  dup_quad            boolean;
BEGIN
  -- Если уже есть целевой индекс — выходим.
  IF EXISTS (
       SELECT 1 FROM pg_indexes
        WHERE schemaname='public'
          AND tablename='vehicle_availability_mv'
          AND indexname='ux_vehicle_availability_key'
     )
  THEN
    RAISE NOTICE 'vehicle_availability_mv: ux_vehicle_availability_key already exists.';
    RETURN;
  END IF;

  SELECT EXISTS (
           SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='vehicle_availability_mv'
              AND column_name='truck_id'
         ) INTO has_truck_id;

  SELECT EXISTS (
           SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='vehicle_availability_mv'
              AND column_name='available_from'
         ) INTO has_available_from;

  SELECT EXISTS (
           SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='vehicle_availability_mv'
              AND column_name='available_region'
         ) INTO has_available_region;

  SELECT EXISTS (
           SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='vehicle_availability_mv'
              AND column_name='next_region'
         ) INTO has_next_region;

  -- Кандидат 1: (truck_id, available_from)
  IF has_truck_id AND has_available_from THEN
    SELECT EXISTS(
             SELECT 1
               FROM public.vehicle_availability_mv
              GROUP BY truck_id, available_from
             HAVING COUNT(*) > 1
           ) INTO dup_pair;

    IF NOT dup_pair THEN
      EXECUTE 'CREATE UNIQUE INDEX ux_vehicle_availability_key
                 ON public.vehicle_availability_mv (truck_id, available_from)';
      RAISE NOTICE 'vehicle_availability_mv: created unique index on (truck_id, available_from).';
      RETURN;
    END IF;
  END IF;

  -- Fallback 2: (truck_id, available_from, available_region, next_region)
  IF has_truck_id AND has_available_from AND has_available_region AND has_next_region THEN
    SELECT EXISTS(
             SELECT 1
               FROM public.vehicle_availability_mv
              GROUP BY truck_id, available_from, available_region, next_region
             HAVING COUNT(*) > 1
           ) INTO dup_quad;

    IF NOT dup_quad THEN
      EXECUTE 'CREATE UNIQUE INDEX ux_vehicle_availability_key
                 ON public.vehicle_availability_mv (truck_id, available_from, available_region, next_region)';
      RAISE NOTICE 'vehicle_availability_mv: created unique index on (truck_id, available_from, available_region, next_region).';
      RETURN;
    END IF;
  END IF;

  -- Если дошли сюда — уникальный ключ подобрать не удалось
  RAISE NOTICE 'vehicle_availability_mv: cannot pick unique key (duplicates remain) — keep using plain REFRESH.';
END $$;

----------------------------------------------------------------------
-- 3) (Опционально) сразу дернуть CONCURRENTLY там, где уже есть уникальный индекс.
--    Если индекса нет — выводим NOTICE и пропускаем.
----------------------------------------------------------------------
DO $$
DECLARE
  has_ux_fe boolean;
  has_ux_va boolean;
BEGIN
  SELECT EXISTS(
           SELECT 1 FROM pg_indexes
            WHERE schemaname='public' AND tablename='freights_enriched_mv'
              AND indexname IN ('ux_fe_mv_id','ux_fe_mv_pair','ux_freights_enriched_key')
         ) INTO has_ux_fe;

  SELECT EXISTS(
           SELECT 1 FROM pg_indexes
            WHERE schemaname='public' AND tablename='vehicle_availability_mv'
              AND indexname IN ('ux_vehicle_availability_key')
         ) INTO has_ux_va;

  IF has_ux_fe THEN
    EXECUTE 'REFRESH MATERIALIZED VIEW CONCURRENTLY public.freights_enriched_mv';
    RAISE NOTICE 'freights_enriched_mv: CONCURRENTLY refreshed.';
  ELSE
    RAISE NOTICE 'freights_enriched_mv: skip CONCURRENTLY (no unique index).';
  END IF;

  IF has_ux_va THEN
    EXECUTE 'REFRESH MATERIALIZED VIEW CONCURRENTLY public.vehicle_availability_mv';
    RAISE NOTICE 'vehicle_availability_mv: CONCURRENTLY refreshed.';
  ELSE
    RAISE NOTICE 'vehicle_availability_mv: skip CONCURRENTLY (no unique index).';
  END IF;
END $$;
