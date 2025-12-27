#requires -Version 7.0
<#
FoxProFlow • FlowMeta utility
file: scripts/pwsh/ff-flowmeta-scoreboard.ps1

Goal:
  Fast scoreboard snapshot (local + docker + API):
    - git branch/dirty + commits since last N hours
    - docker compose ps -a (raw)
    - API health JSON (prefer /health/extended, fallback to /health/extended2, then /health)

Save:
  - _flowmeta\latest_scoreboard.json (pretty)
  - _flowmeta\scoreboard.jsonl (append, 1 line per run)

Safe:
  - no secret env values collected
  - no docker logs collected here
#>

[CmdletBinding()]
param(
  [int]$SinceHours = 24,
  [string]$ApiBase = "http://127.0.0.1:8080",
  [string]$ComposeFile = (Join-Path (Get-Location).Path "docker-compose.yml"),
  [string]$OutDir = (Join-Path (Get-Location).Path "_flowmeta")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string]$msg) { Write-Host "[META] $msg" -ForegroundColor Cyan }
function Write-Warn([string]$msg) { Write-Host "[META][WARN] $msg" -ForegroundColor Yellow }

function Ensure-Dir([string]$path) { New-Item -ItemType Directory -Path $path -Force | Out-Null }

function Try-Run([scriptblock]$cmd) {
  try {
    $out = & $cmd 2>&1
    return ,$out
  } catch {
    return ,@("ERROR: $($_.Exception.Message)")
  }
}

function Try-HttpJson([string]$url) {
  try {
    $obj = Invoke-RestMethod -Method Get -Uri $url -TimeoutSec 8
    return @{ ok = $true; data = $obj; err = $null }
  } catch {
    # Keep it concise (no secrets), but actionable.
    $msg = $_.Exception.Message
    return @{ ok = $false; data = $null; err = $msg }
  }
}

$rid = "score_" + (Get-Date -Format "yyyyMMdd_HHmmss")
Ensure-Dir $OutDir

$since = (Get-Date).AddHours(-$SinceHours)
$sinceArg = $since.ToString("yyyy-MM-ddTHH:mm:ss")

Write-Info "RID: $rid"
Write-Info "SinceHours: $SinceHours (since $sinceArg)"
Write-Info "ApiBase: $ApiBase"

# --- Git
$gitBranch = (Try-Run { git rev-parse --abbrev-ref HEAD }) | Select-Object -First 1
$gitDirtyLines = Try-Run { git status --porcelain }
$gitDirty = (($gitDirtyLines | Where-Object { $_ -and $_ -notmatch '^ERROR:' }) | Measure-Object).Count -gt 0

$gitCommits = Try-Run { git log --since="$sinceArg" --pretty=format:"%h|%ad|%an|%s" --date=iso-strict }
$gitCommitLines = $gitCommits | Where-Object { $_ -and $_ -notmatch '^ERROR:' }
$gitCommitCount = ($gitCommitLines | Measure-Object).Count

$gitLast = (Try-Run { git log -1 --pretty=format:"%h|%ad|%an|%s" --date=iso-strict }) | Select-Object -First 1

# --- Docker compose ps
$dockerPs = Try-Run { docker compose --ansi never -f $ComposeFile ps -a }

# --- API health (prefer /health/extended, fallback to /health/extended2, then /health)
$healthSource = "/health/extended"
$h = Try-HttpJson -url ("$ApiBase/health/extended")

if (-not $h.ok) {
  $h2 = Try-HttpJson -url ("$ApiBase/health/extended2")
  if ($h2.ok) {
    $h = $h2
    $healthSource = "/health/extended2"
  } else {
    $h3 = Try-HttpJson -url ("$ApiBase/health")
    if ($h3.ok) {
      $h = $h3
      $healthSource = "/health"
    }
  }
}

$score = [ordered]@{
  rid          = $rid
  ts_utc       = (Get-Date).ToUniversalTime().ToString("o")
  ts_local     = (Get-Date).ToString("o")
  cwd          = (Get-Location).Path
  since_hours  = $SinceHours
  git          = [ordered]@{
    branch        = $gitBranch
    dirty         = $gitDirty
    commit_count  = $gitCommitCount
    last_commit   = $gitLast
  }
  docker       = [ordered]@{
    compose_file  = $ComposeFile
    ps_raw        = ($dockerPs -join "`n")
  }
  api          = [ordered]@{
    base          = $ApiBase
    health_path   = $healthSource
    health_ok     = [bool]$h.ok
    health_error  = $h.err
    health_data   = $h.data
  }
}

$latestPath  = Join-Path $OutDir "latest_scoreboard.json"
$historyPath = Join-Path $OutDir "scoreboard.jsonl"

# pretty latest
($score | ConvertTo-Json -Depth 50) | Out-File -FilePath $latestPath -Encoding utf8

# jsonl history (one line)
($score | ConvertTo-Json -Depth 50 -Compress) | Out-File -FilePath $historyPath -Encoding utf8 -Append

Write-Host ""
Write-Host "=== SCOREBOARD SUMMARY ===" -ForegroundColor Green
Write-Host ("Git: branch={0} dirty={1} commits({2}h)={3}" -f $gitBranch, $gitDirty, $SinceHours, $gitCommitCount)
Write-Host ("Docker: compose ps captured -> {0} lines" -f (($dockerPs | Measure-Object).Count))
Write-Host ("API {0}: ok={1}" -f $healthSource, [bool]$h.ok)

if ($h.ok -and $null -ne $h.data) {
  try {
    if ($null -ne $h.data.queue_len)            { Write-Host ("  queue_len: {0}" -f $h.data.queue_len) }
    if ($null -ne $h.data.beat_age_sec)         { Write-Host ("  beat_age_sec: {0}" -f $h.data.beat_age_sec) }
    if ($null -ne $h.data.queue_busy_streak_min){ Write-Host ("  queue_busy_streak_min: {0}" -f $h.data.queue_busy_streak_min) }
  } catch { }
} elseif (-not $h.ok) {
  Write-Warn ("API error: {0}" -f $h.err)
}

Write-Host ""
Write-Host ("Saved: {0}" -f $latestPath)
Write-Host ("History: {0}" -f $historyPath)
