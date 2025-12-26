# FoxProFlow • Security Lane • Security Surface Map v0
Дата: 2025-12-26
Создал: Архитектор Яцков Евгений Анатольевич

Evidence folder:
C:\Users\Evgeniy\projects\foxproflow-wt\A-run\ops\_local\evidence\sec_preflight_20251226_043007

## 1) Top domains by OpenAPI path count

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

## 2) P0 candidates (heuristic)

* /api/autoplan_legacy/run
* /api/autoplan/run
* /api/autoplan/trips/{trip_id}/confirm
* /api/devfactory/orders
* /api/devfactory/orders/{dev_order_id}
* /api/devfactory/orders/{dev_order_id}/tasks
* /api/devfactory/orders/public/{dev_order_public_id}
* /api/devfactory/orders/recent
* /api/devfactory/tasks/{task_id}/autofix/disable
* /api/devfactory/tasks/{task_id}/autofix/enable
* /api/devfactory/tasks/{task_id}/autofix/kpi
* /api/devfactory/tasks/{task_id}/autofix/run
* /api/devfactory/tasks/intent
* /api/devorders/{dev_order_id}/link/billing
* /api/devorders/{dev_order_id}/link/lead
* /api/devorders/{dev_order_id}/link/tenant
* /api/driver/auth/confirm
* /api/driver/auth/confirm_code
* /api/trips/{trip_id}/confirm
* /api/trips/autoplan/run/{run_id}
* /api/trips/autoplan/runs

## 3) Domains (paths)

### (root/other) (5)
* /api/devorders
* /api/drivers
* /api/telemetry
* /api/trucks
* /health/extended2

### autoplan (18)
* /api/autoplan/config
* /api/autoplan/debug/celery
* /api/autoplan/diag/price_layer
* /api/autoplan/health
* /api/autoplan/pipeline/coords/unknown
* /api/autoplan/pipeline/kpi
* /api/autoplan/pipeline/no_km
* /api/autoplan/pipeline/recent
* /api/autoplan/pipeline/recent_with_thresholds
* /api/autoplan/pipeline/recent2
* /api/autoplan/pipeline/summary
* /api/autoplan/pipeline/summary2
* /api/autoplan/result/{task_id}
* /api/autoplan/result/batch
* /api/autoplan/run
* /api/autoplan/trips/{trip_id}/confirm
* /api/autoplan/vitrine/decision/{audit_id}
* /api/autoplan/vitrine/decisions

### autoplan_legacy (2)
* /api/autoplan_legacy/run
* /api/autoplan_legacy/trips/{trip_id}/revert

### crm (6)
* /api/crm/leads/{lead_id}/mark-ready-for-trial
* /api/crm/leads/{lead_id}/win-and-start-onboarding
* /api/crm/leads/trial-candidates
* /api/crm/smoke/db
* /api/crm/smoke/ping
* /api/crm/trials/overview

### devfactory (16)
* /api/devfactory/catalog
* /api/devfactory/catalog/{order_type}/estimate
* /api/devfactory/kpi/tasks
* /api/devfactory/orders
* /api/devfactory/orders/{dev_order_id}
* /api/devfactory/orders/{dev_order_id}/tasks
* /api/devfactory/orders/public/{dev_order_public_id}
* /api/devfactory/orders/recent
* /api/devfactory/tasks
* /api/devfactory/tasks/{task_id}
* /api/devfactory/tasks/{task_id}/autofix/disable
* /api/devfactory/tasks/{task_id}/autofix/enable
* /api/devfactory/tasks/{task_id}/autofix/kpi
* /api/devfactory/tasks/{task_id}/autofix/run
* /api/devfactory/tasks/{task_id}/questions/regen
* /api/devfactory/tasks/intent

### devorders (8)
* /api/devorders/{dev_order_id}
* /api/devorders/{dev_order_id}/bootstrap-tasks
* /api/devorders/{dev_order_id}/commercial-context
* /api/devorders/{dev_order_id}/link/billing
* /api/devorders/{dev_order_id}/link/lead
* /api/devorders/{dev_order_id}/link/tenant
* /api/devorders/{dev_order_id}/tasks
* /api/devorders/status

### dispatcher (4)
* /api/dispatcher/alerts/{alert_id}/resolve
* /api/dispatcher/alerts/by_trip/{trip_id}/resolve_all
* /api/dispatcher/alerts/recent
* /api/dispatcher/trips/monitor

### driver (7)
* /api/driver/auth/confirm
* /api/driver/auth/confirm_code
* /api/driver/auth/request_code
* /api/driver/telemetry/batch
* /api/driver/trips/{trip_id}/ack
* /api/driver/trips/{trip_id}/complete
* /api/driver/trips/assigned

### eri (7)
* /api/eri/attention_signal
* /api/eri/attention_signal/_schema
* /api/eri/attention_signal/recent
* /api/eri/context
* /api/eri/snapshot
* /api/eri/snapshot/recent
* /api/eri/talk

### flowlang (4)
* /api/flowlang/plans
* /api/flowlang/plans/{name}
* /api/flowlang/plans/{name}/settings
* /api/flowlang/plans/current

### flowmeta (1)
* /api/flowmeta/domains-with-entities

### flowmind (3)
* /api/flowmind/advice
* /api/flowmind/devfactory-suggestions
* /api/flowmind/plans

### flowworld (4)
* /api/flowworld/spaces
* /api/flowworld/spaces/{code}
* /api/flowworld/state
* /api/flowworld/trip-links

### onboarding (3)
* /api/onboarding/sessions/{session_id}
* /api/onboarding/sessions/{session_id}/steps/{step_code}/set-status
* /api/onboarding/sessions/overview

### parsers (2)
* /api/parsers/ingest/freights
* /api/parsers/ingest/trucks

### pipeline (2)
* /api/pipeline/recent
* /api/pipeline/summary

### routing (3)
* /api/routing/health
* /api/routing/route
* /api/routing/table

### sales (3)
* /api/sales/message
* /api/sales/proposal/{session_id}
* /api/sales/start

### telemetry (2)
* /api/telemetry/history
* /api/telemetry/latest

### trips (12)
* /api/trips/{trip_id}/confirm
* /api/trips/{trip_id}/facts
* /api/trips/{trip_id}/finish
* /api/trips/{trip_id}/start
* /api/trips/autoplan/latest
* /api/trips/autoplan/run/{run_id}
* /api/trips/autoplan/runs
* /api/trips/operator/overview
* /api/trips/plan
* /api/trips/recent
* /api/trips/recent_clean
* /api/trips/recent_clean_strict

### trucks (3)
* /api/trucks/{truck_id}/card
* /api/trucks/{truck_id}/driver/assign
* /api/trucks/attach_trailer

