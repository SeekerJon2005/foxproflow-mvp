#requires -Version 7.0
<#
FoxProFlow RUN • Worker Critical Tasks Smoke
file: scripts/pwsh/ff-worker-critical-tasks-smoke.ps1

Goal:
  Ensure Celery worker is responsive AND required tasks are registered.
  Evidence: ops/_local/evidence/<release_id>/...

Notes:
  - Uses "celery inspect ping" then "celery inspect registered".
  - Robust against docker compose warnings mixed into stdout/stderr.
  - Supports RequiredTasks (string[]) for direct invocation AND RequiredTasksCsv for pwsh -File.
  - Can optionally scan worker logs for "Received unregistered task".
  - Retries until success or timeout.

Lane: A-RUN only.
Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$ReleaseId = "",

  [string]$ComposeFile = "",
  [string]$ProjectName = $(if ($env:FF_COMPOSE_PROJECT) { $env:FF_COMPOSE_PROJECT } elseif ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "" }),

  [string]$WorkerService = "worker",
  [string]$CeleryApp = "src.worker.celery_app:app",

  # Preferred for direct invocation: .\script.ps1 -RequiredTasks @("a","b")
  [string[]]$RequiredTasks = @(
    "ops.beat.heartbeat"
    "ops.queue.watchdog"
    "ops.alerts.sla"
    "crm.smoke.ping"
    "crm.smoke.db_contract_v2"
    "routing.smoke.osrm_and_db"
    "devfactory.commercial.run_order"
    "agents.kpi.report"
  ),

  # Preferred for pwsh -File invocation: -RequiredTasksCsv "a;b;c"
  [string]$RequiredTasksCsv = "",

  # IMPORTANT: cold-start after down/up can be slow
  [int]$Retries = 40,
  [int]$SleepSec = 2,

  [int]$PingTimeoutSec = 20,
  [int]$InspectTimeoutSec = 30,

  [switch]$CheckUnregisteredInLogs,
  [int]$LogsSinceMin = 30,

  [int]$LogsTailLinesOnFail = 200,

  [string]$EvidenceDir = ""
)

# NOTE: DO NOT place any executable statements before [CmdletBinding]/param.
$VERSION = "2025-12-27.det.v5"

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Now-Stamp { (Get-Date).ToString("yyyyMMdd_HHmmss") }
function Now-Iso   { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function Repo-Root { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }

function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function Set-Utf8([string]$Path, [string]$Text) { $d=Split-Path $Path -Parent; if($d){Ensure-Dir $d}; ($Text ?? "") | Set-Content -LiteralPath $Path -Encoding utf8NoBOM }
function Add-Utf8([string]$Path, [string]$Text) { $d=Split-Path $Path -Parent; if($d){Ensure-Dir $d}; ($Text ?? "") | Add-Content -LiteralPath $Path -Encoding utf8NoBOM }

function Log([string]$msg) { Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg) }

function Resolve-ComposeFile([string]$repoRoot, [string]$composeFile) {
  if ([string]::IsNullOrWhiteSpace($composeFile)) { $composeFile = Join-Path $repoRoot "docker-compose.yml" }
  if (-not (Test-Path -LiteralPath $composeFile)) { throw "ComposeFile not found: $composeFile" }
  return (Resolve-Path -LiteralPath $composeFile).Path
}

function Dc([string]$composeFile, [string]$projectName, [string[]]$composeArgs) {
  $argv = @("compose","--ansi","never","-f",$composeFile)
  if ($projectName) { $argv += @("-p",$projectName) }
  $argv += $composeArgs

  $out = & docker @argv 2>&1
  $code = $LASTEXITCODE
  return [pscustomobject]@{
    code = $code
    out  = ($out | Out-String)
    argv = ("docker " + ($argv -join " "))
  }
}

function DcExec([string]$composeFile, [string]$projectName, [string]$service, [string[]]$cmd) {
  $argv = @("compose","--ansi","never","-f",$composeFile)
  if ($projectName) { $argv += @("-p",$projectName) }
  $argv += @("exec","-T",$service)
  $argv += $cmd

  $out = & docker @argv 2>&1
  $code = $LASTEXITCODE
  return [pscustomobject]@{
    code = $code
    out  = ($out | Out-String)
    argv = ("docker " + ($argv -join " "))
  }
}

