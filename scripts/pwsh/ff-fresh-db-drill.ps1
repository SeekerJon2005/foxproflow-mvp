#requires -Version 7.0
<#
FoxProFlow RUN • Fresh DB Drill (bootstrap + verify + drop)
file: scripts/pwsh/ff-fresh-db-drill.ps1

Procedure:
  1) create temp DB
  2) apply bootstrap SQL via psql inside postgres container (supports \i fixpacks/*)
  3) run verify suite script (host-side)
  4) drop temp DB (unless KeepDb / KeepDbOnFail)

Outputs:
  - exit code 0 on PASS
  - non-zero on FAIL
  - evidence logs in ops/_local/evidence/<rid>/fresh_db_drill/
#>

param(
  [Parameter(Mandatory = $true)]
  [string] $BootstrapSqlPath,

  [Parameter(Mandatory = $true)]
  [string] $SuiteFile,

  [string] $PgService = "postgres",
  [string] $PgUser = $(if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "admin" }),
  [string] $AdminDb = "postgres",
  [string] $DbPrefix = "ff_tmp_",

  # optional; auto-detect if empty
  [string] $VerifyScriptPath = "",

  [string] $EvidenceRoot = "",

  # where to stage SQL tree inside postgres container
  [string] $SqlStageBase = "/tmp/ffsql_stage",

  [switch] $KeepDb,
  [switch] $KeepDbOnFail
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Write-Log([string]$Msg) {
  $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  "[${ts}] $Msg"
}

function Resolve-VerifyScriptPath {
  param(
    [string] $Provided,
    [string] $RepoRoot
  )

  if ($Provided) {
    if (Test-Path -LiteralPath $Provided) {
      return (Resolve-Path -LiteralPath $Provided).Path
    }
    throw "VerifyScriptPath provided but not found: $Provided"
  }

  $wtParent = Split-Path -Parent $RepoRoot

  $candidates = @(
    (Join-Path $RepoRoot  "scripts\sql\verify\run_verify_suite.ps1"),
    (Join-Path $RepoRoot  "scripts\sql\verify\run_verify_suite_v2.ps1"),
    (Join-Path $wtParent  "C-sql\scripts\sql\verify\run_verify_suite.ps1"),
    (Join-Path $wtParent  "C-sql\scripts\sql\verify\run_verify_suite_v2.ps1"),
    (Join-Path $wtParent  "scripts\sql\verify\run_verify_suite.ps1"),
    (Join-Path $wtParent  "scripts\sql\verify\run_verify_suite_v2.ps1")
  )

  foreach ($p in $candidates) {
    if (Test-Path -LiteralPath $p) {
      return (Resolve-Path -LiteralPath $p).Path
    }
  }

  throw ("Verify script not found. Tried: " + ($candidates -join "; "))
}

function Get-PgContainerId {
  $cid = (docker compose ps -q $PgService 2>$null | Select-Object -First 1)
  if (-not $cid) { throw "Cannot resolve container id for service '$PgService' (docker compose ps -q returned empty)" }
  return $cid.Trim()
}

function Invoke-ComposePsql {
  param(
    [Parameter(Mandatory = $true)]
    [string] $DatabaseName,

    [Parameter(Mandatory = $true)]
    [string] $Sql
  )

  docker compose exec -T $PgService psql -U $PgUser -d $DatabaseName -v ON_ERROR_STOP=1 -c $Sql | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "psql failed (db=$DatabaseName) exit=$LASTEXITCODE" }
}

function Invoke-ComposePsqlFileWithStage {
  param(
    [Parameter(Mandatory = $true)]
    [string] $DatabaseName,

    [Parameter(Mandatory = $true)]
    [string] $FilePath,

    [Parameter(Mandatory = $true)]
    [string] $StageDir
  )

  $fp = (Resolve-Path -LiteralPath $FilePath).Path
  if (-not (Test-Path -LiteralPath $fp)) { throw "Bootstrap SQL not found: $fp" }

  $sqlRootHost = Split-Path -Parent $fp
  $baseName = Split-Path -Leaf $fp

  $cid = Get-PgContainerId

  # Prepare staging dir
  docker compose exec -T $PgService sh -lc "rm -rf '$StageDir' && mkdir -p '$StageDir'" | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "failed to prepare stage dir in container: $StageDir" }

  # Copy whole SQL root directory (so \i fixpacks/... works)
  # It will appear as $StageDir/sql
  $destSqlDir = "$StageDir/sql"
  docker cp "$sqlRootHost" "${cid}:${destSqlDir}" | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "docker cp failed for sql root: $sqlRootHost -> $destSqlDir" }

  # Run from that directory so relative includes resolve
  $cmd = "cd '$destSqlDir' && psql -U '$PgUser' -d '$DatabaseName' -v ON_ERROR_STOP=1 -f '$baseName'"
  docker compose exec -T $PgService sh -lc $cmd | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "psql -f failed (db=$DatabaseName) exit=$LASTEXITCODE" }

  # Cleanup stage dir (always)
  docker compose exec -T $PgService sh -lc "rm -rf '$StageDir'" | Out-Host
}

function New-TempDbName {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $rand  = Get-Random -Minimum 1000 -Maximum 9999
  return "$DbPrefix$stamp" + "_" + $rand
}

function Drop-DbForce {
  param([Parameter(Mandatory=$true)][string]$DbName)

  $q = @"
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$DbName'
  AND pid <> pg_backend_pid();
"@
  Invoke-ComposePsql -DatabaseName $AdminDb -Sql $q
  Invoke-ComposePsql -DatabaseName $AdminDb -Sql ("DROP DATABASE IF EXISTS `"$DbName`";")
}

# ---- defaults
$repoRoot = Resolve-RepoRoot
Push-Location $repoRoot
try {
  $VerifyScriptPath = Resolve-VerifyScriptPath -Provided $VerifyScriptPath -RepoRoot $repoRoot

  if (-not $EvidenceRoot) {
    $EvidenceRoot = (Join-Path $repoRoot "ops\_local\evidence")
  }

  $rid = "freshdb_" + (Get-Date -Format "yyyyMMdd_HHmmss")
  $evDir = Join-Path $EvidenceRoot $rid
  $drillDir = Join-Path $evDir "fresh_db_drill"
  Ensure-Dir $drillDir

  $logFile = Join-Path $drillDir "drill.log"
  $verifyLog = Join-Path $drillDir "verify.log"

  $tempDb = New-TempDbName
  (Write-Log "FreshDB: temp db = $tempDb") | Tee-Object -FilePath $logFile -Append | Out-Host

  $ok = $false
  try {
    (Write-Log "FreshDB: create db $tempDb") | Tee-Object -FilePath $logFile -Append | Out-Host
    Invoke-ComposePsql -DatabaseName $AdminDb -Sql ("CREATE DATABASE `"$tempDb`";")

    (Write-Log "FreshDB: apply bootstrap $BootstrapSqlPath") | Tee-Object -FilePath $logFile -Append | Out-Host
    $stage = "$SqlStageBase/$rid"
    Invoke-ComposePsqlFileWithStage -DatabaseName $tempDb -FilePath $BootstrapSqlPath -StageDir $stage

    # 3) run verify suite (host-side)
    $env:FF_TEMP_DB = $tempDb

    (Write-Log "FreshDB: run verify suite $SuiteFile") | Tee-Object -FilePath $logFile -Append | Out-Host
    & pwsh -NoProfile -File $VerifyScriptPath -SuiteFile $SuiteFile *>&1 | Tee-Object -FilePath $verifyLog | Out-Host
    $verifyExit = $LASTEXITCODE
    if ($verifyExit -ne 0) { throw "Verify suite failed exit=$verifyExit" }

    $ok = $true
    (Write-Log "FreshDB: PASS") | Tee-Object -FilePath $logFile -Append | Out-Host
  }
  finally {
    $shouldKeep = $KeepDb.IsPresent -or (($KeepDbOnFail.IsPresent) -and (-not $ok))
    if ($shouldKeep) {
      (Write-Log "FreshDB: KEEP db $tempDb (KeepDb/KeepDbOnFail)") | Tee-Object -FilePath $logFile -Append | Out-Host
    }
    else {
      (Write-Log "FreshDB: drop db $tempDb") | Tee-Object -FilePath $logFile -Append | Out-Host
      try { Drop-DbForce -DbName $tempDb } catch { (Write-Log "FreshDB: drop failed: $_") | Tee-Object -FilePath $logFile -Append | Out-Host }
    }
    try { Remove-Item Env:\FF_TEMP_DB -ErrorAction SilentlyContinue } catch {}
  }

  if (-not $ok) { exit 2 }
  exit 0
}
finally {
  Pop-Location
}
