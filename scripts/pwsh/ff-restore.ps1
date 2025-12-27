#requires -Version 7.0
<#
FoxProFlow RUN • Restore (Postgres) from backup folder ops/_backups/<stamp>
file: scripts/pwsh/ff-restore.ps1

Supports different manifest schemas:
  - legacy: db_name, pg_user, dump file pg_<db>.dump
  - newer: postgres.db_name / postgres.user OR db.name / db.user
Also supports dump names:
  - db.dump
  - pg_*.dump

Evidence (in EvidenceDir):
  - restore.log
  - summary.restore.json
  - digest.restore.sha256

Created by: Архитектор Яцков Евгений Анатольевич
Lane: A-RUN only
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [Parameter(Mandatory=$true)]
  [string]$BackupPath,

  [string]$ComposeFile = "",
  [string[]]$ComposeFiles = @(),

  [string]$ProjectName = "",

  [string]$PgService = "postgres",

  [string]$EvidenceDir = "",

  [switch]$NoGlobals
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$SCRIPT_VERSION = "2025-12-27.v3"

function NowIso() { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function EnsureDir([string]$p) { if (-not (Test-Path -LiteralPath $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }

function WriteLog([string]$Path, [string]$Text) {
  $Text | Add-Content -LiteralPath $Path -Encoding UTF8
}

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

function ResolveComposePaths([string]$repoRoot, [string]$composeFile, [string[]]$composeFiles) {
  $paths = New-Object System.Collections.Generic.List[string]

  if ($composeFiles -and $composeFiles.Count -gt 0) {
    foreach ($p in $composeFiles) { if ($p) { $paths.Add($p) | Out-Null } }
  } else {
    if ([string]::IsNullOrWhiteSpace($composeFile)) { $composeFile = Join-Path $repoRoot "docker-compose.yml" }
    $paths.Add($composeFile) | Out-Null
  }

  $resolved = New-Object System.Collections.Generic.List[string]
  foreach ($p in $paths) {
    $pp = $p
    if (-not [System.IO.Path]::IsPathRooted($pp)) { $pp = Join-Path $repoRoot $pp }
    if (-not (Test-Path -LiteralPath $pp)) { throw "Compose file not found: $pp" }
    $resolved.Add((Resolve-Path -LiteralPath $pp).Path) | Out-Null
  }

  return ,$resolved.ToArray()
}

function ExtractContainerIdStrict([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return "" }
  $lines = $text -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
  foreach ($ln in $lines) { if ($ln -match '^[0-9a-f]{12,64}$') { return $ln } }
  return ""
}

# IMPORTANT: do NOT use param name `$args` here (reserved automatic var)
function Compose([string[]]$composePaths, [string]$projectName, [string[]]$ComposeArgs, [string]$logPath) {
  if (-not $ComposeArgs -or $ComposeArgs.Count -eq 0) {
    throw "BUG: Compose called with empty args (would print docker compose help)."
  }

  $argv = New-Object System.Collections.Generic.List[string]
  $argv.Add("compose") | Out-Null
  $argv.Add("--ansi") | Out-Null
  $argv.Add("never") | Out-Null

  foreach ($cf in $composePaths) { $argv.Add("-f") | Out-Null; $argv.Add($cf) | Out-Null }

  if (-not [string]::IsNullOrWhiteSpace($projectName)) { $argv.Add("-p") | Out-Null; $argv.Add($projectName) | Out-Null }

  foreach ($a in $ComposeArgs) { $argv.Add($a) | Out-Null }

  $out = & docker @($argv.ToArray()) 2>&1
  $code = $LASTEXITCODE
  $txt = (($out | Out-String).TrimEnd())

  if ($logPath) {
    WriteLog $logPath ("argv=" + ("docker " + ($argv.ToArray() -join " ")))
    WriteLog $logPath ("exit=" + $code)
    if ($txt) { WriteLog $logPath $txt }
    WriteLog $logPath ""
  }

  return [pscustomobject]@{ code=[int]$code; out=$txt }
}

function DockerExecSh([string]$cid, [string]$inner) {
  $out = & docker exec -i $cid sh -lc $inner 2>&1
  $code = $LASTEXITCODE
  return [pscustomobject]@{ code=[int]$code; out=(($out|Out-String).TrimEnd()); inner=$inner }
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

function FindCidByLabels([string]$projectName, [string]$serviceName) {
  if ([string]::IsNullOrWhiteSpace($projectName)) { return "" }
  $out = & docker ps -aq `
    --filter "label=com.docker.compose.project=$projectName" `
    --filter "label=com.docker.compose.service=$serviceName" 2>&1
  if ($LASTEXITCODE -ne 0) { return "" }
  $txt = (($out | Out-String).Trim())
  if ([string]::IsNullOrWhiteSpace($txt)) { return "" }
  $first = ($txt -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
  if ($first -match '^[0-9a-f]{12,64}$') { return $first.Trim() }
  return ""
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

# ---- MAIN ----
$null = Get-Command docker -ErrorAction Stop
$RepoRoot = FindRepoRoot $PSScriptRoot

$BackupPath = (Resolve-Path -LiteralPath $BackupPath).Path
if (-not (Test-Path -LiteralPath $BackupPath -PathType Container)) { throw "BackupPath not found: $BackupPath" }

$manifestPath = Join-Path $BackupPath "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath)) { throw "manifest.json not found in: $BackupPath" }

$man = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json -Depth 80

# ProjectName fallback
if ([string]::IsNullOrWhiteSpace($ProjectName)) {
  if ($env:FF_COMPOSE_PROJECT) { $ProjectName = $env:FF_COMPOSE_PROJECT }
  elseif ($env:COMPOSE_PROJECT_NAME) { $ProjectName = $env:COMPOSE_PROJECT_NAME }
  else {
    $ProjectName = GetStr $man "project_name"
    if ([string]::IsNullOrWhiteSpace($ProjectName)) {
      $ProjectName = GetStr (GetProp $man "compose") "project_name"
    }
  }
}

# Evidence dir
if ([string]::IsNullOrWhiteSpace($EvidenceDir)) {
  $rid = "restore_" + (Get-Date -Format "yyyyMMdd_HHmmss")
  $EvidenceDir = Join-Path $RepoRoot ("ops\_local\evidence\{0}" -f $rid)
}
EnsureDir $EvidenceDir

$logPath = Join-Path $EvidenceDir "restore.log"
$sumPath = Join-Path $EvidenceDir "summary.restore.json"
$digPath = Join-Path $EvidenceDir "digest.restore.sha256"

"ts=$(NowIso) restore start" | Set-Content -LiteralPath $logPath -Encoding UTF8
WriteLog $logPath ("script_version=" + $SCRIPT_VERSION)
WriteLog $logPath ("backup_path=" + $BackupPath)
WriteLog $logPath ("manifest=" + $manifestPath)
WriteLog $logPath ("project=" + $ProjectName)
WriteLog $logPath ("pg_service=" + $PgService)
WriteLog $logPath ""

# derive db/user (multiple schemas)
$dbName = GetStr $man "db_name"
if ([string]::IsNullOrWhiteSpace($dbName)) { $dbName = GetStr (GetProp $man "postgres") "db_name" }
if ([string]::IsNullOrWhiteSpace($dbName)) { $dbName = GetStr (GetProp $man "db") "name" }
if ([string]::IsNullOrWhiteSpace($dbName)) { $dbName = "postgres" }

$dbUser = GetStr $man "pg_user"
if ([string]::IsNullOrWhiteSpace($dbUser)) { $dbUser = GetStr (GetProp $man "postgres") "user" }
if ([string]::IsNullOrWhiteSpace($dbUser)) { $dbUser = GetStr (GetProp $man "db") "user" }
if ([string]::IsNullOrWhiteSpace($dbUser)) { $dbUser = "postgres" }

WriteLog $logPath ("db_name=" + $dbName)
WriteLog $logPath ("db_user=" + $dbUser)
WriteLog $logPath ""

# locate dump file
$dumpCandidates = @()
$maybe = Join-Path $BackupPath "db.dump"
if (Test-Path -LiteralPath $maybe) { $dumpCandidates += (Get-Item -LiteralPath $maybe) }
$dumpCandidates += Get-ChildItem -LiteralPath $BackupPath -File -Filter "pg_*.dump" -ErrorAction SilentlyContinue
if ($dumpCandidates.Count -eq 0) { throw "No dump found in $BackupPath (expected db.dump or pg_*.dump)" }
$dumpFile = ($dumpCandidates | Sort-Object Length -Descending | Select-Object -First 1).FullName

# locate globals
$globalsFile = $null
if (-not $NoGlobals) {
  foreach ($n in @("pg_globals.sql","globals.sql")) {
    $p = Join-Path $BackupPath $n
    if (Test-Path -LiteralPath $p) { $globalsFile = $p; break }
  }
}

WriteLog $logPath ("dump_file=" + $dumpFile)
WriteLog $logPath ("globals_file=" + $(if ($globalsFile) { $globalsFile } else { "<none>" }))
WriteLog $logPath ""

# resolve compose paths
$composePaths = ResolveComposePaths -repoRoot $RepoRoot -composeFile $ComposeFile -composeFiles $ComposeFiles
WriteLog $logPath ("compose_files=" + ($composePaths -join "; "))
WriteLog $logPath ""

# preflight
$null = Compose -composePaths $composePaths -projectName $ProjectName -ComposeArgs @("config","--services") -logPath $logPath
$null = Compose -composePaths $composePaths -projectName $ProjectName -ComposeArgs @("ps","-a") -logPath $logPath

# find postgres container id
$psq = Compose -composePaths $composePaths -projectName $ProjectName -ComposeArgs @("ps","-a","-q",$PgService) -logPath $logPath
if ($psq.code -ne 0) { throw "docker compose ps failed (exit=$($psq.code)). See: $logPath" }

$cid = ExtractContainerIdStrict $psq.out
if ([string]::IsNullOrWhiteSpace($cid)) {
  $cid = FindCidByLabels -projectName $ProjectName -serviceName $PgService
}

if ([string]::IsNullOrWhiteSpace($cid)) {
  $null = Compose -composePaths $composePaths -projectName $ProjectName -ComposeArgs @("logs","--no-color","--tail","200",$PgService) -logPath $logPath
  throw "Postgres container id not found for service '$PgService'. See: $logPath"
}

WriteLog $logPath ("pg_cid=" + $cid)
WriteLog $logPath ""

# copy files into container
$dumpIn = "/tmp/ff_restore.dump"
$globIn = "/tmp/ff_restore_globals.sql"

(& docker cp $dumpFile ("{0}:{1}" -f $cid, $dumpIn) 2>&1 | Out-String).TrimEnd() | ForEach-Object { if ($_){ WriteLog $logPath $_ } }
if ($LASTEXITCODE -ne 0) { throw "docker cp dump failed. See: $logPath" }
WriteLog $logPath ""

if ($globalsFile) {
  (& docker cp $globalsFile ("{0}:{1}" -f $cid, $globIn) 2>&1 | Out-String).TrimEnd() | ForEach-Object { if ($_){ WriteLog $logPath $_ } }
  if ($LASTEXITCODE -ne 0) { WriteLog $logPath "WARN: docker cp globals failed (continuing)" }
  WriteLog $logPath ""
}

# terminate connections (best-effort)
try {
  $sqlTerm = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$dbName' AND pid <> pg_backend_pid();"
  $cmdTerm = ('psql -U "{0}" -d "{1}" -Atc "{2}"' -f $dbUser, $dbName, $sqlTerm)
  $rTerm = DockerExecSh $cid $cmdTerm
  WriteLog $logPath ("term_exit=" + $rTerm.code)
  if ($rTerm.out) { WriteLog $logPath $rTerm.out }
  WriteLog $logPath ""
} catch {}

# reset public schema (hard gate)
$cmdReset = ('psql -v ON_ERROR_STOP=1 -U "{0}" -d "{1}" -c ''DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;''' -f $dbUser, $dbName)
$rReset = DockerExecSh $cid $cmdReset
WriteLog $logPath ("reset_exit=" + $rReset.code)
if ($rReset.out) { WriteLog $logPath $rReset.out }
WriteLog $logPath ""
if ($rReset.code -ne 0) { throw "reset public schema failed. See: $logPath" }

# globals (best-effort)
if ($globalsFile) {
  try {
    $cmdGlob = ('psql -U "{0}" -d "{1}" -f "{2}"' -f $dbUser, $dbName, $globIn)
    $rGlob = DockerExecSh $cid $cmdGlob
    WriteLog $logPath ("globals_exit=" + $rGlob.code)
    if ($rGlob.out) { WriteLog $logPath $rGlob.out }
    WriteLog $logPath ""
  } catch {}
}

# restore dump (hard gate)
$cmdRestore = ('pg_restore --no-owner --no-privileges --if-exists --clean -U "{0}" -d "{1}" "{2}"' -f $dbUser, $dbName, $dumpIn)
$rRestore = DockerExecSh $cid $cmdRestore
WriteLog $logPath ("restore_exit=" + $rRestore.code)
if ($rRestore.out) { WriteLog $logPath $rRestore.out }
WriteLog $logPath ""
if ($rRestore.code -ne 0) { throw "pg_restore failed. See: $logPath" }

# cleanup inside container (best-effort)
try { DockerExecSh $cid ('rm -f "{0}" "{1}"' -f $dumpIn, $globIn) | Out-Null } catch {}

# summary + digest
$summary = [ordered]@{
  ok = $true
  ts = (NowIso)
  script = [ordered]@{ name="ff-restore.ps1"; version=$SCRIPT_VERSION }
  backup_path = $BackupPath
  manifest = $manifestPath
  dump_file = $dumpFile
  globals_file = $globalsFile
  compose_files = $composePaths
  project = $ProjectName
  pg_service = $PgService
  pg_cid = $cid
  db = [ordered]@{ name=$dbName; user=$dbUser }
  evidence_dir = $EvidenceDir
}
($summary | ConvertTo-Json -Depth 50) | Set-Content -LiteralPath $sumPath -Encoding utf8NoBOM
MakeDigest -dir $EvidenceDir -outPath $digPath

Write-Host ("RESTORE OK ✅  evidence: {0}" -f $EvidenceDir) -ForegroundColor Green
Write-Output ("evidenceDir: " + $EvidenceDir)
exit 0