function DcLogs([string]$composeFile, [string]$projectName, [string]$service, [string]$sinceArg, [int]$tail = 0) {
  $argv = @("compose","--ansi","never","-f",$composeFile)
  if ($projectName) { $argv += @("-p",$projectName) }
  $argv += @("logs")
  if ($sinceArg) { $argv += @("--since",$sinceArg) }
  if ($tail -gt 0) { $argv += @("--tail","$tail") }
  $argv += @($service)

  $out = & docker @argv 2>&1
  $code = $LASTEXITCODE
  return [pscustomobject]@{
    code = $code
    out  = ($out | Out-String)
    argv = ("docker " + ($argv -join " "))
  }
}

function Extract-ServiceNames([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return @() }
  $names = New-Object System.Collections.Generic.List[string]
  foreach ($line in ($text -split '\r?\n')) {
    $t = ($line ?? "").Trim()
    if (-not $t) { continue }
    if ($t -match '^[A-Za-z0-9][A-Za-z0-9_-]*$') { $names.Add($t) | Out-Null }
  }
  return @($names.ToArray() | Sort-Object -Unique)
}

function Contains-Pong([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return $false }
  return ($text -match '(?i)\bpong\b')
}

function Parse-WorkerNameFromPing([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return "" }
  $m = [regex]::Match($text, '(?m)^\s*->\s*([^\s:]+)\s*:\s*OK\s*$', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  if ($m.Success) { return $m.Groups[1].Value.Trim() }
  return ""
}

function Extract-RegisteredTasks([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return @() }
  $ms = [regex]::Matches($text, '(?m)^\s*\*\s+([^\s]+)\s*$', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  $names = foreach ($m in $ms) { $m.Groups[1].Value.Trim() }
  return @($names | Where-Object { $_ } | Sort-Object -Unique)
}

function Detect-UnregisteredHits([string]$logsText) {
  if ([string]::IsNullOrWhiteSpace($logsText)) { return @() }
  $hits = New-Object System.Collections.Generic.List[string]
  foreach ($line in ($logsText -split '\r?\n')) {
    if ($line -match 'Received unregistered task') { $hits.Add($line) | Out-Null }
  }
  return $hits.ToArray()
}

function Split-TasksCsv([string]$csv) {
  if ([string]::IsNullOrWhiteSpace($csv)) { return @() }

  # IMPORTANT:
  # Use regex \r and \n (NOT PowerShell backticks inside single quotes),
  # otherwise it splits on letters 'r'/'n' and breaks task names.
  $parts = @($csv -split '[,;\r\n]+' | ForEach-Object { ($_.ToString()).Trim() } | Where-Object { $_ })

  $seen = @{}
  $out = New-Object System.Collections.Generic.List[string]
  foreach ($p in $parts) {
    if (-not $seen.ContainsKey($p)) { $seen[$p] = $true; $out.Add($p) | Out-Null }
  }
  return $out.ToArray()
}

function Extract-FirstContainerId([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return "" }
  $m = [regex]::Match($text, '(?i)\b[0-9a-f]{12,64}\b')
  if ($m.Success) { return $m.Value.ToLowerInvariant() }
  return ""
}

function Get-ComposeServiceContainerId([string]$composeFile, [string]$projectName, [string]$service) {
  $r = Dc -composeFile $composeFile -projectName $projectName -composeArgs @("ps","-q",$service)
  $cid = Extract-FirstContainerId $r.out
  return [pscustomobject]@{
    code = $r.code
    out  = $r.out
    argv = $r.argv
    cid  = $cid
  }
}

function Get-ContainerState([string]$cid) {
  if ([string]::IsNullOrWhiteSpace($cid)) {
    return [pscustomobject]@{ ok=$false; error="empty cid" }
  }

  $fmt = "{{.State.Status}}|{{.State.Running}}|{{.State.Restarting}}|{{.State.ExitCode}}|{{.RestartCount}}"
  $out = & docker inspect -f $fmt $cid 2>&1
  $code = $LASTEXITCODE
  $s = ($out | Out-String).Trim()

  if ($code -ne 0) {
    return [pscustomobject]@{ ok=$false; error=$s; raw=$s; code=$code }
  }

  $parts = $s -split '\|'
  $status = ($parts[0] ?? "").Trim()
  $running = (($parts[1] ?? "").Trim().ToLowerInvariant() -eq "true")
  $restarting = (($parts[2] ?? "").Trim().ToLowerInvariant() -eq "true")
  $exitCode = 0
  $restartCount = 0
  try { $exitCode = [int](($parts[3] ?? "0").Trim()) } catch {}
  try { $restartCount = [int](($parts[4] ?? "0").Trim()) } catch {}

  return [pscustomobject]@{
    ok = $true
    status = $status
    running = $running
    restarting = $restarting
    exit_code = $exitCode
    restart_count = $restartCount
    raw = $s
    code = $code
  }
}

# -----------------------------
# Main
# -----------------------------
$repoRoot = Repo-Root
$ComposeFile = Resolve-ComposeFile -repoRoot $repoRoot -composeFile $ComposeFile

if ([string]::IsNullOrWhiteSpace($ProjectName)) {
  throw "ProjectName is empty. Provide -ProjectName or set FF_COMPOSE_PROJECT/COMPOSE_PROJECT_NAME."
}

if ([string]::IsNullOrWhiteSpace($ReleaseId)) {
  $ReleaseId = "worker_smoke_" + (Now-Stamp)
}

if ([string]::IsNullOrWhiteSpace($EvidenceDir)) {
  $EvidenceDir = Join-Path $repoRoot ("ops\_local\evidence\{0}" -f $ReleaseId)
}
Ensure-Dir $EvidenceDir
Write-Output ("evidence: " + $EvidenceDir)

# PRECHECK evidence
try {
  $psa = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("ps","-a")
  Set-Utf8 (Join-Path $EvidenceDir "docker_compose_ps_a.txt") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $psa.argv, $psa.out, $psa.code)

  $sv = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("config","--services")
  Set-Utf8 (Join-Path $EvidenceDir "docker_compose_services.txt") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $sv.argv, $sv.out, $sv.code)

  $services = Extract-ServiceNames $sv.out
  Set-Utf8 (Join-Path $EvidenceDir "compose_services_extracted.txt") ((@($services) -join "`n") + "`n")
} catch { }

