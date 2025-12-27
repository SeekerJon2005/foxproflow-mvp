#requires -Version 7.0
<#
FoxProFlow RUN • Worker Critical Tasks Smoke
file: scripts/pwsh/ff-worker-critical-tasks-smoke.ps1

Goal:
  Ensure Celery worker is responsive AND required tasks are registered.
  Evidence: ops/_local/evidence/<release_id>/...

Notes:
  - Uses "celery inspect ping" (more deterministic than "celery status").
  - Supports RequiredTasks (string[]) for direct invocation AND RequiredTasksCsv for pwsh -File.
  - Can optionally scan worker logs for "Received unregistered task".

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

  [int]$Retries = 10,
  [int]$SleepSec = 2,

  [int]$PingTimeoutSec = 10,
  [int]$InspectTimeoutSec = 20,

  [switch]$CheckUnregisteredInLogs,
  [int]$LogsSinceMin = 30,

  [string]$EvidenceDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Now-Stamp { (Get-Date).ToString("yyyyMMdd_HHmmss") }
function Now-Iso   { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function Repo-Root { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }

function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function Set-Utf8([string]$Path, [string]$Text) { $d=Split-Path $Path -Parent; if($d){Ensure-Dir $d}; $Text | Set-Content -LiteralPath $Path -Encoding utf8NoBOM }
function Add-Utf8([string]$Path, [string]$Text) { $d=Split-Path $Path -Parent; if($d){Ensure-Dir $d}; $Text | Add-Content -LiteralPath $Path -Encoding utf8NoBOM }

function Log([string]$msg) { Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg) }

