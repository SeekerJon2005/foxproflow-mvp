#requires -Version 7.0
<#
FoxProFlow • Security Lane • Gate v0 (one-click)
file: scripts/pwsh/sec/ff-sec-gate-v0.ps1

Runs:
  1) sec preflight (evidence)
  2) surface map
  3) policy map
  4) immune watchlist
  5) immune drill (evidence)
  6) coverage score

Outputs:
  - evidence folder: ops/_local/evidence/sec_gate_v0_<stamp>/
  - per-step logs: step_XX_*.log
  - copies key json summaries into evidence
  - prints OK/WARN/CRIT and exits:
      0 OK
      2 WARN (degraded)
      3 CRIT (failed)
#>

[CmdletBinding(PositionalBinding = $false)]
param(
  [string]$BaseUrl = $(if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8080" }),
  [string]$ProjectName = $(if ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "foxproflow-mvp20" }),
  [string]$ComposeFile = "",
  [int]$TimeoutSec = 10,
  [int]$LogsSinceMin = 15
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Now-Stamp { Get-Date -Format "yyyyMMdd_HHmmss" }
function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }

function Ensure-Dir([string]$p) {
  if ([string]::IsNullOrWhiteSpace($p)) { return }
  New-Item -ItemType Directory -Force -Path $p | Out-Null
}

function Repo-Root {
  (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Write-Utf8([string]$path, [string]$text) {
  $dir = Split-Path $path -Parent
  if ($dir) { Ensure-Dir $dir }
  $text | Set-Content -LiteralPath $path -Encoding utf8NoBOM
}

function Run-Step {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string[]]$PwshArgs,
    [Parameter(Mandatory = $true)][string]$LogPath
  )

  Write-Host ""
  Write-Host ("==> {0}" -f $Name) -ForegroundColor Cyan

  $out = & pwsh @PwshArgs 2>&1
  $code = $LASTEXITCODE

  Write-Utf8 $LogPath ($out | Out-String)

  if ($code -ne 0) {
    Write-Host ("FAIL: {0} (exit={1})" -f $Name, $code) -ForegroundColor Red
    Write-Host ("See log: {0}" -f $LogPath) -ForegroundColor Yellow
  }

  return [pscustomobject]@{ code = [int]$code; log = $LogPath }
}

# --- init ---
$root = Repo-Root
if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
  $ComposeFile = Join-Path $root "docker-compose.yml"
}
if (-not (Test-Path -LiteralPath $ComposeFile)) {
  throw "ComposeFile not found: $ComposeFile"
}

$evRoot = Join-Path $root "ops\_local\evidence"
Ensure-Dir $evRoot

$gateId = "sec_gate_v0_" + (Now-Stamp)
$gateDir = Join-Path $evRoot $gateId
Ensure-Dir $gateDir

$meta = [pscustomobject]@{
  ts = Now-Iso
  gate = "sec_gate_v0"
  base_url = $BaseUrl
  compose_project = $ProjectName
  compose_file = $ComposeFile
  logs_since_min = $LogsSinceMin
  timeout_sec = $TimeoutSec
  gate_dir = $gateDir
}
($meta | ConvertTo-Json -Depth 32) | Set-Content -Encoding utf8NoBOM -LiteralPath (Join-Path $gateDir "gate_meta.json")

# Paths to scripts
$secPreflight = Join-Path $root "scripts\pwsh\sec\ff-sec-preflight.ps1"
$surfaceMap   = Join-Path $root "scripts\pwsh\sec\ff-sec-surface-map.ps1"
$policyMap    = Join-Path $root "scripts\pwsh\sec\ff-sec-policy-map.ps1"
$watchlist    = Join-Path $root "scripts\pwsh\sec\ff-sec-immune-watchlist.ps1"
$drill        = Join-Path $root "scripts\pwsh\sec\ff-sec-drill.ps1"
$coverage     = Join-Path $root "scripts\pwsh\sec\ff-sec-coverage-score.ps1"

foreach ($p in @($secPreflight, $surfaceMap, $policyMap, $watchlist, $drill, $coverage)) {
  if (-not (Test-Path -LiteralPath $p)) { throw "Missing script: $p" }
}

# Track overall status
$gateStatus = "OK"   # OK/WARN/CRIT

