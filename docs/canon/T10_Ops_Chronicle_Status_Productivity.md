# FoxProFlow CANON — T10 • Ops Chronicle / Status / Productivity

## T10 (Canon) • Версия v1.1 • Дата: 2025-12-27

**Создал:** Архитектор Яцков Евгений Анатольевич  
**Доступ:** Архитектор Яцков Евгений Анатольевич  
**Статус:** Canon / Active  

---

## 0) Назначение тома (один абзац)

Этот том — “операционная память” FoxProFlow: фиксирует реальность (Current State), боевые факты (RAW), выжимки (DIGEST), решения (DecisionLog) и продуктивность/баланс. В отличие от T1–T9 (как должно быть), T10 описывает **как было и как есть** — с датами и доказательствами.

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

## 3) Боевые факты / Chronicle (append-only)

### 2025-12-27 — DR restore-drill PASS
- **Команда:** `pwsh -NoProfile -File scripts/pwsh/ff-restore-drill.ps1`
- **Результат:** PASS (restore + checks + down -v)
- **Evidence:** `ops/_local/evidence/restore_drill_20251227_213325`
- **Примечание:** подтверждено в терминале строками `RESTORE OK` и `RESTORE-DRILL OK`.

---

## 4) Ops Roadmap (операционные next steps)

### 4.1 P0 (сразу после PASS)
1) Зафиксировать и закоммитить DR-пакет A-run (скрипты + pg-drill compose + T10 каноны + .gitignore).  
2) Добавить weekly restore-drill (Task Scheduler) + сохранять evidence (summary+digest).

### 4.2 P1
- Укрепить smoke-порядок релиза (waiting “running && not restarting” и т.п.).
- Канонизировать Release Gate (build→migrate→deploy→smoke→rollback) как исполнимый runbook.

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

---
