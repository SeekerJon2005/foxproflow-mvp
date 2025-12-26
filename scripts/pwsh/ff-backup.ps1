#requires -Version 7.0
<#
FoxProFlow RUN • Backup helper
file: scripts/pwsh/ff-backup.ps1

Creates backup under ops/_backups/<stamp>:
  - manifest.json
  - snapshot_docker-compose.yml
  - snapshot_docker-compose.env.dynamic.yml (if exists)
  - snapshot_.env (if exists)
  - pg_<db>.dump (custom format)
  - pg_globals.sql

Prints: outDir: <ABS_PATH>   (for ff-release-m0.ps1 parser)

Lane: A-RUN only.

Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$BackupDir = "",
  [string]$ComposeFile = "",
  [string]$ProjectName = $(if ($env:FF_COMPOSE_PROJECT) { $env:FF_COMPOSE_PROJECT } elseif ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "foxproflow-mvp20" }),

  [string]$PgService = "postgres",
  [string]$PgUser = "admin",
  [string]$DbName = "foxproflow",

  [switch]$NoCleanupTmp
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# Silence docker compose warnings about missing pgAdmin env vars (local-only; no compose/env changes)
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_EMAIL))    { $env:PGADMIN_EMAIL    = "disabled@local" }
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_PASSWORD)) { $env:PGADMIN_PASSWORD = "disabled" }

function Now-Stamp { (Get-Date).ToString("yyyyMMdd-HHmmss") }
function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function Repo-Root { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }

function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function Set-Utf8([string]$Path, [string]$Text) { $d=Split-Path $Path -Parent; if($d){Ensure-Dir $d}; $Text | Set-Content -LiteralPath $Path -Encoding utf8NoBOM }

function Resolve-ComposeFile([string]$repoRoot, [string]$composeFile) {
  if ([string]::IsNullOrWhiteSpace($composeFile)) { $composeFile = Join-Path $repoRoot "docker-compose.yml" }
  if (-not (Test-Path -LiteralPath $composeFile)) { throw "ComposeFile not found: $composeFile" }
  return (Resolve-Path -LiteralPath $composeFile).Path
}

function Dc([string]$composeFile, [string]$projectName, [string[]]$composeArgs) {
  $argv = New-Object System.Collections.Generic.List[string]
  $argv.Add("compose") | Out-Null
  $argv.Add("--ansi") | Out-Null
  $argv.Add("never") | Out-Null
  $argv.Add("-f") | Out-Null
  $argv.Add($composeFile) | Out-Null
  if ($projectName) { $argv.Add("-p") | Out-Null; $argv.Add($projectName) | Out-Null }
  foreach ($a in $composeArgs) { $argv.Add($a) | Out-Null }

  $out = & docker @($argv.ToArray()) 2>&1
  $code = $LASTEXITCODE

  return [pscustomobject]@{
    code = [int]$code
    out  = ($out | Out-String)
    argv = ("docker " + ($argv.ToArray() -join " "))
  }
}

function Extract-FirstContainerId([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return "" }
  # docker container id is hex 12..64 chars
  $m = [regex]::Match($text, '(?im)\b[0-9a-f]{12,64}\b')
  if ($m.Success) { return $m.Value.Trim() }
  return ""
}

$repoRoot = Repo-Root
$ComposeFile = Resolve-ComposeFile -repoRoot $repoRoot -composeFile $ComposeFile

if ([string]::IsNullOrWhiteSpace($ProjectName)) {
  throw "ProjectName is empty. Provide -ProjectName or set FF_COMPOSE_PROJECT/COMPOSE_PROJECT_NAME."
}

if ([string]::IsNullOrWhiteSpace($BackupDir)) {
  $BackupDir = Join-Path $repoRoot "ops\_backups"
}
Ensure-Dir $BackupDir

$outDir = Join-Path $BackupDir (Now-Stamp)
Ensure-Dir $outDir
$outDirAbs = (Resolve-Path -LiteralPath $outDir).Path

# snapshots
Copy-Item -Force -LiteralPath $ComposeFile -Destination (Join-Path $outDir "snapshot_docker-compose.yml")

$dyn = Join-Path $repoRoot "docker-compose.env.dynamic.yml"
if (Test-Path -LiteralPath $dyn) {
  Copy-Item -Force -LiteralPath $dyn -Destination (Join-Path $outDir "snapshot_docker-compose.env.dynamic.yml")
}

$envFile = Join-Path $repoRoot ".env"
if (Test-Path -LiteralPath $envFile) {
  Copy-Item -Force -LiteralPath $envFile -Destination (Join-Path $outDir "snapshot_.env")
}

# resolve container id (robust against warnings in stderr)
$ps = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("ps","-q",$PgService)
if ($ps.code -ne 0) { throw "docker compose ps -q $PgService failed (exit=$($ps.code)). argv=$($ps.argv)`n$($ps.out)" }

