-- 20251126_ops_driver_alerts_resolve.sql
-- Добавляет поля для управления жизненным циклом off-route алертов:
--   resolved_at      — когда алерт закрыт диспетчером;
--   resolved_by      — кем закрыт (логин/имя/идентификатор);
--   resolved_comment — комментарий/причина закрытия.
--
-- Патч недеструктивный и идемпотентный (IF NOT EXISTS).

ALTER TABLE ops.driver_alerts
  ADD COLUMN IF NOT EXISTS resolved_at timestamptz,
  ADD COLUMN IF NOT EXISTS resolved_by text,
  ADD COLUMN IF NOT EXISTS resolved_comment text;

COMMENT ON COLUMN ops.driver_alerts.resolved_at IS 'Когда алерт закрыт диспетчером';
COMMENT ON COLUMN ops.driver_alerts.resolved_by IS 'Кем закрыт (логин/имя)';
COMMENT ON COLUMN ops.driver_alerts.resolved_comment IS 'Комментарий диспетчера';
