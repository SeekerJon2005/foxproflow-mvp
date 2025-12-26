#requires -Version 7.0
<#
FoxProFlow • Security Lane • Immune Drill (read-only evidence snapshot)
file: scripts/pwsh/sec/ff-sec-drill.ps1

Goal:
  - One command to collect evidence for Immune Watchlist signals (read-only).
  - Produce evidence pack folder:
      ops/_local/evidence/sec_drill_<stamp>/
        - drill_meta.json
        - health_extended.json (or snip)
        - compose_ps.txt
        - logs_worker_tail.txt
        - logs_api_tail.txt
        - redis_llen.txt
        - drill_summary.json

Rules:
  - READ-ONLY: no apply, no SQL, no compose up/down.
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$BaseUrl = $(if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8080" }),
  [string]$ProjectName = $(if ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "foxproflow-mvp20" }),
  [string]$ComposeFile = "",

  [string]$WatchlistJson = "",
  [string]$EvidenceRoot = "",

  [int]$TimeoutSec = 10,
  [int]$LogsTailLines = 400,
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

function Join-Url([string]$base, [string]$path) {
  $b = $base.TrimEnd("/")
  $p = $path.TrimStart("/")
  return "$b/$p"
}

function DcExec([string[]]$args) {
  $argv = @("compose","--ansi","never")
  if (-not [string]::IsNullOrWhiteSpace($ComposeFile)) { $argv += @("-f",$ComposeFile) }
  if (-not [string]::IsNullOrWhiteSpace($ProjectName)) { $argv += @("-p",$ProjectName) }
  $argv += $args
  & docker @argv 2>&1
}

function Try-ParseJson([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return $null }
  try { return ($text | ConvertFrom-Json -Depth 64) } catch { return $null }
}

function Invoke-HttpJson([string]$url) {
  $body = ""
  $code = 0
  $err  = ""
  $json = $null

  $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
  try {
    if ($curl) {
      $tmp = [System.IO.Path]::GetTempFileName()
      try {
        $httpCodeStr = & curl.exe -4 --http1.1 --noproxy 127.0.0.1 -sS -m $TimeoutSec -w "%{http_code}" -o $tmp $url 2>&1
        $m = [regex]::Match($httpCodeStr, "(\d{3})\s*$")
        if ($m.Success) { $code = [int]$m.Groups[1].Value } else { $code = 0 }
        $body = Get-Content -Raw -Path $tmp -ErrorAction SilentlyContinue
        if ($code -eq 0 -and -not [string]::IsNullOrWhiteSpace($httpCodeStr)) { $err = $httpCodeStr.Trim() }
      } finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $tmp
      }
    } else {
      $resp = Invoke-WebRequest -Uri $url -TimeoutSec $TimeoutSec -SkipHttpErrorCheck
      $code = [int]$resp.StatusCode
      $body = [string]$resp.Content
    }

    $json = Try-ParseJson $body
    return [pscustomobject]@{ url=$url; http_code=$code; ok=($code -ge 200 -and $code -lt 300); err=$err; json=$json; body=$body }
  } catch {
    return [pscustomobject]@{ url=$url; http_code=0; ok=$false; err=$_.Exception.Message; json=$null; body="" }
  }
}

function Load-JsonFile([string]$p) {
  $full = (Resolve-Path -LiteralPath $p).Path
  (Get-Content -Raw -LiteralPath $full) | ConvertFrom-Json -Depth 100
}

# Resolve repo root + defaults
$WorktreeRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
if ([string]::IsNullOrWhiteSpace($ComposeFile)) { $ComposeFile = Join-Path $WorktreeRoot "docker-compose.yml" }
if (-not (Test-Path -LiteralPath $ComposeFile)) { throw "ComposeFile not found: $ComposeFile" }

if ([string]::IsNullOrWhiteSpace($EvidenceRoot)) { $EvidenceRoot = Join-Path $WorktreeRoot "ops\_local\evidence" }
Ensure-Dir $EvidenceRoot

if ([string]::IsNullOrWhiteSpace($WatchlistJson)) {
  $WatchlistJson = Join-Path $WorktreeRoot "docs\ops\security\security_immune_watchlist_v0.json"
}
if (-not (Test-Path -LiteralPath $WatchlistJson)) { throw "WatchlistJson not found: $WatchlistJson" }

$wl = Load-JsonFile $WatchlistJson
$watchItems = @($wl.watchlist)

$runId = "sec_drill_" + (Now-Stamp)
$evDir = Join-Path $EvidenceRoot $runId
Ensure-Dir $evDir

