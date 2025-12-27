\# DIGEST — CP1 DB baseline (2025-12-23)



Worktree: C:\\Users\\Evgeniy\\projects\\foxproflow-wt\\C-sql (branch wt/sql)  

Автор: Архитектор Яцков Евгений Анатольевич (оператор), C-sql lane (DB owner)



\## Суть

DB bootstrap + совместимость для CP1 подтверждены: verify-suite проходит, fixpacks применяются идемпотентно (safe re-run).



\## Применено (apply)

\- scripts/sql/fixpacks/20251222\_db\_bootstrap\_min\_apply.sql

\- scripts/sql/fixpacks/20251222\_hotfix\_eventlog\_corrid\_trucks\_crm\_apply.sql

\- scripts/sql/fixpacks/20251222\_hotfix\_routing\_trip\_segments\_compat\_apply.sql



\## Проверено (verify)

\- scripts/sql/verify/20251222\_db\_bootstrap\_min\_smoke.sql

\- scripts/sql/verify/20251222\_db\_bootstrap\_min\_postcheck.sql

\- scripts/sql/verify/20251222\_hotfix\_eventlog\_corrid\_trucks\_crm\_smoke.sql

\- scripts/sql/verify/20251222\_hotfix\_routing\_trip\_segments\_compat\_smoke.sql

\- scripts/sql/verify/20251223\_cp1\_db\_core\_suite.sql (one-shot suite)



\## Ключевые инварианты CP1 (DB)

\- sec.\* (roles/policies/bindings) присутствуют и читаются

\- dev.dev\_task присутствует (для DevFactory)

\- ops.event\_log имеет correlation\_id (совместимость ops)

\- planner.kpi\_snapshots + planner.planner\_kpi\_daily присутствуют (KPI контур)

\- public.trips / public.trip\_segments имеют compat-колонки (routing/segments)

\- public.trucks присутствует (compat)

\- crm.leads\_trial\_candidates\_v присутствует (CRM compat)



\## Как проверить (для A-run/B-dev)

Запуск one-shot verify:

\- scripts/sql/verify/20251223\_cp1\_db\_core\_suite.sql



Ожидаемо: строка `OK: CP1 DB core suite passed`.



