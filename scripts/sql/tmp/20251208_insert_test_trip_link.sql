INSERT INTO world.trip_links (entity_type, entity_id, space_id, object_id, relation, meta)
SELECT
  'trip'::text,
  1::bigint,              -- тестовый trip_id, позже заменим на реальный
  s.id,
  o.id,
  'origin',
  jsonb_build_object(
    'note',   'Тестовая привязка рейса 1 к дому primorsk_house',
    'debug',  true
  )
FROM world.spaces s
JOIN world.objects o ON o.space_id = s.id AND o.code = 'primorsk_house'
WHERE s.code = 'primorsk_base'
LIMIT 1;
