BEGIN;

-- Задаём дефолт для created_by, чтобы новые записи не падали
ALTER TABLE dev.dev_order_link
  ALTER COLUMN created_by SET DEFAULT 'system:devorders-api';

-- Чиним исторические NULL (если вдруг были)
UPDATE dev.dev_order_link
SET created_by = 'system:devorders-api'
WHERE created_by IS NULL;

COMMIT;
