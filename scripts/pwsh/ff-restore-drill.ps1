#requires -Version 7.0
<#
FoxProFlow RUN • Restore Drill (dedicated postgres-only compose)
file: scripts/pwsh/ff-restore-drill.ps1

Flow:
  - pick latest backup
  - read manifest -> db/user (supports legacy + newer schemas)
  - start dedicated postgres via ops/drill/docker-compose.pg-drill.yml (separate compose project)
  - restore from backup into drill postgres
  - basic DB checks
  - down -v (default)
  - evidence: ops/_local/evidence/restore_drill_*/ (RAW + summary + digest)

Created by: Архитектор Яцков Евгений Анатольевич
Lane: A-RUN only
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$BackupPath = "",

  [string]$DrillProjectName = "ff-drill-restore",
  [string]$DrillComposeFile = "",

  [string]$PgService = "postgres",

  [int]$ReadyTimeoutSec = 120,
  [int]$ReadyPollSec = 2,

  [switch]$KeepOnFail,
  [switch]$KeepOnSuccess
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$SCRIPT_VERSION = "2025-12-27.v4"

function ThrowIf([bool]$cond, [string]$msg) { if ($cond) { throw $msg } }
function EnsureDir([string]$p) { if (-not (Test-Path -LiteralPath $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function NowIso() { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }

function FindRepoRoot([string]$from) {
  $d = (Resolve-Path -LiteralPath $from).Path
  if (-not (Test-Path -LiteralPath $d -PathType Container)) { $d = Split-Path $d -Parent }
  while ($true) {
    if (Test-Path -LiteralPath (Join-Path $d ".git")) { return $d }
    if (Test-Path -LiteralPath (Join-Path $d "docker-compose.yml")) { return $d }
    $p = Split-Path $d -Parent
    if (-not $p -or $p -eq $d) { break }
    $d = $p
  }
  throw "Repo root not found from: $from"
}

function ExtractContainerIdStrict([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return "" }
  $lines = $text -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
  foreach ($ln in $lines) { if ($ln -match '^[0-9a-f]{12,64}$') { return $ln } }
  return ""
}

function GetProp([object]$obj, [string]$name) {
  if ($null -eq $obj) { return $null }
  if ($obj.PSObject.Properties.Name -contains $name) { return $obj.$name }
  return $null
}
function GetStr([object]$obj, [string]$name) {
  $v = GetProp $obj $name
  if ($null -eq $v) { return "" }
  return ([string]$v).Trim()
}

function WriteLog([string]$Path, [string]$Text) {
  $Text | Add-Content -LiteralPath $Path -Encoding UTF8
}

$null = Get-Command docker -ErrorAction Stop
$RepoRoot = FindRepoRoot $PSScriptRoot

# ---- pick backup ----
if ([string]::IsNullOrWhiteSpace($BackupPath)) {
  $broot = Join-Path $RepoRoot "ops\_backups"
  ThrowIf (-not (Test-Path -LiteralPath $broot)) "Backup root not found: $broot"
  $cand = Get-ChildItem -LiteralPath $broot -Directory | Sort-Object Name -Descending | Select-Object -First 1
  ThrowIf ($null -eq $cand) "No backups found in: $broot"
  $BackupPath = $cand.FullName
}
$BackupPath = (Resolve-Path -LiteralPath $BackupPath).Path
$manifestPath = Join-Path $BackupPath "manifest.json"
ThrowIf (-not (Test-Path -LiteralPath $manifestPath)) "manifest.json not found: $manifestPath"

$man = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json -Depth 80

# ---- derive db/user (supports multiple schemas) ----
$dbName = GetStr $man "db_name"
if ([string]::IsNullOrWhiteSpace($dbName)) { $dbName = GetStr (GetProp $man "postgres") "db_name" }
if ([string]::IsNullOrWhiteSpace($dbName)) { $dbName = GetStr (GetProp $man "db") "name" }
if ([string]::IsNullOrWhiteSpace($dbName)) { $dbName = GetStr (GetProp $man "db") "db" }
if ([string]::IsNullOrWhiteSpace($dbName)) { $dbName = "postgres" }

$dbUser = GetStr $man "pg_user"
if ([string]::IsNullOrWhiteSpace($dbUser)) { $dbUser = GetStr (GetProp $man "postgres") "user" }
if ([string]::IsNullOrWhiteSpace($dbUser)) { $dbUser = GetStr (GetProp $man "db") "user" }
if ([string]::IsNullOrWhiteSpace($dbUser)) { $dbUser = "postgres" }

# ---- drill compose file ----
if ([string]::IsNullOrWhiteSpace($DrillComposeFile)) {
  $DrillComposeFile = Join-Path $RepoRoot "ops\drill\docker-compose.pg-drill.yml"
}
ThrowIf (-not (Test-Path -LiteralPath $DrillComposeFile)) "DrillComposeFile not found: $DrillComposeFile"
$DrillComposeFile = (Resolve-Path -LiteralPath $DrillComposeFile).Path

# ---- evidence ----
$rid = "restore_drill_" + (Get-Date -Format "yyyyMMdd_HHmmss")
$ev  = Join-Path $RepoRoot ("ops\_local\evidence\{0}" -f $rid)
EnsureDir $ev

$log    = Join-Path $ev "drill.log"
$chk    = Join-Path $ev "db_checks.txt"
$sum    = Join-Path $ev "summary.json"
$digest = Join-Path $ev "digest.sha256"

"ts=$(NowIso) restore-drill start" | Set-Content -LiteralPath $log -Encoding UTF8
WriteLog $log ("script_version=" + $SCRIPT_VERSION)
WriteLog $log ("backup=" + $BackupPath)
WriteLog $log ("manifest=" + $manifestPath)
WriteLog $log ("project=" + $DrillProjectName)
WriteLog $log ("drill_compose=" + $DrillComposeFile)
WriteLog $log ("pg_service=" + $PgService)
WriteLog $log ("db_name=" + $dbName)
WriteLog $log ("db_user=" + $dbUser)
WriteLog $log ""

# FIX P0: do NOT use param name `$args` (reserved automatic var)
function Compose([string[]]$ComposeArgs) {
  if (-not $ComposeArgs -or $ComposeArgs.Count -eq 0) {
    throw "BUG: Compose called with empty args (would print docker compose help)."
  }

  $argv = @("compose","--ansi","never","-f",$DrillComposeFile,"-p",$DrillProjectName) + $ComposeArgs
  $out  = & docker @argv 2>&1
  $code = $LASTEXITCODE
  $txt  = (($out | Out-String).TrimEnd())

  WriteLog $log ("argv=" + ("docker " + ($argv -join " ")))
  WriteLog $log ("exit=" + $code)
  if ($txt) { WriteLog $log $txt }
  WriteLog $log ""

  return [pscustomobject]@{ code=[int]$code; out=$txt }
}

function DockerExecSh([string]$cid, [string]$inner) {
  $out = & docker exec -i $cid sh -lc $inner 2>&1
  $code = $LASTEXITCODE
  return [pscustomobject]@{ code=[int]$code; out=(($out|Out-String).TrimEnd()); inner=$inner }
}

function MakeDigest([string]$dir, [string]$outPath) {
  $files = Get-ChildItem -LiteralPath $dir -File | Sort-Object Name
  $lines = New-Object System.Collections.Generic.List[string]
  foreach ($f in $files) {
    $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $f.FullName).Hash
    $lines.Add(("{0}  {1}" -f $h, $f.Name)) | Out-Null
  }
  ($lines -join "`r`n") + "`r`n" | Set-Content -LiteralPath $outPath -Encoding utf8NoBOM
}

$ok = $false

# preserve current env vars to avoid polluting session
$prevEnv = @{
  FF_DRILL_PG_USER     = $env:FF_DRILL_PG_USER
  FF_DRILL_PG_DB       = $env:FF_DRILL_PG_DB
  FF_DRILL_PG_PASSWORD = $env:FF_DRILL_PG_PASSWORD
}

try {
  # inject db/user for initdb
  $env:FF_DRILL_PG_USER = $dbUser
  $env:FF_DRILL_PG_DB   = $dbName
  if ([string]::IsNullOrWhiteSpace($env:FF_DRILL_PG_PASSWORD)) { $env:FF_DRILL_PG_PASSWORD = "drill" }

  # preflight: list services in drill compose (helps diagnose yaml errors)
  $null = Compose @("config","--services")

  # up postgres
  $rUp = Compose @("up","-d",$PgService)
  if ($rUp.code -ne 0) { throw "compose up failed (exit=$($rUp.code)). See: $log" }

  # ps -a for evidence
  $null = Compose @("ps","-a")

  # get cid
  $psq = Compose @("ps","-a","-q",$PgService)
  $cid = ExtractContainerIdStrict $psq.out
  if ([string]::IsNullOrWhiteSpace($cid)) {
    $null = Compose @("logs","--no-color","--tail","200",$PgService)
    throw "drill postgres container id not found. See: $log"
  }
  WriteLog $log ("drill_pg_cid=" + $cid)
  WriteLog $log ""

  # wait ready
  $ready = $false
  $deadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
  while ((Get-Date) -lt $deadline) {
    $r = DockerExecSh $cid 'pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"'
    if ($r.code -eq 0 -and $r.out -match "accepting connections") { $ready = $true; break }
    Start-Sleep -Seconds $ReadyPollSec
  }
  if (-not $ready) {
    $null = Compose @("logs","--no-color","--tail","200",$PgService)
    throw "postgres not ready (timeout=${ReadyTimeoutSec}s). See: $log"
  }

  # call restore into drill project using drill compose only
  $restoreScript = Join-Path $RepoRoot "scripts\pwsh\ff-restore.ps1"
  ThrowIf (-not (Test-Path -LiteralPath $restoreScript)) "restore script not found: $restoreScript"

  & pwsh -NoProfile -File $restoreScript -BackupPath $BackupPath -ComposeFiles @($DrillComposeFile) -ProjectName $DrillProjectName -PgService $PgService -EvidenceDir $ev 2>&1 |
    Tee-Object -FilePath $log -Append | Out-Host

  $rc = $LASTEXITCODE
  if ($rc -ne 0) { throw "ff-restore failed (exit=$rc). See: $log" }

  # basic checks
  $checks = @()
  $checks += "ts=$(NowIso)"
  $checks += "db=$dbName user=$dbUser"
  $checks += ""

  $r1 = DockerExecSh $cid ('psql -U "{0}" -d "{1}" -Atc "SELECT count(*) FROM information_schema.schemata WHERE schema_name NOT IN (''pg_catalog'',''information_schema'');"' -f $dbUser, $dbName)
  $checks += "non_system_schema_count:"
  $checks += $r1.out
  $checks += ""

  $r2 = DockerExecSh $cid ('psql -U "{0}" -d "{1}" -Atc "SELECT count(*) FROM pg_class WHERE relkind IN (''r'',''m'');"' -f $dbUser, $dbName)
  $checks += "table_plus_matview_count:"
  $checks += $r2.out
  $checks += ""

  $checks -join "`r`n" | Set-Content -LiteralPath $chk -Encoding UTF8

  $ok = $true

  # summary + digest
  $summary = [ordered]@{
    ok = $true
    ts = (NowIso)
    script = [ordered]@{ name="ff-restore-drill.ps1"; version=$SCRIPT_VERSION }
    backup_path = $BackupPath
    manifest = $manifestPath
    drill = [ordered]@{
      project = $DrillProjectName
      compose = $DrillComposeFile
      service = $PgService
      cid = $cid
    }
    db = [ordered]@{ name=$dbName; user=$dbUser }
    evidence_dir = $ev
  }
  ($summary | ConvertTo-Json -Depth 40) | Set-Content -LiteralPath $sum -Encoding utf8NoBOM
  MakeDigest -dir $ev -outPath $digest

  Write-Host ("RESTORE-DRILL OK ✅  evidence: {0}" -f $ev) -ForegroundColor Green
  Write-Output ("evidenceDir: " + $ev)
}
catch {
  WriteLog $log ("ERROR: " + $_.Exception.Message)

  $summary = [ordered]@{
    ok = $false
    ts = (NowIso)
    script = [ordered]@{ name="ff-restore-drill.ps1"; version=$SCRIPT_VERSION }
    backup_path = $BackupPath
    manifest = $manifestPath
    evidence_dir = $ev
    error = $_.Exception.Message
  }
  try { ($summary | ConvertTo-Json -Depth 40) | Set-Content -LiteralPath $sum -Encoding utf8NoBOM } catch {}
  try { MakeDigest -dir $ev -outPath $digest } catch {}

  Write-Host ("RESTORE-DRILL FAIL ❌  evidence: {0}" -f $ev) -ForegroundColor Red

  if (-not $KeepOnFail) {
    try { $null = Compose @("down","-v","--remove-orphans") } catch {}
  }
  throw
}
finally {
  if ($ok -and -not $KeepOnSuccess) {
    try { $null = Compose @("down","-v","--remove-orphans") } catch {}
  }

  # restore env
  foreach ($k in $prevEnv.Keys) {
    $v = $prevEnv[$k]
    if ($null -eq $v) {
      try { Remove-Item -LiteralPath ("Env:{0}" -f $k) -ErrorAction SilentlyContinue } catch {}
    } else {
      Set-Item -LiteralPath ("Env:{0}" -f $k) -Value $v
    }
  }
}
