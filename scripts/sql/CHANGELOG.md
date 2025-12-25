# scripts/sql — Changelog (append-only)

Правила:
- Append-only: новые записи добавлять сверху, существующие не переписывать.
- Каждая запись должна ссылаться на DevFactory task id: `[DEVTASK:<id>]`.
- Внутри записи перечислять изменённые артефакты (fixpacks/migrations/verify/docs).
- Проверяемость: после любых изменений должен проходить `scripts/sql/verify/run_verify_m0.ps1`.

---

## 2025-12-24

### [DEVTASK:29] Gate M0 / SQL — contracts + audit + verify (commit: b62b5aa)
- Fixpacks:
  - `scripts/sql/fixpacks/20251224_m0_devfactory_contract_apply.sql` — DevFactory contract (`dev.dev_order`, инварианты, `dev.v_dev_order_commercial_ctx` create-if-missing, индексы)
  - `scripts/sql/fixpacks/20251224_m0_crm_contract_apply.sql` — CRM contract (`crm.tenants`, `crm.leads`, `crm.leads_trial_candidates_v` NDC-safe)
  - `scripts/sql/fixpacks/20251224_m0_ops_audit_events_apply.sql` — Audit trail (`ops.audit_events`)
- Verify:
  - `scripts/sql/verify/verify_m0.sql` — PASS/FAIL, existence + column contract + DML proof в транзакции с ROLLBACK
  - `scripts/sql/verify/run_verify_m0.ps1` — project-aware runner (FF_COMPOSE_PROJECT / PreferProject, fail-on-mismatch по умолчанию)
- Docs/Policy:
  - `scripts/sql/POLICY_MIGRATIONS_ROLLBACK.md` — политика fixpacks/migrations/verify/rollback
  - `docs/canon/T2_EarthStack_FlowMeta_UniversalIntegration_Runbook_RUFirst_LinkMap.md` — секция DB Contract M0

### [DEVTASK:35] dev_order minimal bootstrap (fixpack+verify) (commit: a54561a)
- Fixpack:
  - `scripts/sql/fixpacks/20251224_dev_order_min_apply.sql`
- Verify:
  - `scripts/sql/verify/20251224_dev_order_min_smoke.sql`

---

## 2025-12-23

### [DEVTASK:31] trip_segments uuid contract + updated_at trigger (fixpacks+verify) (commit: 21aa5fa)
- Fixpacks:
  - `scripts/sql/fixpacks/20251223_trip_segments_id_uuid_align_apply.sql`
  - `scripts/sql/fixpacks/20251223_trip_segments_uuid_shadowcol_apply.sql`
  - `scripts/sql/fixpacks/20251224_trip_segments_updated_at_trigger_apply.sql`
- Verify:
  - `scripts/sql/verify/20251223_trip_segments_id_uuid_align_smoke.sql`
  - `scripts/sql/verify/20251223_trip_segments_uuid_shadowcol_smoke.sql`
  - `scripts/sql/verify/20251224_trip_segments_updated_at_trigger_smoke.sql`

### [DEVTASK:33] offroute driver_id (fixpacks+verify) (commit: c799f81)
- Fixpacks:
  - `scripts/sql/fixpacks/20251223_offroute_add_driver_id_apply.sql`
  - `scripts/sql/fixpacks/20251223_offroute_trucks_add_driver_id_apply.sql`
- Verify:
  - `scripts/sql/verify/20251223_offroute_add_driver_id_smoke.sql`
  - `scripts/sql/verify/20251223_offroute_trucks_add_driver_id_smoke.sql`

### [DEVTASK:34] trips.completed_at (fixpack+verify) (commit: b92698a)
- Fixpack:
  - `scripts/sql/fixpacks/20251223_trips_add_completed_at_apply.sql`
- Verify:
  - `scripts/sql/verify/20251223_trips_add_completed_at_smoke.sql`
