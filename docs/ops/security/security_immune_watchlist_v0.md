# FoxProFlow • Security Lane • Immune Watchlist v0 (advisory-first)
Дата: 2025-12-26
Создал: Архитектор Яцков Евгений Анатольевич

Source policy map:
C:\Users\Evgeniy\projects\foxproflow-wt\A-run\docs\ops\security\security_policy_map_v0.json

## 1) Hot domains/actions (P0/P1 coverage)

### Domains (P0/P1)
| Count | Domain |
|---:|---|
| 10 | devfactory |
| 3 | devorders |
| 2 | autoplan |
| 2 | trips |
| 1 | autoplan_legacy |
| 1 | driver |

### Actions (P0/P1)
| Count | Action |
|---:|---|
| 5 | devfactory.write |
| 3 | devfactory.autofix_admin |
| 3 | devorders.link_write |
| 2 | autoplan.apply |
| 2 | devfactory.read |
| 2 | trips.apply |
| 1 | autoplan_legacy.apply |
| 1 | driver.apply |

## 2) Watchlist

### IMM-001 (P0) — Policy deny spike on P0/P1 actions
Why: Рост deny по опасным действиям = дрейф ролей/ключей/политик или попытка обхода. Ранний индикатор инцидента.
Threshold: WARN: >=20 denies/10m (P0/P1); CRIT: >=100 denies/10m или рост x5
Evidence:
- api logs: 403 Forbidden на protected endpoints
- ops/event_log (если есть): policy_deny/action/subject/ts
- devfactory events: deny на autofix/admin
Scope actions:
- devfactory.write
- devfactory.autofix_admin
- devorders.link_write
- autoplan.apply
- devfactory.read
- trips.apply
- autoplan_legacy.apply
- driver.apply

### IMM-002 (P0) — Autofix enable/run attempts (denied or repeated)
Why: Autofix = опасная кнопка. Повторные попытки без разрешения — misconfig или злоупотребление.
Threshold: WARN: >=3 attempts/10m; CRIT: >=10 attempts/10m
Evidence:
- api: /api/devfactory/tasks/*/autofix/* (403/200)
- devfactory autofix events (если включены)
- audit trail: correlation_id + subject
Scope actions:
- devfactory.autofix_admin

### IMM-003 (P0) — 5xx spike on execution domains (autoplan/devfactory/devorders)
Why: Рост 5xx на контурах исполнения/коммерции = деградация и риск потери денег/доверия.
Threshold: WARN: 5xx_rate >=2%/10m; CRIT: >=5%/10m или 10+ подряд
Evidence:
- api logs: ERROR/Traceback frequency
- health/extended latency + ready flags
- celery task failures correlated
Scope actions:
- devfactory.write
- devfactory.autofix_admin
- devorders.link_write
- autoplan.apply
- devfactory.read

### IMM-004 (P1) — Queue backlog / unregistered Celery tasks
Why: Unregistered tasks и рост очередей = скрытый отказ контуров.
Threshold: WARN: LLEN queue >100; CRIT: >1000 или Received unregistered task
Evidence:
- worker logs: Received unregistered task
- redis-cli LLEN <queue>
- celery inspect ping/registered
Scope actions:
- ops.queue_read
- ops.health_read

### IMM-005 (P1) — Health degradation (ready=false, latency spikes)
Why: Перед инцидентом часто растёт latency Postgres/Redis и ready=false.
Threshold: WARN: pg latency >50ms; CRIT: >200ms или ready=false
Evidence:
- GET /health/extended snapshots
- docker compose ps + restarts
- postgres logs: connection/lock issues
Scope actions:
- ops.health_read

