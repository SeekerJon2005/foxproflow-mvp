# FoxProFlow CANON — T10 • Ops Chronicle / Status / Productivity

## T10 (Canon) • Версия v1.2 • Дата: 2025-12-27

**Создал:** Архитектор Яцков Евгений Анатольевич  
**Доступ:** Архитектор Яцков Евгений Анатольевич  
**Статус:** Canon / Active  

---

## 0) Назначение тома (один абзац)

Этот том — “операционная память” FoxProFlow: фиксирует реальность (Current State), боевые факты (RAW), выжимки (DIGEST), решения (DecisionLog) и продуктивность/баланс. В отличие от T1–T9 (как должно быть), T10 описывает **как было и как есть** — с датами и доказательствами.

---

## 0.1 Changelog

- v1.1 (2025-12-27): зафиксирован DR-контур (backup/restore/restore-drill PASS), добавлены Ops-уроки ($args pitfall, pg-only drill).
- v1.2 (2025-12-27): включён weekly restore-drill через Task Scheduler, добавлены evidence paths и политика ретеншна/DoD для DR.

---

## 1) Политика Ops-учёта

### 1.1 RAW (сырые факты)
RAW — это неизменённые факты: вывод команд, логи, ошибки, команды запуска, конфиги/флаги, наблюдения.  
RAW **не “причесываем”**. Максимум — добавляем время и заголовок.

### 1.2 DIGEST (выжимка смысла)
DIGEST отвечает:
- цель,
- симптом,
- диагностика (на какие факты опирались),
- причина,
- исправление,
- проверки (checks),
- итог (OK/DEGRADED/ROLLBACK),
- next steps,
- ссылки на RAW/evidence.

### 1.3 DecisionLog (решения и причины)
Каждое решение обязано иметь rationale (почему), альтернативы, риски и критерий закрытия.

### 1.4 Ops-урок: терминальная гигиена
Запрещено вставлять в PowerShell разметку ` ```powershell ` / ` ``` ` и разделители вида `---` как команды.  
Это создаёт мусорные файлы, ошибки парсинга и загрязняет репозиторий.  
Команды — только “чистые”. Документы — через Notepad/файлы.

---

## 2) Current State (снапшоты реальности)

Правило: Current State обновляется как **снапшот с датой**. Старое не стираем.

### 2.1 Снапшот: инфраструктурная база (Windows локально)
**Дата фиксации:** 2025-12-14  
**База URL (канон):** `http://127.0.0.1:8080` (IPv4-safe; localhost может уводить в `::1`)  

---

### 2.2 Снапшот: Ops DR / Backup / Restore — PASS
**Дата фиксации:** 2025-12-27

**Факт:** DR-контур переведён в доказуемый режим: backup → restore → restore-drill с evidence.

**Команды/инструменты (A-run):**
- `C:\Users\Evgeniy\projects\foxproflow-wt\A-run\scripts\pwsh\ff-backup.ps1`
- `C:\Users\Evgeniy\projects\foxproflow-wt\A-run\scripts\pwsh\ff-restore.ps1`
- `C:\Users\Evgeniy\projects\foxproflow-wt\A-run\scripts\pwsh\ff-restore-drill.ps1`
- DRILL окружение: `C:\Users\Evgeniy\projects\foxproflow-wt\A-run\ops\drill\docker-compose.pg-drill.yml` (postgres-only compose)

**Evidence (пример факта):**
- `ops/_local/evidence/restore_drill_20251227_213325` — PASS (restore + db checks + down -v)  
- Backup, использованный drill’ом: `ops/_backups/20251227-211437` (по логу запуска)

**Ключевые Ops-уроки из реальности:**
- PowerShell pitfall: нельзя использовать `$args` как имя параметра функции (например, `Compose([string[]]$args)`), т.к. `$args` — автоматическая переменная. Это деградирует вызовы `docker compose up/ps` в “help/Usage” и создаёт ложную картину “контейнеров нет”. Использовать `ComposeArgs` + guard “args not empty”.
- Restore-drill обязан быть изолирован (pg-only compose), чтобы не зависеть от профилей/pgAdmin/прочих сервисов “боевого” стенда.

---

### 2.3 Снапшот: WeeklyRestoreDrill (Task Scheduler) — ENABLED + PASS
**Дата фиксации:** 2025-12-27

**Факт:** включён регулярный weekly restore-drill через Windows Task Scheduler.

**Task:**
- Имя: `FoxProFlow\WeeklyRestoreDrill`
- Schedule: WEEKLY, SUN 07:30
- Wrapper script: `C:\Users\Evgeniy\projects\foxproflow-wt\A-run\scripts\pwsh\ff-sched-weekly-restore-drill.ps1`

**Проверка исполнения:**
- `Get-ScheduledTaskInfo` показал: `LastTaskResult = 0` (успех), `NextRunTime = 28.12.2025 07:30:00`