# Build required tasks list (Csv preferred)
$tasksIn = @()
$requiredSource = "array"
if (-not [string]::IsNullOrWhiteSpace($RequiredTasksCsv)) {
  $tasksIn = Split-TasksCsv $RequiredTasksCsv
  $requiredSource = "csv"
} else {
  $tasksIn = @($RequiredTasks)
}

# sanitize tasks: trim + drop empty + drop anything starting with '-'
$RequiredTasks = @(
  $tasksIn |
    ForEach-Object { if ($_ -ne $null) { $_.ToString().Trim() } } |
    Where-Object { $_ -and $_ -notmatch '^\s*-' } |
    Sort-Object -Unique
)
Set-Utf8 (Join-Path $EvidenceDir "required_tasks_sanitized.txt") ((@($RequiredTasks) -join "`n") + "`n")
if (@($RequiredTasks).Count -eq 0) { throw "RequiredTasks is empty after sanitize." }

Log ("WorkerTasksSmoke: version={0}" -f $VERSION)
Log ("WorkerTasksSmoke: service={0} app={1}" -f $WorkerService, $CeleryApp)
if ($requiredSource -eq "csv") {
  Log ("WorkerTasksSmoke: required(csv)={0}" -f (@($RequiredTasks) -join ", "))
} else {
  Log ("WorkerTasksSmoke: required={0}" -f (@($RequiredTasks) -join ", "))
}
Log ("WorkerTasksSmoke: retries={0} sleep={1} ping_t={2} inspect_t={3}" -f $Retries, $SleepSec, $PingTimeoutSec, $InspectTimeoutSec)
if ($CheckUnregisteredInLogs) { Log ("WorkerTasksSmoke: log_check=on since={0}m" -f $LogsSinceMin) }

$ok = $false
$exitCode = 1
$failReason = ""
$failStage = ""
$workerName = ""
$missing = @()
$unregisteredHits = @()
$attemptsUsed = 0

$workerCid = ""
$workerState = $null

$pingLog = Join-Path $EvidenceDir "celery_ping.log"
$regLog  = Join-Path $EvidenceDir "celery_inspect_registered.log"
$sumPath = Join-Path $EvidenceDir "summary.json"

Set-Utf8 $pingLog ("ts={0}`n" -f (Now-Iso))
Set-Utf8 $regLog  ("ts={0}`n" -f (Now-Iso))