# Collect
$meta = [pscustomobject]@{
  ts = Now-Iso
  lane = "security"
  script = (Resolve-Path $PSCommandPath).Path
  worktree_root = $WorktreeRoot
  compose_file = $ComposeFile
  compose_project = $ProjectName
  base_url = $BaseUrl
  watchlist_json = $WatchlistJson
  logs_since_min = $LogsSinceMin
  logs_tail_lines = $LogsTailLines
}

($meta | ConvertTo-Json -Depth 32) | Set-Content -LiteralPath (Join-Path $evDir "drill_meta.json") -Encoding utf8NoBOM

# compose ps
$psOut = DcExec @("ps")
Set-Content -LiteralPath (Join-Path $evDir "compose_ps.txt") -Value ($psOut | Out-String) -Encoding utf8NoBOM

# health
$health = Invoke-HttpJson (Join-Url $BaseUrl "/health/extended")
if ($health.json) {
  ($health.json | ConvertTo-Json -Depth 64) | Set-Content -LiteralPath (Join-Path $evDir "health_extended.json") -Encoding utf8NoBOM
} else {
  Set-Content -LiteralPath (Join-Path $evDir "health_extended_raw.txt") -Value ($health.body) -Encoding utf8NoBOM
}

# logs (worker/api)
$since = ("--since={0}m" -f $LogsSinceMin)
$wlog = DcExec @("logs",$since,"--tail",$LogsTailLines.ToString(),"worker")
$alog = DcExec @("logs",$since,"--tail",$LogsTailLines.ToString(),"api")
Set-Content -LiteralPath (Join-Path $evDir "logs_worker_tail.txt") -Value ($wlog | Out-String) -Encoding utf8NoBOM
Set-Content -LiteralPath (Join-Path $evDir "logs_api_tail.txt") -Value ($alog | Out-String) -Encoding utf8NoBOM

# redis LLEN (best-effort)
$queues = @("celery","autoplan","parsers","agents")
$llenLines = New-Object System.Collections.Generic.List[string]
foreach ($q in $queues) {
  try {
    $n = DcExec @("exec","-T","redis","redis-cli","LLEN",$q) | Select-Object -First 1
    $llenLines.Add(("LLEN {0} = {1}" -f $q, ([string]$n).Trim())) | Out-Null
  } catch {
    $llenLines.Add(("LLEN {0} = ERROR: {1}" -f $q, $_.Exception.Message)) | Out-Null
  }
}
Set-Content -LiteralPath (Join-Path $evDir "redis_llen.txt") -Value ($llenLines.ToArray() -join [Environment]::NewLine) -Encoding utf8NoBOM

# Evaluate simple status (advisory)
$flags = New-Object System.Collections.Generic.List[string]

if (-not $health.ok) { $flags.Add(("WARN: /health/extended http_code={0} err={1}" -f $health.http_code, $health.err)) | Out-Null }

foreach ($line in $llenLines) {
  if ($line -match 'LLEN\s+\w+\s*=\s*(\d+)') {
    $v = [int]$matches[1]
    if ($v -gt 1000) { $flags.Add(("CRIT: {0}" -f $line)) | Out-Null }
    elseif ($v -gt 100) { $flags.Add(("WARN: {0}" -f $line)) | Out-Null }
  }
}

# Scan logs for hard signals (very simple)
if ($wlog -match 'Received unregistered task') { $flags.Add("CRIT: worker saw 'Received unregistered task'") | Out-Null }
if ($wlog -match 'Traceback|CRITICAL|FATAL') { $flags.Add("WARN: worker error signatures present") | Out-Null }
if ($alog -match 'Traceback|CRITICAL|FATAL') { $flags.Add("WARN: api error signatures present") | Out-Null }

$status = "OK"
if ($flags | Where-Object { $_ -like "CRIT:*" }) { $status = "CRIT" }
elseif ($flags.Count -gt 0) { $status = "WARN" }

$summary = [pscustomobject]@{
  ok = ($status -eq "OK")
  status = $status
  evidence_dir = $evDir
  flags = @($flags)
  watchlist_items = @($watchItems | Select-Object id, prio, signal, threshold)
}

($summary | ConvertTo-Json -Depth 64) | Set-Content -LiteralPath (Join-Path $evDir "drill_summary.json") -Encoding utf8NoBOM

Write-Host ("[SEC DRILL] status={0}" -f $status) -ForegroundColor $(if ($status -eq "OK") { "Green" } elseif ($status -eq "WARN") { "Yellow" } else { "Red" })
Write-Host ("[SEC DRILL] evidence: {0}" -f $evDir)

if ($flags.Count -gt 0) {
  Write-Host "[SEC DRILL] flags:" -ForegroundColor Yellow
  $flags | ForEach-Object { Write-Host ("  - {0}" -f $_) -ForegroundColor Yellow }
}

if ($status -eq "OK") { exit 0 }
if ($status -eq "WARN") { exit 2 }
exit 3