function Resolve-ComposeFile([string]$repoRoot, [string]$composeFile) {
  if ([string]::IsNullOrWhiteSpace($composeFile)) { $composeFile = Join-Path $repoRoot "docker-compose.yml" }
  if (-not (Test-Path -LiteralPath $composeFile)) { throw "ComposeFile not found: $composeFile" }
  return (Resolve-Path -LiteralPath $composeFile).Path
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

function DcLogs([string]$composeFile, [string]$projectName, [string]$service, [string]$sinceArg) {
  $argv = @("compose","--ansi","never","-f",$composeFile)
  if ($projectName) { $argv += @("-p",$projectName) }
  $argv += @("logs","--since",$sinceArg,$service)

  $out = & docker @argv 2>&1
  $code = $LASTEXITCODE
  return [pscustomobject]@{
    code = $code
    out  = ($out | Out-String)
    argv = ("docker " + ($argv -join " "))
  }
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
  foreach ($line in ($logsText -split "`r?`n")) {
    if ($line -match 'Received unregistered task') { $hits.Add($line) | Out-Null }
  }
  return $hits.ToArray()
}

function Split-TasksCsv([string]$csv) {
  if ([string]::IsNullOrWhiteSpace($csv)) { return @() }
  return @(
    ($csv -split '[,;`r`n]+' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  )
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

# Build tasks input from Csv (if provided) else from RequiredTasks
$tasksIn = @()
if (-not [string]::IsNullOrWhiteSpace($RequiredTasksCsv)) {
  $tasksIn = Split-TasksCsv $RequiredTasksCsv
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
if (@($RequiredTasks).Count -eq 0) { throw "RequiredTasks is empty after sanitize." }

Log ("WorkerTasksSmoke: service={0} app={1}" -f $WorkerService, $CeleryApp)
Log ("WorkerTasksSmoke: required={0}" -f (@($RequiredTasks) -join ", "))
Log ("WorkerTasksSmoke: retries={0} sleep={1} ping_t={2} inspect_t={3}" -f $Retries, $SleepSec, $PingTimeoutSec, $InspectTimeoutSec)
if ($CheckUnregisteredInLogs) { Log ("WorkerTasksSmoke: log_check=on since={0}m" -f $LogsSinceMin) }

$ok = $false
$exitCode = 1
$failReason = ""
$workerName = ""
$missing = @()
$unregisteredHits = @()

$pingLog = Join-Path $EvidenceDir "celery_ping.log"
$regLog  = Join-Path $EvidenceDir "celery_inspect_registered.log"
$sumPath = Join-Path $EvidenceDir "summary.json"

Set-Utf8 $pingLog ("ts={0}`n" -f (Now-Iso))
Set-Utf8 $regLog  ("ts={0}`n" -f (Now-Iso))

try {
  for ($i=1; $i -le $Retries; $i++) {
    Log ("Attempt {0}/{1}: celery inspect ping ..." -f $i, $Retries)

    $ping = DcExec -composeFile $ComposeFile -projectName $ProjectName -service $WorkerService -cmd @(
      "celery","-A",$CeleryApp,"inspect","ping","--timeout",$PingTimeoutSec
    )
    Add-Utf8 $pingLog ("--- attempt {0}/{1} ts={2} ---`nargv={3}`nexit_code={4}`n`n{5}`n" -f $i, $Retries, (Now-Iso), $ping.argv, $ping.code, $ping.out)

    if ($ping.code -ne 0 -or -not (Contains-Pong $ping.out)) {
      $failReason = "ping failed or no pong replies (exit=$($ping.code))"
      Start-Sleep -Seconds $SleepSec
      continue
    }

    $workerName = Parse-WorkerNameFromPing $ping.out
    if ($workerName) { Log ("Ping OK. WorkerName: {0}" -f $workerName) } else { Log "Ping OK. WorkerName not detected." }

    $cmd = New-Object System.Collections.Generic.List[string]
    $cmd.AddRange([string[]]@("celery","-A",$CeleryApp,"inspect","registered","--timeout",$InspectTimeoutSec)) | Out-Null
    if ($workerName) { $cmd.AddRange([string[]]@("-d",$workerName)) | Out-Null }

    Log "Inspecting registered tasks ..."
    $ins = DcExec -composeFile $ComposeFile -projectName $ProjectName -service $WorkerService -cmd ([string[]]$cmd.ToArray())
    Add-Utf8 $regLog ("--- attempt {0}/{1} ts={2} ---`nargv={3}`nexit_code={4}`nworker_name={5}`n`n{6}`n" -f `
      $i, $Retries, (Now-Iso), $ins.argv, $ins.code, $workerName, $ins.out)

    if ($ins.code -ne 0 -or [string]::IsNullOrWhiteSpace($ins.out)) {
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
      $failReason = "Missing required tasks: " + (@($missing) -join ", ")
      Log ("WARN: {0}" -f $failReason)
      Start-Sleep -Seconds $SleepSec
      continue
    }

    if ($CheckUnregisteredInLogs) {
      $since = "{0}m" -f $LogsSinceMin
      $lg = DcLogs -composeFile $ComposeFile -projectName $ProjectName -service $WorkerService -sinceArg $since
      Set-Utf8 (Join-Path $EvidenceDir "worker_logs_recent.txt") ("ts={0}`nargv={1}`nexit_code={2}`n`n{3}" -f (Now-Iso), $lg.argv, $lg.code, $lg.out)

      $unregisteredHits = @(Detect-UnregisteredHits $lg.out)
      if (@($unregisteredHits).Count -gt 0) {
        Set-Utf8 (Join-Path $EvidenceDir "unregistered_hits.txt") ((@($unregisteredHits) -join "`n") + "`n")
        $failReason = "Found 'Received unregistered task' in worker logs (last ${LogsSinceMin}m)"
        Log ("WARN: {0}" -f $failReason)
        Start-Sleep -Seconds $SleepSec
        continue
      }
    }

    $ok = $true
    $exitCode = 0
    $failReason = ""
    break
  }

  if (-not $ok -and [string]::IsNullOrWhiteSpace($failReason)) {
    $failReason = "Timeout: criteria not met"
  }
}
catch {
  $ok = $false
  $exitCode = 1
  $failReason = $_.Exception.Message
  try { Set-Utf8 (Join-Path $EvidenceDir "error.txt") ($_.Exception.ToString()) } catch {}
}

$summaryExit = 0
if (-not $ok) { $summaryExit = $exitCode }
if ($summaryExit -eq 0 -and -not $ok) { $summaryExit = 1 }

$summary = [pscustomobject]@{
  ts = Now-Iso
  ok = [bool]$ok
  exit_code = [int]$summaryExit
  fail_reason = [string]$failReason
  compose_file = $ComposeFile
  project_name = $ProjectName
  worker_service = $WorkerService
  celery_app = $CeleryApp
  worker_name = $workerName
  required_tasks = @($RequiredTasks)
  required_tasks_csv = $RequiredTasksCsv
  missing_tasks = @($missing)
  missing_tasks_cnt = [int](@($missing).Count)
  check_unregistered_logs = [bool]$CheckUnregisteredInLogs
  logs_since_min = [int]$LogsSinceMin
  unregistered_hits_cnt = [int](@($unregisteredHits).Count)
  evidence_dir = $EvidenceDir
}

try { Set-Utf8 $sumPath (($summary | ConvertTo-Json -Depth 40)) } catch {}

if ($ok) {
  Log "OK: WorkerTasksSmoke PASS"
  exit 0
} else {
  Log ("FAIL: WorkerTasksSmoke FAIL: {0}" -f $failReason)
  exit $summaryExit
}
