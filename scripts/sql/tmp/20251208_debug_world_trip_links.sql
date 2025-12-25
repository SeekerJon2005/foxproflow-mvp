SELECT
  id,
  entity_type,
  entity_id,
  space_id,
  object_id,
  relation,
  meta
FROM world.trip_links
ORDER BY id;
