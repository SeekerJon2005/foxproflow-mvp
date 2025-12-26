#requires -Version 7.0
<#
FoxProFlow RUN • Worker Critical Tasks Smoke
file: scripts/pwsh/ff-worker-critical-tasks-smoke.ps1

Goal:
  Ensure Celery worker is responsive AND required tasks are registered.
  PASS/FAIL + evidence dir.

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

  # If you don't pass -RequiredTasks explicitly, we use CORE defaults below.
  [string[]]$RequiredTasks = @(
    "ops.beat.heartbeat",
    "ops.queue.watchdog",
    "ops.alerts.sla",
    "routing.osrm.warmup",
    "routing.smoke.osrm_and_db",
    "crm.smoke.ping",
    "crm.smoke.db_contract_v2",
    "devorders.smoke.db_contract",
    "devfactory.commercial.run_order"
  ),

  # Robust matching: exact OR fuzzy tokens (planner.kpi.snapshot -> planner.*kpi.*snapshot)
  [switch]$UseFuzzyMatch,

  [int]$Retries = 30,
  [int]$SleepSec = 2,

  [int]$StatusTimeoutSec = 5,
  [int]$InspectTimeoutSec = 10,

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

function Extract-RegisteredTasks([string]$text) {
  $list = New-Object System.Collections.Generic.List[string]
  foreach ($ln in ($text -split "`r?`n")) {
    $m = [regex]::Match($ln, '^\s*\*\s+(.+?)\s*$')
    if ($m.Success) { $list.Add($m.Groups[1].Value.Trim()) | Out-Null }
  }
  return ($list.ToArray() | Where-Object { $_ } | Sort-Object -Unique)
}

function Build-FuzzyPattern([string]$taskName) {
  $tokens = @($taskName -split '\.' | Where-Object { $_ })
  if ($tokens.Count -eq 0) { return [regex]::Escape($taskName) }
  $esc = $tokens | ForEach-Object { [regex]::Escape($_) }
  return ($esc -join '.*')
}

function Task-Exists([string]$required, [string[]]$registered, [bool]$useFuzzy) {
  if (-not $registered) { return $false }
  $req = $required.Trim()
  if ([string]::IsNullOrWhiteSpace($req)) { return $true }

  $regLower = @($registered | ForEach-Object { $_.ToLowerInvariant() })
  if ($regLower -contains $req.ToLowerInvariant()) { return $true }

  if (-not $useFuzzy) { return $false }

  $pat = Build-FuzzyPattern $required
  foreach ($r in $registered) {
    if ($r -match $pat) { return $true }
  }
  return $false
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

# default: enable fuzzy match (safer)
if (-not $PSBoundParameters.ContainsKey("UseFuzzyMatch")) { $UseFuzzyMatch = $true }

Log ("WorkerTasksSmoke: service={0} app={1}" -f $WorkerService, $CeleryApp)
Log ("WorkerTasksSmoke: required={0}" -f ((@($RequiredTasks) -join ", ")))
Log ("WorkerTasksSmoke: retries={0} sleep={1} status_t={2} inspect_t={3} fuzzy={4}" -f $Retries, $SleepSec, $StatusTimeoutSec, $InspectTimeoutSec, [bool]$UseFuzzyMatch)

$ok = $false
$missing = @()
$exitCode = 1
$failReason = ""

try {
  $statusLog  = Join-Path $EvidenceDir "celery_status.log"
  $inspectLog = Join-Path $EvidenceDir "celery_inspect_registered.log"

  for ($i=1; $i -le $Retries; $i++) {
    Log ("Attempt {0}/{1}: celery status ..." -f $i, $Retries)

    $st = DcExec -composeFile $ComposeFile -projectName $ProjectName -service $WorkerService -cmd @(
      "celery","-A",$CeleryApp,"status","--timeout",$StatusTimeoutSec
    )
    Set-Utf8 $statusLog ("ts={0}`nargv={1}`nexit_code={2}`n`n{3}" -f (Now-Iso), $st.argv, $st.code, $st.out)

    if ($st.code -eq 0 -and -not [string]::IsNullOrWhiteSpace($st.out)) {
      Log "celery status OK, inspecting registered tasks ..."
      $ins = DcExec -composeFile $ComposeFile -projectName $ProjectName -service $WorkerService -cmd @(
        "celery","-A",$CeleryApp,"inspect","registered","--timeout",$InspectTimeoutSec
      )
      Set-Utf8 $inspectLog ("ts={0}`nargv={1}`nexit_code={2}`n`n{3}" -f (Now-Iso), $ins.argv, $ins.code, $ins.out)

      if ($ins.code -eq 0 -and -not [string]::IsNullOrWhiteSpace($ins.out)) {
        $taskNames = Extract-RegisteredTasks $ins.out
        Set-Utf8 (Join-Path $EvidenceDir "registered_tasks_extracted.txt") (($taskNames -join "`n"))

        $missing = @()
        foreach ($t in @($RequiredTasks)) {
          if ([string]::IsNullOrWhiteSpace($t)) { continue }
          if (-not (Task-Exists -required $t -registered $taskNames -useFuzzy ([bool]$UseFuzzyMatch))) { $missing += $t }
        }

        if ($missing.Count -eq 0) {
          $ok = $true
          $exitCode = 0
          $failReason = ""
          break
        } else {
          $failReason = "Missing required tasks: " + ($missing -join ", ")
          Set-Utf8 (Join-Path $EvidenceDir "missing_tasks.txt") (($missing -join "`n"))
          Log ("WARN: {0}" -f $failReason)
        }
      } else {
        $failReason = "celery inspect registered failed (exit=$($ins.code))"
        Log ("WARN: {0}" -f $failReason)
      }
    } else {
      $failReason = "celery status failed (exit=$($st.code))"
      Log ("WARN: {0}" -f $failReason)
    }

    Start-Sleep -Seconds $SleepSec
  }
} catch {
  $ok = $false
  $exitCode = 1
  $failReason = $_.Exception.Message
  try { Set-Utf8 (Join-Path $EvidenceDir "error.txt") ($_.Exception.ToString()) } catch {}
}

$summary = [pscustomobject]@{
  ts = Now-Iso
  ok = [bool]$ok
  exit_code = [int]$exitCode
  fail_reason = [string]$failReason
  compose_file = $ComposeFile
  project_name = $ProjectName
  worker_service = $WorkerService
  celery_app = $CeleryApp
  fuzzy_match = [bool]$UseFuzzyMatch
  required_tasks = @($RequiredTasks)
  missing_tasks = @($missing)
  evidence_dir = $EvidenceDir
}

try { Set-Utf8 (Join-Path $EvidenceDir "summary.json") (($summary | ConvertTo-Json -Depth 40)) } catch {}

if ($ok) {
  Log "OK: WorkerTasksSmoke PASS"
  exit 0
} else {
  Log ("FAIL: WorkerTasksSmoke FAIL: {0}" -f $failReason)
  exit $exitCode
}