try {
  for ($i=1; $i -le $Retries; $i++) {
    $attemptsUsed = $i
    Log ("Attempt {0}/{1}: celery inspect ping ..." -f $i, $Retries)

    # 0) Get worker container id (robust against compose warnings)
    $psq = Get-ComposeServiceContainerId -composeFile $ComposeFile -projectName $ProjectName -service $WorkerService
    $workerCid = $psq.cid

    Add-Utf8 $pingLog ("--- attempt {0}/{1} ts={2} ---`nargv_psq={3}`npsq_exit_code={4}`npsq_out={5}`n`n" -f `
      $i, $Retries, (Now-Iso), $psq.argv, $psq.code, ($psq.out ?? "").TrimEnd())

    if ([string]::IsNullOrWhiteSpace($workerCid)) {
      $failStage = "container_id"
      $failReason = "worker container id not found (docker compose ps -q returned empty)"
      Start-Sleep -Seconds $SleepSec
      continue
    }

    # 1) Inspect state (avoid exec into restarting container)
    $st = Get-ContainerState -cid $workerCid
    $workerState = $st

    Add-Utf8 $pingLog ("worker_cid={0}`ninspect_ok={1}`ninspect_raw={2}`n`n" -f $workerCid, $st.ok, ($st.raw ?? $st.error ?? ""))

    if (-not $st.ok) {
      $failStage = "inspect"
      $failReason = "docker inspect failed for worker container id=$workerCid: $($st.error)"
      Start-Sleep -Seconds $SleepSec
      continue
    }

    if (($st.restarting -eq $true) -or ($st.running -ne $true) -or ($st.status -ne "running")) {
      $failStage = "container_state"
      $failReason = "worker not ready: status=$($st.status) running=$($st.running) restarting=$($st.restarting) exit=$($st.exit_code) restarts=$($st.restart_count)"
      Start-Sleep -Seconds $SleepSec
      continue
    }

    # 2) Celery ping
    $ping = DcExec -composeFile $ComposeFile -projectName $ProjectName -service $WorkerService -cmd @(
      "celery","-A",$CeleryApp,"inspect","ping","--timeout","$PingTimeoutSec"
    )
    Add-Utf8 $pingLog ("argv={0}`nexit_code={1}`n`n{2}`n" -f $ping.argv, $ping.code, $ping.out)

    if ($ping.code -ne 0 -or -not (Contains-Pong $ping.out)) {
      $failStage = "ping"
      $failReason = "ping failed or no pong replies (exit=$($ping.code))"
      Start-Sleep -Seconds $SleepSec
      continue
    }

    $workerName = Parse-WorkerNameFromPing $ping.out
    if ($workerName) { Log ("Ping OK. WorkerName: {0}" -f $workerName) } else { Log "Ping OK. WorkerName not detected." }

    # 3) Inspect registered tasks
    $cmd = New-Object System.Collections.Generic.List[string]
    $cmd.AddRange([string[]]@("celery","-A",$CeleryApp,"inspect","registered","--timeout","$InspectTimeoutSec")) | Out-Null
    if ($workerName) { $cmd.AddRange([string[]]@("-d",$workerName)) | Out-Null }

    Log "Inspecting registered tasks ..."
    $ins = DcExec -composeFile $ComposeFile -projectName $ProjectName -service $WorkerService -cmd ([string[]]$cmd.ToArray())
    Add-Utf8 $regLog ("--- attempt {0}/{1} ts={2} ---`nargv={3}`nexit_code={4}`nworker_name={5}`n`n{6}`n" -f `
      $i, $Retries, (Now-Iso), $ins.argv, $ins.code, $workerName, $ins.out)

    if ($ins.code -ne 0 -or [string]::IsNullOrWhiteSpace($ins.out)) {
      $failStage = "registered"
      $failReason = "inspect registered failed or empty output (exit=$($ins.code))"
      Start-Sleep -Seconds $SleepSec
      continue
    }

    $registered = Extract-RegisteredTasks $ins.out
    Set-Utf8 (Join-Path $EvidenceDir "registered_tasks_extracted.txt") ((@($registered) -join "`n") + "`n")

    $set = @{}
    foreach ($t in @($registered)) { if ($t) { $set[$t] = $true } }

    $missing = @()
    foreach ($req in @($RequiredTasks)) {
      if (-not $set.ContainsKey($req)) { $missing += $req }
    }

    if (@($missing).Count -gt 0) {
      Set-Utf8 (Join-Path $EvidenceDir "missing_tasks.txt") ((@($missing) -join "`n") + "`n")
      $failStage = "missing_tasks"
      $failReason = "Missing required tasks: " + (@($missing) -join ", ")
      Log ("WARN: {0}" -f $failReason)
      Start-Sleep -Seconds $SleepSec
      continue
    }

    # 4) Optional: log scan for unregistered tasks
    if ($CheckUnregisteredInLogs) {
      $since = "{0}m" -f $LogsSinceMin
      $lg = DcLogs -composeFile $ComposeFile -projectName $ProjectName -service $WorkerService -sinceArg $since -tail 0
      Set-Utf8 (Join-Path $EvidenceDir "worker_logs_recent.txt") ("ts={0}`nargv={1}`nexit_code={2}`n`n{3}" -f (Now-Iso), $lg.argv, $lg.code, $lg.out)

      $unregisteredHits = @(Detect-UnregisteredHits $lg.out)
      if (@($unregisteredHits).Count -gt 0) {
        Set-Utf8 (Join-Path $EvidenceDir "unregistered_hits.txt") ((@($unregisteredHits) -join "`n") + "`n")
        $failStage = "unregistered_in_logs"
        $failReason = "Found 'Received unregistered task' in worker logs (last ${LogsSinceMin}m)"
        Log ("WARN: {0}" -f $failReason)
        Start-Sleep -Seconds $SleepSec
        continue
      }
    }

    $ok = $true
    $exitCode = 0
    $failReason = ""
    $failStage = ""
    break
  }

  if (-not $ok -and [string]::IsNullOrWhiteSpace($failReason)) {
    $failStage = "timeout"
    $failReason = "Timeout: criteria not met"
  }
}
catch {
  $ok = $false
  $exitCode = 1
  $failStage = "exception"
  $failReason = $_.Exception.Message
  try { Set-Utf8 (Join-Path $EvidenceDir "error.txt") ($_.Exception.ToString()) } catch {}
}

