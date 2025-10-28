# scripts/ops/foxproflow.ops.ps1
# FoxProFlow — PowerShell ops helpers (Docker-first, Celery-first)
# Подключение в сессии:
#   . "C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\scripts\ops\foxproflow.ops.ps1"

param(
  [string]$Worker   = 'foxproflow-worker',
  [string]$Beat     = 'foxproflow-beat',
  [string]$Postgres = 'foxproflow-postgres',
  [string]$DbUser   = 'admin',
  [string]$DbName   = 'foxproflow'
)

# =============================================================
# Celery tasks diagnostics
# =============================================================
function Get-FFKnownTasks {
  $py = @'
from src.worker.celery_app import celery as app
tasks = sorted([t for t in app.tasks.keys() if t.startswith(("mv.refresh","planner.","forecast","etl."))])
print("\n".join(f"    * {t}" for t in tasks))
'@
  $cmd = @"
python - <<'PY'
$py
PY
"@
  & docker exec -i $Worker sh -lc $cmd
}

# =============================================================
# Надежный запуск Celery-задачи через send_task (устойчиво к кавычкам)
# Реализация через "python -c" и безопасное экранирование
# =============================================================
function Invoke-FFTask {
  param(
    [Parameter(Mandatory=$true)][string]$Name,
    [hashtable]$Kwargs
  )

  $json = if ($Kwargs) { ($Kwargs | ConvertTo-Json -Compress) } else { '{}' }

  # Python-код как многострочная строка
  $py = @"
import json
from src.worker.celery_app import celery as app
print(app.send_task('$Name', kwargs=json.loads('$json')).id)
"@

  # Экранируем одинарные кавычки для передачи в sh -lc '...'
  $pyEsc = $py -replace "'", "'\''"
  $cmd = "python -c '$pyEsc'"

  & docker exec -i $Worker sh -lc $cmd
}

# =============================================================
# Цепочка: REFRESH vehicle_availability_mv -> hourly replan
# =============================================================
function Invoke-FFRollingCycle {
  [void](Invoke-FFTask -Name 'mv.refresh.vehicle_availability')
  Start-Sleep -Seconds 2
  [void](Invoke-FFTask -Name 'planner.hourly.replan.all')
  'Triggered: mv.refresh.vehicle_availability -> planner.hourly.replan.all'
}

# =============================================================
# Beat schedule listing (по умолчанию читаем из beat)
# =============================================================
function Get-FFBeatSchedule {
  param([ValidateSet('beat','worker')]$From='beat')
  $container = if ($From -eq 'beat') { $Beat } else { $Worker }

  $py = @'
from src.worker.celery_app import celery as app
import json
print(json.dumps(sorted(list(app.conf.beat_schedule.keys()))))
'@
  $cmd = @"
python - <<'PY'
$py
PY
"@
  $keysJson = & docker exec -i $container sh -lc $cmd 2>$null
  try { $keysJson | ConvertFrom-Json } catch { @() }
}

# =============================================================
# Показать путь celery_app и ключи расписания из контейнера
# =============================================================
function Show-FFCeleryInfo {
  param([ValidateSet('beat','worker')]$From='beat')
  $container = if ($From -eq 'beat') { $Beat } else { $Worker }

  $py = @'
import inspect, json
import src.worker.celery_app as m
print("celery_app path:", m.__file__)
print("beat keys:", json.dumps(sorted(list(m.celery.conf.beat_schedule.keys()))))
'@
  $cmd = @"
python - <<'PY'
$py
PY
"@
  & docker exec -i $container sh -lc $cmd
}

# =============================================================
# Database operations
# =============================================================
function Refresh-FFAvailabilityMV-DB {
  $args = @('exec','-i',$Postgres,'psql','-U',$DbUser,'-d',$DbName,'-c',
            'REFRESH MATERIALIZED VIEW CONCURRENTLY public.vehicle_availability_mv;')
  & docker @args
}

function Test-FFMVConcurrently {
  & docker exec -i $Postgres psql -U $DbUser -d $DbName -c `
"SELECT indexname,indexdef FROM pg_indexes
 WHERE schemaname='public' AND tablename='vehicle_availability_mv';"
}

# --- Снимок MV: один -c, без \pset (надежно для Windows PowerShell) ---
function Get-FFAvailabilitySnapshot {
  $sql = @"
SELECT truck_id, available_from, available_region, next_region
FROM public.vehicle_availability_mv
ORDER BY available_from NULLS LAST
LIMIT 20;
"@
  & docker exec -i $Postgres psql -U $DbUser -d $DbName `
    -v ON_ERROR_STOP=1 -X -q -P pager=off -c $sql
}

# =============================================================
# Logs
# =============================================================
function Watch-FFLogs {
  param([ValidateSet('worker','beat','api','postgres')]$Target='worker',[int]$Tail=200)
  $name = "foxproflow-$Target"
  & docker logs --tail $Tail -f $name
}

# =============================================================
# Restart containers
# =============================================================
function Restart-FF {
  param([ValidateSet('worker','beat','api','postgres','all')]$What='all')
  switch ($What) {
    'worker'   { & docker restart $Worker }
    'beat'     { & docker restart $Beat }
    'api'      { & docker restart foxproflow-api }
    'postgres' { & docker restart $Postgres }
    'all'      { & docker restart $Worker; & docker restart $Beat }
  }
}

# =============================================================
# Управление дефолтным регионом ТС (fallback на холодном старте)
# =============================================================
function Set-FFTruckDefaultRegion {
  param(
    [Parameter(Mandatory=$true)][string]$TruckId,
    [Parameter(Mandatory=$true)][string]$RegionCode
  )
  & docker exec -i $Postgres psql -U $DbUser -d $DbName -c @"
CREATE TABLE IF NOT EXISTS public.truck_region_defaults(
  truck_id uuid PRIMARY KEY,
  region   text NOT NULL
);
"@
  & docker exec -i $Postgres psql -U $DbUser -d $DbName -c `
"INSERT INTO public.truck_region_defaults(truck_id,region)
 VALUES ('$TruckId','$RegionCode')
 ON CONFLICT (truck_id) DO UPDATE SET region=EXCLUDED.region;"
}

# =============================================================
# Диагностическая сводка
# =============================================================
function Get-FFStatus {
  "== Tasks =="
  Get-FFKnownTasks
  "`n== Beat schedule (from beat) =="
  ($s = Get-FFBeatSchedule); if ($s.Count -eq 0) { "  (empty or unavailable)" } else { $s }
}
