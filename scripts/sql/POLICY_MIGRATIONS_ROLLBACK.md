# SQL Policy — Migrations / Fixpacks / Verify / Rollback (Gate M0)

**Автор:** Архитектор Яцков Евгений Анатольевич  
**Статус:** Active / Enforced  
**Версия:** v1.1 (2025-12-24)  
**Принцип:** Любая правка БД = verify. Нет изменений “на глаз”.

---

## 0) Область действия и жёсткие границы (C-SQL lane)

Эта политика обязательна для любых изменений в:

- `scripts/sql/fixpacks/**`
- `scripts/sql/migrations/**`
- `scripts/sql/verify/**`

Запрещено в рамках C-SQL lane:

- править Python (`src/**`)
- править compose/env/runtime (`docker-compose*.yml`, `.env*`)

Каждый SQL-артефакт обязан быть:
1) **доказуемым** (verify),
2) **объяснимым** (header + changelog),
3) **безопасным** (NDC, rollback/compensation).

---

## 1) Термины

### Fixpack
Идемпотентный SQL (можно применять повторно). Используется для:
- bootstrap (создать недостающие объекты),
- NDC-расширений (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`),
- hotfix’ов без ломания контрактов.

**Правило:** fixpack не должен требовать “чистого состояния” и не должен ломаться при повторном применении.

### Migration
Версионное изменение схемы/данных, которое меняет “форму мира”.
Для каждой миграции обязателен **rollback** или **компенсация**.

**Правило:** миграции — это управляемые шаги, которые можно откатить или компенсировать документированно.

### Verify-suite
Набор проверок, который даёт **PASS/FAIL однозначно** и позволяет доказать состояние БД без знания истории проекта.

---

## 2) Layout и Naming

- Fixpacks: `scripts/sql/fixpacks/YYYYMMDD_<scope>_<topic>_apply.sql`
- Migrations:
  - `scripts/sql/migrations/YYYYMMDD_<topic>_apply.sql`
  - `scripts/sql/migrations/YYYYMMDD_<topic>_rollback.sql` *(если rollback применим)*
- Verify:
  - `scripts/sql/verify/verify_m0.sql` (Gate M0)
  - `scripts/sql/verify/verify_<scope>.sql` (по мере роста)
  - runner: `scripts/sql/verify/run_verify_m0.ps1`

---

## 3) Обязательная шапка для SQL файлов (контракт артефакта)

Каждый fixpack/migration должен начинаться с header-комментария:

```sql
-- Type: Fixpack | Migration(apply) | Migration(rollback) | Verify
-- Scope: dev|crm|ops|public|...
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Date: YYYY-MM-DD
-- DevTask/DevOrder: <ID если есть>
-- Purpose: <что меняем и зачем>
-- Preconditions: <что должно существовать до применения>
-- Safety: NDC notes / lock notes / data-loss notes
-- Rollback: <описание> или "Compensation: <описание>"
-- Verify: scripts/sql/verify/<...>.sql (что доказывает)
4) Fixpacks — правила
4.1 Идемпотентность (MUST)
Fixpack обязан быть повторно применимым. Допустимые паттерны:

CREATE SCHEMA IF NOT EXISTS ...

CREATE TABLE IF NOT EXISTS ...

ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...

индексы через проверки наличия (pg_indexes) или CREATE INDEX IF NOT EXISTS (если версия поддерживает)

4.2 Запрет “тихих ломаний” контрактов (MUST)
Запрещено в fixpack:

DROP TABLE, DROP COLUMN, ALTER COLUMN TYPE без NDC-плана

“переписывание” view контрактов через CREATE OR REPLACE VIEW, если view уже существует и контракт колонок может отличаться

Правильный паттерн для view:

CREATE VIEW только если отсутствует, либо NDC-версионирование (*_v2) + переключение потребителей.

4.3 Транзакции и CONCURRENTLY (MUST)
По умолчанию fixpack выполняется в BEGIN; ... COMMIT;

Но CREATE INDEX CONCURRENTLY нельзя выполнять внутри транзакции.

Для таких случаев: выделяй отдельный файл или явный блок “NON-TRANSACTIONAL” и документируй это в header.

4.4 Fail-fast на несовместимость (SHOULD)
Если есть риск несовместимого типа/контракта — лучше падать рано (например, если crm.tenants.id не uuid).

5) Migrations — правила
5.1 Apply + Rollback (предпочтительно)
Если изменение обратимо без потери данных:

должен быть *_rollback.sql,

откат должен быть безопасен,

откат должен проходить verify (или отдельный verify rollback).

5.2 Компенсация (если rollback неразумен)
Если откат опасен/дорог/может терять данные:

делаем компенсационную миграцию, которая возвращает контракт/поведение,

фиксируем documented path: “как вернуться на шаг назад”

какой apply применяли,

какой compensate применять,

какой verify запускать.

5.3 “Ирреверсибл” — только с явной маркировкой (MUST)
Любая миграция с потенциальной потерей данных должна:

иметь явную пометку в header DATA LOSS RISK: YES,

иметь компенсационный путь,

быть вынесена отдельным DevTask и отдельно согласована.

6) Обязательное правило NDC (двухшаговые изменения)
Запрещено ломать контракт одним ударом, если можно сделать NDC:

ADD новое (колонка/таблица/алиас/view)

Backfill / dual-write (если нужно)

Переключение кода (DEV lane)

Только потом (отдельной задачей) удалить старое

7) Verify — всегда (контур доказуемости)
7.1 PASS/FAIL однозначно (MUST)
Verify должен:

выполняться с ON_ERROR_STOP=1,

на FAIL — выбрасывать ошибку/исключение,

на PASS — печатать явный маркер (например OK: verify_m0 PASS).

7.2 Проверки не должны быть “пустыми” (MUST)
Минимум для Gate M0:

existence (схемы/таблицы/вьюхи/функции),

column-level contract для ключевых сущностей,

DML proof в транзакции с ROLLBACK (вставка/обновление/селект).

7.3 Verify не должен оставлять следов (MUST)
Все DML-проверки делаются внутри транзакции и завершаются ROLLBACK.

8) Контрактность и документация (DataDictionary)
Если меняется контракт (таблица/колонка/семантика/view):

обновить DataDictionary/Contract документ (канонический T2 файл или отдельный контракт-md в docs/canon/**),

сделать запись в scripts/sql/CHANGELOG.md.

9) Интеграция с релизом (RUN/DEV)
RUN и DEV должны иметь возможность доказать БД одной командой:

scripts/sql/verify/run_verify_m0.ps1 → PASS/FAIL

Рекомендуемый порядок в релизе:

backup

apply fixpacks/migrations

verify

smoke (API)

10) Что считается “готово” (Gate M0 / SQL)
Состояние БД проверяемо без знания истории проекта:

один запуск verify даёт доказательство контрактов (PASS/FAIL),

rollback/compensation путь описан и воспроизводим,

контрактные сущности DevFactory/CRM/Audit зафиксированы документально,

нет “тихих” сценариев проверки не той БД (project-aware runner / явные параметры).