**Scheduler log (локальный):**
- `ops/_local/evidence/_scheduler/weekly_restore_drill.log`

**Evidence (test run):**
- `ops/_local/evidence/restore_drill_20251227_222736` — PASS (restore + db checks + down -v)

---

## 3) Боевые факты / Chronicle (append-only)

### 2025-12-27 — DR restore-drill PASS (manual run)
- **Команда:** `pwsh -NoProfile -File scripts/pwsh/ff-restore-drill.ps1`
- **Результат:** PASS (restore + checks + down -v)
- **Evidence:** `ops/_local/evidence/restore_drill_20251227_213325`
- **Примечание:** подтверждено в терминале строками `RESTORE OK` и `RESTORE-DRILL OK`.

### 2025-12-27 — WeeklyRestoreDrill PASS (Task Scheduler test run)
- **Task:** `FoxProFlow\WeeklyRestoreDrill`
- **Результат:** PASS (`LastTaskResult=0`)
- **Scheduler log:** `ops/_local/evidence/_scheduler/weekly_restore_drill.log`
- **Evidence:** `ops/_local/evidence/restore_drill_20251227_222736`

---

## 4) Ops Roadmap (операционные next steps)

### 4.1 P0 DONE (закрыто фактами)
- [x] DR-пакет A-run: backup/restore/restore-drill + pg-only drill compose + T10 каноны + .gitignore.
- [x] Стабилизация cold-start worker smoke (увеличены retries/timeouts, добавлена готовность/ожидание).
- [x] Weekly restore-drill в Task Scheduler + успешный test run.

### 4.2 P0 NEXT (следующие шаги)
1) Закоммитить wrapper-скрипт планировщика (если ещё не зафиксирован в git):  
   `scripts/pwsh/ff-sched-weekly-restore-drill.ps1`
2) Политика ретеншна:
   - держать N последних backup’ов (например 14–30),
   - держать N последних restore_drill evidence (например 30),
   - контролировать объём `ops/_backups` и `ops/_local/evidence`.
3) Опционально: добавить “DR drill PASS within last 7 days” как soft-gate в release-m0.

### 4.3 P1
- Укрепить smoke-порядок релиза (waiting “running && not restarting” и т.п.).
- Канонизировать Release Gate (build→migrate→deploy→smoke→rollback) как исполнимый runbook + evidence.

---

## 5) Decision Index (ключевые решения Ops)

Формат: `DEC.YYYY-MM-DD.NNN (CAT) — название`

### DEC.2025-12-27.001 (OPS) — Restore-drill обязателен и изолирован (pg-only)
**Суть:** restore-drill регулярно подтверждает, что backup реально восстанавливается. DRILL поднимает **только Postgres** в отдельном compose-проекте.  
**Почему:** иначе backup превращается в “непроверяемую страховку”.  
**Статус:** active.

### DEC.2025-12-27.002 (OPS) — Запрещено использовать `$args` как имя параметра (Compose pitfall)
**Суть:** `$args` — автоматическая переменная PowerShell; использование как имени параметра ломает передачу аргументов и вызывает `docker compose` help вместо команд.  
**Правило:** использовать `ComposeArgs` и guard на пустой список.  
**Статус:** active.

### DEC.2025-12-27.003 (SEC/OPS) — DR-артефакты не должны утекать в git
**Суть:** `ops/_backups/**` и `ops/_local/evidence/**` должны быть локальными (в .gitignore).  
**Почему:** там могут быть дампы/PII/секреты и просто тяжёлые файлы.  
**Статус:** active.

### DEC.2025-12-27.004 (OPS) — Weekly restore-drill через Task Scheduler (обязательная регулярность)
**Суть:** DR проверяется автоматически по расписанию (`FoxProFlow\WeeklyRestoreDrill`), результат фиксируется в `_scheduler` логе и в evidence папке restore_drill.  
**Почему:** DR без регулярной проверки деградирует в “непроверенный ритуал”.  
**Статус:** active.

---

## 6) Приложения

### 6.1 Мини-шаблон DIGEST
- Дата:
- Цель:
- Симптом:
- Диагностика (факты):
- Причина:
- Исправление:
- Checks:
- Итог:
- Next steps:
- Evidence paths:

### 6.2 Команды-референсы (операторские)
- Manual restore-drill:
  - `pwsh -NoProfile -File scripts/pwsh/ff-restore-drill.ps1`
- Task status:
  - `Get-ScheduledTaskInfo -TaskPath "\FoxProFlow\" -TaskName "WeeklyRestoreDrill" | Select LastRunTime,LastTaskResult,NextRunTime`
- Scheduler log:
  - `Get-Content ops/_local/evidence/_scheduler/weekly_restore_drill.log -Tail 120`

---
