# SQL Changelog — 2025-12-24 — devfactory_task_kpi_v2 UNIQUE index (enable CONCURRENTLY) — M0+

**Created by:** Архитектор Яцков Евгений Анатольевич  
**Scope:** C-sql  
**Goal:** сделать `mv_concurrent_ready=true` для `analytics.devfactory_task_kpi_v2` и включить `REFRESH MATERIALIZED VIEW CONCURRENTLY`.

## Added
- `scripts/sql/fixpacks/20251224_devfactory_task_kpi_v2_unique_index_apply.sql`
  - Creates unconditional UNIQUE index on `analytics.devfactory_task_kpi_v2(project_ref, stack)`
  - Rationale: матвью агрегирует `dev.dev_task` по `(project_ref, stack)` → ключ естественно уникален.

## How to verify
- `scripts/sql/verify/20251224_gate_m0_db_contract_verify.sql`
  - Expect: `mv_concurrent_ready=true`
  - Concurrent refresh test executes (no skipping).