Set-Utf8 (Join-Path $outDir "compose_ps_q.log") ("ts={0}`nargv={1}`nexit_code={2}`n`n{3}" -f (Now-Iso), $ps.argv, $ps.code, $ps.out)

$cid = Extract-FirstContainerId $ps.out
if ([string]::IsNullOrWhiteSpace($cid)) {
  throw "Cannot extract container id for service '$PgService' from output. See compose_ps_q.log in $outDirAbs"
}

$tmpDump = "/tmp/pg_${DbName}.dump"
$tmpGlobals = "/tmp/pg_globals.sql"

# dump inside container (binary-safe)
$cmd1 = "pg_dump -U $PgUser -d $DbName -Fc -f $tmpDump"
$out1 = & docker exec $cid sh -lc $cmd1 2>&1
$code1 = $LASTEXITCODE
Set-Utf8 (Join-Path $outDir "pg_dump_exec.log") ("ts={0}`ncid={1}`ncmd={2}`nexit_code={3}`n`n{4}" -f (Now-Iso), $cid, $cmd1, $code1, ($out1 | Out-String))
if ($code1 -ne 0) { throw "pg_dump failed (exit=$code1). See pg_dump_exec.log in $outDirAbs" }

$cmd2 = "pg_dumpall -U $PgUser --globals-only -f $tmpGlobals"
$out2 = & docker exec $cid sh -lc $cmd2 2>&1
$code2 = $LASTEXITCODE
Set-Utf8 (Join-Path $outDir "pg_globals_exec.log") ("ts={0}`ncid={1}`ncmd={2}`nexit_code={3}`n`n{4}" -f (Now-Iso), $cid, $cmd2, $code2, ($out2 | Out-String))
if ($code2 -ne 0) { throw "pg_dumpall --globals-only failed (exit=$code2). See pg_globals_exec.log in $outDirAbs" }

# copy to host
$dstDump = Join-Path $outDir ("pg_{0}.dump" -f $DbName)
$dstGlobals = Join-Path $outDir "pg_globals.sql"

$srcDump = "${cid}:${tmpDump}"
$srcGlobals = "${cid}:${tmpGlobals}"

$out3 = & docker cp $srcDump $dstDump 2>&1
$code3 = $LASTEXITCODE
Set-Utf8 (Join-Path $outDir "docker_cp_dump.log") ("ts={0}`nsrc={1}`ndst={2}`nexit_code={3}`n`n{4}" -f (Now-Iso), $srcDump, $dstDump, $code3, ($out3 | Out-String))
if ($code3 -ne 0) { throw "docker cp dump failed (exit=$code3). See docker_cp_dump.log in $outDirAbs" }

$out4 = & docker cp $srcGlobals $dstGlobals 2>&1
$code4 = $LASTEXITCODE
Set-Utf8 (Join-Path $outDir "docker_cp_globals.log") ("ts={0}`nsrc={1}`ndst={2}`nexit_code={3}`n`n{4}" -f (Now-Iso), $srcGlobals, $dstGlobals, $code4, ($out4 | Out-String))
if ($code4 -ne 0) { throw "docker cp globals failed (exit=$code4). See docker_cp_globals.log in $outDirAbs" }

if (-not $NoCleanupTmp) {
  try { & docker exec $cid sh -lc ("rm -f {0} {1}" -f $tmpDump, $tmpGlobals) 2>$null | Out-Null } catch {}
}

function FileMeta([string]$p) {
  if (-not (Test-Path -LiteralPath $p)) { return $null }
  $fi = Get-Item -LiteralPath $p
  return [pscustomobject]@{ name=$fi.Name; bytes=[int64]$fi.Length; ts=$fi.LastWriteTime.ToString("o") }
}

$files = @()
$files += FileMeta (Join-Path $outDir "snapshot_docker-compose.yml")
$files += FileMeta (Join-Path $outDir "snapshot_docker-compose.env.dynamic.yml")
$files += FileMeta (Join-Path $outDir "snapshot_.env")
$files += FileMeta $dstDump
$files += FileMeta $dstGlobals
$files = @($files | Where-Object { $_ -ne $null })

$manifest = [pscustomobject]@{
  ts = Now-Iso
  out_dir = $outDirAbs
  compose_file = $ComposeFile
  project_name = $ProjectName
  pg_service = $PgService
  pg_container_id = $cid
  pg_user = $PgUser
  db_name = $DbName
  files = $files
}

Set-Utf8 (Join-Path $outDir "manifest.json") (($manifest | ConvertTo-Json -Depth 40))

# IMPORTANT for ff-release-m0.ps1 parser:
Write-Output ("outDir: " + $outDirAbs)