# On failure: capture worker tail for quick diagnosis
if (-not $ok) {
  try {
    $tail = DcLogs -composeFile $ComposeFile -projectName $ProjectName -service $WorkerService -sinceArg "" -tail $LogsTailLinesOnFail
    Set-Utf8 (Join-Path $EvidenceDir "worker_logs_tail.txt") ("ts={0}`nargv={1}`nexit_code={2}`n`n{3}" -f (Now-Iso), $tail.argv, $tail.code, $tail.out)
  } catch {}
}

$summaryExit = 0
if (-not $ok) { $summaryExit = $exitCode }
if ($summaryExit -eq 0 -and -not $ok) { $summaryExit = 1 }

$summary = [pscustomobject]@{
  ts = Now-Iso
  version = $VERSION
  release_id = $ReleaseId

  ok = [bool]$ok
  exit_code = [int]$summaryExit
  fail_stage = [string]$failStage
  fail_reason = [string]$failReason

  compose_file = $ComposeFile
  project_name = $ProjectName

  worker_service = $WorkerService
  celery_app = $CeleryApp

  worker_container_id = $workerCid
  worker_state = $workerState

  required_tasks_source = $requiredSource
  required_tasks = @($RequiredTasks)
  required_tasks_csv = $RequiredTasksCsv

  attempts_used = [int]$attemptsUsed
  retries = [int]$Retries
  sleep_sec = [int]$SleepSec
  ping_timeout_sec = [int]$PingTimeoutSec
  inspect_timeout_sec = [int]$InspectTimeoutSec

  missing_tasks = @($missing)
  missing_tasks_cnt = [int](@($missing).Count)

  check_unregistered_logs = [bool]$CheckUnregisteredInLogs
  logs_since_min = [int]$LogsSinceMin
  unregistered_hits_cnt = [int](@($unregisteredHits).Count)

  evidence_dir = $EvidenceDir
}

try { Set-Utf8 $sumPath (($summary | ConvertTo-Json -Depth 60)) } catch {}

if ($ok) {
  Log "OK: WorkerTasksSmoke PASS"
  exit 0
} else {
  Log ("FAIL: WorkerTasksSmoke FAIL: {0}" -f $failReason)
  exit $summaryExit
}
