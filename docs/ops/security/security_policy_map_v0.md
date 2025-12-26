# FoxProFlow • Security Lane • Policy Map v0
Дата: 2025-12-26
Создал: Архитектор Яцков Евгений Анатольевич

Evidence folder:
C:\Users\Evgeniy\projects\foxproflow-wt\A-run\ops\_local\evidence\sec_preflight_20251226_043007

## 1) Domain stats

| Count | Domain |
|---:|---|
| 18 | autoplan |
| 16 | devfactory |
| 12 | trips |
| 8 | devorders |
| 7 | driver |
| 7 | eri |
| 6 | crm |
| 5 | (root/other) |
| 4 | dispatcher |
| 4 | flowlang |
| 4 | flowworld |
| 3 | sales |
| 3 | routing |
| 3 | trucks |
| 3 | flowmind |
| 3 | onboarding |
| 2 | parsers |
| 2 | pipeline |
| 2 | autoplan_legacy |
| 2 | telemetry |
| 1 | flowmeta |

## 2) P0 endpoints (highest risk / first gates)

* /api/devfactory/tasks/{task_id}/autofix/run [POST] → action devfactory.autofix_admin policy devfactory.autofix_admin (score=145)
* /api/devfactory/tasks/{task_id}/autofix/disable [POST] → action devfactory.autofix_admin policy devfactory.autofix_admin (score=100)
* /api/devfactory/tasks/{task_id}/autofix/enable [POST] → action devfactory.autofix_admin policy devfactory.autofix_admin (score=100)
* /api/devfactory/tasks/{task_id}/autofix/kpi [GET] → action devfactory.read policy devfactory.read (score=90)

## 3) P1 endpoints

* /api/autoplan/trips/{trip_id}/confirm [POST] → action autoplan.apply (score=85)
* /api/autoplan_legacy/run [POST] → action autoplan_legacy.apply (score=80)
* /api/autoplan/run [POST] → action autoplan.apply (score=80)
* /api/trips/{trip_id}/confirm [POST] → action trips.apply (score=75)
* /api/devfactory/tasks/intent [POST] → action devfactory.write (score=70)
* /api/devorders/{dev_order_id}/link/billing [POST] → action devorders.link_write (score=70)
* /api/devorders/{dev_order_id}/link/lead [POST] → action devorders.link_write (score=70)
* /api/devorders/{dev_order_id}/link/tenant [POST] → action devorders.link_write (score=70)
* /api/trips/autoplan/run/{run_id} [GET] → action trips.apply (score=70)
* /api/driver/auth/confirm [POST] → action driver.apply (score=68)
* /api/devfactory/orders [POST] → action devfactory.write (score=65)
* /api/devfactory/orders/{dev_order_id} [GET] → action devfactory.write (score=65)
* /api/devfactory/orders/{dev_order_id}/tasks [GET] → action devfactory.write (score=65)
* /api/devfactory/orders/public/{dev_order_public_id} [GET] → action devfactory.write (score=65)
* /api/devfactory/orders/recent [GET] → action devfactory.read (score=60)

## 4) Action/Policy dictionary (unique)

* autoplan.read  (endpoints=16)
* trips.read  (endpoints=10)
* devfactory.read  (endpoints=8)
* eri.read  (endpoints=7)
* driver.read  (endpoints=6)
* crm.read  (endpoints=6)
* devfactory.write  (endpoints=5)
* _root_other_.read  (endpoints=5)
* devorders.read  (endpoints=4)
* dispatcher.read  (endpoints=4)
* flowworld.read  (endpoints=4)
* flowlang.read  (endpoints=4)
* flowmind.read  (endpoints=3)
* sales.read  (endpoints=3)
* routing.read  (endpoints=3)
* onboarding.read  (endpoints=3)
* devfactory.autofix_admin  (endpoints=3)
* trucks.read  (endpoints=3)
* devorders.link_write  (endpoints=3)
* parsers.read  (endpoints=2)
* pipeline.read  (endpoints=2)
* telemetry.read  (endpoints=2)
* trips.apply  (endpoints=2)
* autoplan.apply  (endpoints=2)
* autoplan_legacy.apply  (endpoints=1)
* autoplan_legacy.read  (endpoints=1)
* driver.apply  (endpoints=1)
* devorders.admin  (endpoints=1)
* flowmeta.read  (endpoints=1)

## 5) Notes
- v0 mapping is heuristic; methods-aware mapping is enabled if openapi.json is available in evidence.
- This document does NOT apply gates; it proposes action/policy names and priorities only.
