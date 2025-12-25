\# SQL Changelog — 2025-12-24 — Gate M0 (SQL)



\*\*Created by:\*\* Архитектор Яцков Евгений Анатольевич  

\*\*DevTask:\*\* (set real DevTask id)



\## Added



\- `scripts/sql/fixpacks/20251224\_ops\_agent\_events\_apply.sql`

&nbsp; - Adds `ops.agent\_events` (minimal agent logging contract)

&nbsp; - Rollback: `scripts/sql/rollback/20251224\_ops\_agent\_events\_rollback.sql`



\- `scripts/sql/fixpacks/20251224\_devfactory\_task\_kpi\_v2\_refresh\_patch\_apply.sql`

&nbsp; - Makes first refresh of `analytics.devfactory\_task\_kpi\_v2` non-concurrent (safe on clean DB)

&nbsp; - Uses CONCURRENTLY only when populated + has valid unconditional UNIQUE index



\## Verify



\- `scripts/sql/verify/20251224\_gate\_m0\_db\_contract\_verify.sql`

&nbsp; - PASS marker: `OK: Gate M0 DB contract verify passed`



\## Notes



\- This closes the known DevFactory contract gap: missing `ops.agent\_events`.

\- This hardens the known first-refresh issue for `devfactory\_task\_kpi\_v2`.



