#requires -Version 7.0
<#
FoxProFlow • Ops • Worker critical tasks smoke
file: scripts/pwsh/ff-worker-critical-tasks-smoke.ps1

Gate intent:
Worker must register (inspect registered):
  - planner.kpi.snapshot
  - planner.kpi.daily_refresh
  - analytics.devfactory.daily

Exit codes:
  0 PASS
  2 FAIL (missing tasks / worker down)
  1 ERROR
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$ComposeFile = "",
  [string]$ProjectName = "",
  [string]$WorkerService = "worker",
  [string[]]$CriticalTasks = @(
    "planner.kpi.snapshot",
    "planner.kpi.daily_refresh",
    "analytics.devfactory.daily"
  ),
  [switch]$Json,
  [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Say([string]$m) { if (-not $Quiet) { Write-Host "[smoke] $m" } }
function Fail([string]$m) { Write-Host "[smoke][fail] $m" }

function Get-RepoRoot() {
  $root = (& git rev-parse --show-toplevel 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $root) { throw "git rev-parse --show-toplevel failed" }
  return $root.Trim()
}

function Resolve-ComposeFile([string]$repoRoot) {
  if ($ComposeFile -and (Test-Path -LiteralPath $ComposeFile)) { return (Resolve-Path -LiteralPath $ComposeFile).Path }
  if ($env:FF_COMPOSE_FILE -and (Test-Path -LiteralPath $env:FF_COMPOSE_FILE)) { return (Resolve-Path -LiteralPath $env:FF_COMPOSE_FILE).Path }
  $cand = Join-Path $repoRoot "docker-compose.yml"
  if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }
  throw "docker-compose.yml not found. Set -ComposeFile or env:FF_COMPOSE_FILE"
}

function Get-ProjectArgs() {
  $pn = $ProjectName
  if (-not $pn) { $pn = $env:FF_COMPOSE_PROJECT }
  if (-not $pn) { $pn = $env:COMPOSE_PROJECT_NAME }
  if ($pn) { return @("-p", $pn) }
  return @()
}

function DockerCompose([string[]]$args) {
  $docker = (Get-Command docker -ErrorAction Stop).Source
  $out = & $docker @args 2>&1
  $code = $LASTEXITCODE
  return [pscustomobject]@{ code=$code; out=($out | Out-String) }
}

function Get-WorkerId([string]$composeFile, [string[]]$projArgs) {
  $r = DockerCompose (@("compose","--ansi","never","-f",$composeFile) + $projArgs + @("ps","-q",$WorkerService))
  if ($r.code -ne 0) { throw "docker compose ps failed: $($r.out.Trim())" }
  return ($r.out.Trim())
}

function ExecInWorker([string]$composeFile, [string[]]$projArgs, [string]$cmd) {
  return (DockerCompose (@("compose","--ansi","never","-f",$composeFile) + $projArgs + @("exec","-T",$WorkerService,"sh","-lc",$cmd)))
}

function Get-RegisteredTasks([string]$composeFile, [string[]]$projArgs) {
  $py = @'
python - <<'PY'
import json, sys

candidates = [
  ("src.worker.celery_app", "app"),
  ("worker.celery_app", "app"),
  ("src.worker.celery_app", "celery_app"),
  ("worker.celery_app", "celery_app"),
]

for mod, attr in candidates:
    try:
        m = __import__(mod, fromlist=[attr])
        app = getattr(m, attr, None)
        if app is None:
            continue
        tasks = sorted([k for k in getattr(app, "tasks", {}).keys() if isinstance(k, str)])
        print(json.dumps({"ok": True, "module": mod, "attr": attr, "tasks": tasks}, ensure_ascii=False))
        sys.exit(0)
    except Exception:
        continue

print(json.dumps({"ok": False, "error": "cannot import celery app candidates"}, ensure_ascii=False))
sys.exit(2)
PY
'@

  $r = ExecInWorker $composeFile $projArgs $py
  if ($r.code -ne 0) { throw "worker exec failed: $($r.out.Trim())" }

  $obj = $null
  try { $obj = $r.out | ConvertFrom-Json } catch { throw "cannot parse JSON from worker: $($r.out.Trim())" }
  if (-not $obj.ok) { throw "cannot import celery app inside worker" }
  return @($obj.tasks)
}

try {
  $repoRoot = Get-RepoRoot
  $composeFile = Resolve-ComposeFile $repoRoot
  $projArgs = Get-ProjectArgs

  $wid = Get-WorkerId $composeFile $projArgs
  if (-not $wid) { Fail "Worker container not found (compose ps -q returned empty)."; exit 2 }

  Say "Compose: $composeFile"
  Say "Worker:  $WorkerService ($wid)"

  $tasks = Get-RegisteredTasks $composeFile $projArgs

  $missing = @()
  foreach ($t in $CriticalTasks) {
    if ($tasks -notcontains $t) { $missing += $t }
  }

  $payload = [pscustomobject]@{
    ok = ($missing.Count -eq 0)
    compose_file = $composeFile
    worker_service = $WorkerService
    critical_tasks = $CriticalTasks
    missing_tasks = $missing
    registered_count = $tasks.Count
  }

  if ($Json) {
    $payload | ConvertTo-Json -Depth 6
    exit $(if ($payload.ok) { 0 } else { 2 })
  }

  if ($missing.Count -eq 0) {
    Say ("PASS: all critical tasks registered ({0})" -f $CriticalTasks.Count)
    exit 0
  }

  Fail ("FAIL: missing tasks ({0}): {1}" -f $missing.Count, ($missing -join ", "))
  exit 2

} catch {
  Fail $_.Exception.Message
  exit 1
}
