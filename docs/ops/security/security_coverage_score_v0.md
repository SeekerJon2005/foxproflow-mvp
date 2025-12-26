# FoxProFlow • Security Lane • Coverage Score v0
Дата: 2025-12-26
Создал: Архитектор Яцков Евгений Анатольевич

Source: security_policy_map_v0.json
C:\Users\Evgeniy\projects\foxproflow-wt\A-run\docs\ops\security\security_policy_map_v0.json

## 1) Summary metrics

* Total endpoints: 115
* P0: 4 (unique actions: 2)
* P1: 15 (unique actions: 7)
* P2: 18 (unique actions: 4)
* P3: 78
* Risk share (P0+P1 / total): 16,52%
* Coverage score v0: 100

## 2) Hot domains (P0/P1)

| Count | Domain |
|---:|---|
| 10 | devfactory |
| 3 | devorders |
| 2 | autoplan |
| 2 | trips |
| 1 | autoplan_legacy |
| 1 | driver |

## 3) Top 25 risky endpoints

| Score | Prio | Domain | Action | Path |
|---:|---|---|---|---|
| 145 | P0 | devfactory | devfactory.autofix_admin | /api/devfactory/tasks/{task_id}/autofix/run |
| 100 | P0 | devfactory | devfactory.autofix_admin | /api/devfactory/tasks/{task_id}/autofix/disable |
| 100 | P0 | devfactory | devfactory.autofix_admin | /api/devfactory/tasks/{task_id}/autofix/enable |
| 90 | P0 | devfactory | devfactory.read | /api/devfactory/tasks/{task_id}/autofix/kpi |
| 85 | P1 | autoplan | autoplan.apply | /api/autoplan/trips/{trip_id}/confirm |
| 80 | P1 | autoplan_legacy | autoplan_legacy.apply | /api/autoplan_legacy/run |
| 80 | P1 | autoplan | autoplan.apply | /api/autoplan/run |
| 75 | P1 | trips | trips.apply | /api/trips/{trip_id}/confirm |
| 70 | P1 | devfactory | devfactory.write | /api/devfactory/tasks/intent |
| 70 | P1 | devorders | devorders.link_write | /api/devorders/{dev_order_id}/link/billing |
| 70 | P1 | devorders | devorders.link_write | /api/devorders/{dev_order_id}/link/lead |
| 70 | P1 | devorders | devorders.link_write | /api/devorders/{dev_order_id}/link/tenant |
| 70 | P1 | trips | trips.apply | /api/trips/autoplan/run/{run_id} |
| 68 | P1 | driver | driver.apply | /api/driver/auth/confirm |
| 65 | P1 | devfactory | devfactory.write | /api/devfactory/orders |
| 65 | P1 | devfactory | devfactory.write | /api/devfactory/orders/{dev_order_id} |
| 65 | P1 | devfactory | devfactory.write | /api/devfactory/orders/{dev_order_id}/tasks |
| 65 | P1 | devfactory | devfactory.write | /api/devfactory/orders/public/{dev_order_public_id} |
| 60 | P1 | devfactory | devfactory.read | /api/devfactory/orders/recent |
| 50 | P2 | devorders | devorders.admin | /api/devorders/{dev_order_id}/bootstrap-tasks |
| 40 | P2 | devfactory | devfactory.read | /api/devfactory/tasks |
| 40 | P2 | devfactory | devfactory.read | /api/devfactory/tasks/{task_id} |
| 40 | P2 | devfactory | devfactory.read | /api/devfactory/tasks/{task_id}/questions/regen |
| 35 | P2 | autoplan_legacy | autoplan_legacy.read | /api/autoplan_legacy/trips/{trip_id}/revert |
| 35 | P2 | autoplan | autoplan.read | /api/autoplan/config |

## 4) Notes
- v0 score assumes every endpoint in policy map is 'covered' (action+policy proposed).
- v1 will compute 'enforcement coverage' by sampling runtime denies/allows and checking require_policies wiring.
