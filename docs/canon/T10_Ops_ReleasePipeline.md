\# FoxProFlow CANON — T10 • Ops: Release Pipeline (build→migrate→deploy→rollback)



\## T10 (Draft→Canon) • Версия v0.1 • Дата: 2025-12-27



\*\*Создал:\*\* Архитектор Яцков Евгений Анатольевич  

\*\*Доступ:\*\* Архитектор Яцков Евгений Анатольевич  

\*\*Статус:\*\* Draft / Active



---



\## 0) Цель



Релиз должен быть:

\- \*\*воспроизводимым\*\* (любой оператор повторит),

\- \*\*доказуемым\*\* (evidence),

\- \*\*безопасным\*\* (FlowSec First),

\- \*\*обратимым\*\* (rollback).



---



\## 1) Жёсткие гейты (что считаем “релизом”)



Release PASS только если:

\- стенд поднимается,

\- миграции применены (или намеренно пропущены с фиксацией причины),

\- smoke PASS,

\- evidence сохранён.



Release FAIL если:

\- “вроде работает” без evidence,

\- smoke падает,

\- rollback невозможен или не проверен.



---



\## 2) Preflight (обязателен)



\- Session Charter: worktree/lane, “one-writer”, список DevTask, текущий ReleaseId.

\- `git status -sb`

\- `docker compose config --services`

\- базовый health (минимум /health).



Evidence минимум:

\- `ops/\_local/evidence/<rid>/step\_precheck.log`

\- git head



---



\## 3) Pipeline (минимальная воспроизводимость)



\### 3.1 BACKUP (обязателен по умолчанию)

\- `scripts/pwsh/ff-backup.ps1`

\- DoD: manifest.json + db.dump + sha256



\### 3.2 BUILD

\- `docker compose build api worker beat` (или целевой список сервисов)

\- Evidence: build log



\### 3.3 MIGRATE

\- любые миграции/фикспаки — строго с фиксацией “что применили”.

\- Если упираемся в БД-контракт или фикспаки — REQ в C.



\### 3.4 DEPLOY

\- `docker compose up -d ...`

\- Evidence: ps/logs минимум



\### 3.5 SMOKE

\- быстрый smoke: api ping + worker ping + критические ручки

\- Evidence: smoke logs + summary.json



---



\## 4) Rollback (если smoke FAIL)



По умолчанию rollback включён:

\- stop services → restore DB из backup → redeploy → re-smoke  

\- Если rollback отключён сознательно — это должно быть явно зафиксировано.



DoD rollback:

\- DB восстановлена (pg\_restore PASS)

\- повторный smoke PASS или факт “почему не PASS” зафиксирован в evidence.



---



\## 5) Evidence policy



Каждый релиз оставляет:

\- RAW: логи шагов (precheck/backup/build/migrate/deploy/smoke/rollback)

\- DIGEST: sha256 ключевых артефактов (дампы, summary)

\- summary.json: итог релиза (ok, время, версии, git head)



---



\## 6) Взаимодействие с ветками (только через REQ)



\- Ошибка API/worker-логики → REQ в B.

\- Ошибка verify/миграций/витрин → REQ в C.

\- Секреты/PII/редакция логов/дампов → REQ в FlowSec (D).



---



\## 7) Changelog

\- v0.1 (2025-12-27): первичная канонизация релиз-пайплайна для M0/M1.