# --- Step 1: Preflight ---
$r1 = Run-Step -Name "SEC PREFLIGHT" -PwshArgs @(
  "-NoProfile",
  "-File", $secPreflight,
  "-BaseUrl", $BaseUrl,
  "-ProjectName", $ProjectName,
  "-ComposeFile", $ComposeFile,
  "-TimeoutSec", $TimeoutSec
) -LogPath (Join-Path $gateDir "step_01_preflight.log")

if ($r1.code -ne 0) { exit 3 }

# Locate the newest preflight evidence folder (best-effort)
$preEv = Get-ChildItem $evRoot -Directory |
  Where-Object { $_.Name -like "sec_preflight_*" } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if ($preEv) {
  Write-Utf8 (Join-Path $gateDir "preflight_evidence_dir.txt") $preEv.FullName
} else {
  Write-Utf8 (Join-Path $gateDir "preflight_evidence_dir.txt") "NOT_FOUND"
  # Surface/policy map may still run if EvidenceDir passed manually, but for gate we consider this critical
  Write-Host "CRIT: cannot locate sec_preflight evidence dir" -ForegroundColor Red
  exit 3
}

# --- Step 2: Surface map ---
$r2 = Run-Step -Name "SEC SURFACE MAP" -PwshArgs @(
  "-NoProfile",
  "-File", $surfaceMap,
  "-EvidenceDir", $preEv.FullName
) -LogPath (Join-Path $gateDir "step_02_surface_map.log")

if ($r2.code -ne 0) { exit 3 }

# --- Step 3: Policy map ---
$r3 = Run-Step -Name "SEC POLICY MAP" -PwshArgs @(
  "-NoProfile",
  "-File", $policyMap,
  "-EvidenceDir", $preEv.FullName
) -LogPath (Join-Path $gateDir "step_03_policy_map.log")

if ($r3.code -ne 0) { exit 3 }

# --- Step 4: Immune watchlist ---
$r4 = Run-Step -Name "SEC IMMUNE WATCHLIST" -PwshArgs @(
  "-NoProfile",
  "-File", $watchlist
) -LogPath (Join-Path $gateDir "step_04_watchlist.log")

if ($r4.code -ne 0) { exit 3 }

# --- Step 5: Drill ---
$r5 = Run-Step -Name "SEC DRILL" -PwshArgs @(
  "-NoProfile",
  "-File", $drill,
  "-BaseUrl", $BaseUrl,
  "-ProjectName", $ProjectName,
  "-ComposeFile", $ComposeFile,
  "-TimeoutSec", $TimeoutSec,
  "-LogsSinceMin", $LogsSinceMin
) -LogPath (Join-Path $gateDir "step_05_drill.log")

# Drill has 3 states: 0 OK, 2 WARN, 3 CRIT
if ($r5.code -eq 2) { $gateStatus = "WARN" }
elseif ($r5.code -ne 0) { $gateStatus = "CRIT"; exit 3 }

# Locate latest sec_drill evidence folder (best-effort)
$drEv = Get-ChildItem $evRoot -Directory |
  Where-Object { $_.Name -like "sec_drill_*" } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if ($drEv) { Write-Utf8 (Join-Path $gateDir "drill_evidence_dir.txt") $drEv.FullName }

# --- Step 6: Coverage score ---
$r6 = Run-Step -Name "SEC COVERAGE" -PwshArgs @(
  "-NoProfile",
  "-File", $coverage
) -LogPath (Join-Path $gateDir "step_06_coverage.log")

if ($r6.code -ne 0) { exit 3 }

# Copy summaries to evidence
$docsSec = Join-Path $root "docs\ops\security"
$copy = @(
  "security_surface_map_v0.json",
  "security_policy_map_v0.json",
  "security_immune_watchlist_v0.json",
  "security_coverage_score_v0.json"
)
foreach ($f in $copy) {
  $src = Join-Path $docsSec $f
  if (Test-Path -LiteralPath $src) {
    Copy-Item -Force -LiteralPath $src -Destination (Join-Path $gateDir $f)
  }
}

Write-Host ""
Write-Host ("[SEC GATE v0] status={0}" -f $gateStatus) -ForegroundColor $(if ($gateStatus -eq "OK") { "Green" } else { "Yellow" })
Write-Host ("[SEC GATE v0] evidence={0}" -f $gateDir)

if ($gateStatus -eq "OK") { exit 0 }
exit 2
