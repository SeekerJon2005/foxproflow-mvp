#requires -Version 7.0
<#
FoxProFlow RUN • Fresh DB Drill (bootstrap + verify + drop)
file: scripts/pwsh/ff-fresh-db-drill.ps1

Procedure:
  1) create temp DB
  2) apply bootstrap SQL via psql inside postgres container (supports \i fixpacks/*)
  3) run verify suite script (host-side) FROM C-sql root so suite relative paths resolve
  4) drop temp DB (unless KeepDb / KeepDbOnFail)

Outputs:
  - exit code 0 on PASS
  - non-zero on FAIL
  - evidence logs in ops/_local/evidence/<rid>/fresh_db_drill/  (or under -EvidenceDir if provided)
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  # Optional: where SQL artifacts live (usually C-sql worktree). If empty -> auto-detect sibling C-sql.
  [AllowEmptyString()]
  [string] $SqlWorktree = "",

  # Optional: bootstrap SQL file. If empty -> default to <SqlWorktree>\scripts\sql\bootstrap_min_apply.sql
  [AllowEmptyString()]
  [string] $BootstrapSqlPath = "",

  # Optional: suite file. If empty -> default to <SqlWorktree>\scripts\sql\verify\suites\bootstrap_min.txt
  [AllowEmptyString()]
  [string] $SuiteFile = "",

  # Optional compose controls (recommended for determinism)
  [AllowEmptyString()]
  [string] $ComposeFile = "",

  [AllowEmptyString()]
  [string] $ProjectName = "",

  [string] $PgService = "postgres",
  [string] $PgUser = $(if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "admin" }),
  [string] $AdminDb = "postgres",
  [string] $DbPrefix = "ff_tmp_",

  # optional; auto-detect if empty
  [AllowEmptyString()]
  [string] $VerifyScriptPath = "",

  # If provided: write outputs into <EvidenceDir>\fresh_db_drill\...
  [AllowEmptyString()]
  [string] $EvidenceDir = "",

  # If EvidenceDir is empty: create new rid under EvidenceRoot (defaults to repoRoot\ops\_local\evidence)
  [AllowEmptyString()]
  [string] $EvidenceRoot = "",

  # where to stage SQL tree inside postgres container
  [string] $SqlStageBase = "/tmp/ffsql_stage",

  # Allow mismatch for compose project selection in downstream verify scripts (if they support it)
  [switch] $AllowProjectMismatch,

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
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
  }
}

function Write-Log([string]$Msg) {
  $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  "[${ts}] $Msg"
}

function Resolve-ComposeFile {
  param(
    [string] $Provided,
    [string] $RepoRoot
  )
  if (-not [string]::IsNullOrWhiteSpace($Provided)) {
    if (-not (Test-Path -LiteralPath $Provided)) { throw "ComposeFile provided but not found: $Provided" }
    return (Resolve-Path -LiteralPath $Provided).Path
  }
  $p = Join-Path $RepoRoot "docker-compose.yml"
  if (-not (Test-Path -LiteralPath $p)) { throw "ComposeFile not found (default): $p" }
  return (Resolve-Path -LiteralPath $p).Path
}

function Resolve-ProjectName {
  param([string]$Provided)
  if (-not [string]::IsNullOrWhiteSpace($Provided)) { return $Provided.Trim() }
  if (-not [string]::IsNullOrWhiteSpace($env:FF_COMPOSE_PROJECT)) { return $env:FF_COMPOSE_PROJECT.Trim() }
  if (-not [string]::IsNullOrWhiteSpace($env:COMPOSE_PROJECT_NAME)) { return $env:COMPOSE_PROJECT_NAME.Trim() }
  return "foxproflow-mvp20"
}

function Resolve-SqlWorktree {
  param(
    [string] $Provided,
    [string] $RepoRoot
  )

  if (-not [string]::IsNullOrWhiteSpace($Provided)) {
    if (-not (Test-Path -LiteralPath $Provided -PathType Container)) { throw "SqlWorktree not found: $Provided" }
    return (Resolve-Path -LiteralPath $Provided).Path
  }

  # sibling worktree: <wt_parent>\C-sql
  $wtParent = Split-Path -Parent $RepoRoot
  $cand = Join-Path $wtParent "C-sql"
  if (Test-Path -LiteralPath $cand -PathType Container) {
    return (Resolve-Path -LiteralPath $cand).Path
  }

  throw "SqlWorktree is empty and sibling C-sql not found near RepoRoot='$RepoRoot'. Provide -SqlWorktree."
}

function Resolve-RelOrAbsFile {
  param(
    [Parameter(Mandatory=$true)][string] $BaseDir,
    [AllowEmptyString()][string] $Value,
    [Parameter(Mandatory=$true)][string] $DefaultRel
  )

  $v = $Value
  if ([string]::IsNullOrWhiteSpace($v)) { $v = $DefaultRel }

  if ([System.IO.Path]::IsPathRooted($v)) {
    if (-not (Test-Path -LiteralPath $v -PathType Leaf)) { throw "File not found: $v" }
    return (Resolve-Path -LiteralPath $v).Path
  }

  $cand = Join-Path $BaseDir $v
  if (-not (Test-Path -LiteralPath $cand -PathType Leaf)) { throw "File not found: $cand" }
  return (Resolve-Path -LiteralPath $cand).Path
}

function Resolve-VerifyScriptPath {
  param(
    [string] $Provided,
    [string] $RepoRoot,
    [string] $SqlWorktreeResolved
  )

  if (-not [string]::IsNullOrWhiteSpace($Provided)) {
    if (Test-Path -LiteralPath $Provided) {
      return (Resolve-Path -LiteralPath $Provided).Path
    }
    throw "VerifyScriptPath provided but not found: $Provided"
  }

  $wtParent = Split-Path -Parent $RepoRoot

  $candidates = @(
    (Join-Path $SqlWorktreeResolved "scripts\sql\verify\run_verify_suite.ps1"),
    (Join-Path $SqlWorktreeResolved "scripts\sql\verify\run_verify_suite_v2.ps1"),
    (Join-Path $RepoRoot            "scripts\sql\verify\run_verify_suite.ps1"),
    (Join-Path $RepoRoot            "scripts\sql\verify\run_verify_suite_v2.ps1"),
    (Join-Path $wtParent            "C-sql\scripts\sql\verify\run_verify_suite.ps1"),
    (Join-Path $wtParent            "C-sql\scripts\sql\verify\run_verify_suite_v2.ps1")
  )

  foreach ($p in $candidates) {
    if (Test-Path -LiteralPath $p) {
      return (Resolve-Path -LiteralPath $p).Path
    }
  }

  throw ("Verify script not found. Tried: " + ($candidates -join "; "))
}

function Get-PwshExe {
  try {
    if ($IsWindows) {
      $cand = Join-Path $PSHOME "pwsh.exe"
      if (Test-Path -LiteralPath $cand) { return $cand }
    }
  } catch { }
  return "pwsh"
}

function Get-ScriptParamKeys {
  param([Parameter(Mandatory=$true)][string]$ScriptPath)
  try {
    $cmd = Get-Command $ScriptPath -ErrorAction Stop
    return @($cmd.Parameters.Keys)
  } catch {
    return @()
  }
}

function Get-DcArgs {
  param([Parameter(Mandatory=$true)][string[]]$Tail)

  $list = New-Object System.Collections.Generic.List[string]
  $list.Add("compose") | Out-Null
  $list.Add("--ansi")  | Out-Null
  $list.Add("never")   | Out-Null

  if ($script:ComposeFileResolved) {
    $list.Add("-f") | Out-Null
    $list.Add($script:ComposeFileResolved) | Out-Null
  }
  if ($script:ProjectNameResolved) {
    $list.Add("-p") | Out-Null
    $list.Add($script:ProjectNameResolved) | Out-Null
  }
  foreach ($x in $Tail) { $list.Add($x) | Out-Null }
  return $list.ToArray()
}

function Get-PgContainerId {
  $argv = Get-DcArgs -Tail @("ps","-q",$PgService)
  $cid = (& docker @argv 2>$null | Select-Object -First 1)
  if (-not $cid) { throw "Cannot resolve container id for service '$PgService' (docker compose ps -q returned empty)" }
  return $cid.Trim()
}

function Invoke-ComposePsql {
  param(
    [Parameter(Mandatory = $true)][string] $DatabaseName,
    [Parameter(Mandatory = $true)][string] $Sql
  )

  $argv = Get-DcArgs -Tail @("exec","-T",$PgService,"psql","-X","-v","ON_ERROR_STOP=1","-U",$PgUser,"-d",$DatabaseName,"-c",$Sql)
  & docker @argv | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "psql failed (db=$DatabaseName) exit=$LASTEXITCODE" }
}

function Invoke-ComposePsqlFileWithStage {
  param(
    [Parameter(Mandatory = $true)][string] $DatabaseName,
    [Parameter(Mandatory = $true)][string] $FilePath,
    [Parameter(Mandatory = $true)][string] $StageDir
  )

  $fp = (Resolve-Path -LiteralPath $FilePath).Path
  if (-not (Test-Path -LiteralPath $fp)) { throw "Bootstrap SQL not found: $fp" }

  $sqlRootHost = Split-Path -Parent $fp
  $baseName = Split-Path -Leaf $fp

  $cid = Get-PgContainerId

  $argvPrep = Get-DcArgs -Tail @("exec","-T",$PgService,"sh","-lc","rm -rf '$StageDir' && mkdir -p '$StageDir'")
  & docker @argvPrep | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "failed to prepare stage dir in container: $StageDir" }

  $destSqlDir = "$StageDir/sql"
  $cleanupOk = $false
  try {
    docker cp "$sqlRootHost" "${cid}:${destSqlDir}" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "docker cp failed for sql root: $sqlRootHost -> $destSqlDir" }

    $cmd = "cd '$destSqlDir' && psql -X -v ON_ERROR_STOP=1 -U '$PgUser' -d '$DatabaseName' -f '$baseName'"
    $argvRun = Get-DcArgs -Tail @("exec","-T",$PgService,"sh","-lc",$cmd)
    & docker @argvRun | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "psql -f failed (db=$DatabaseName) exit=$LASTEXITCODE" }

    $cleanupOk = $true
  }
  finally {
    # Cleanup stage dir best-effort
    $argvClean = Get-DcArgs -Tail @("exec","-T",$PgService,"sh","-lc","rm -rf '$StageDir'")
    & docker @argvClean | Out-Host
    if (-not $cleanupOk -and $LASTEXITCODE -ne 0) {
      # do not throw from cleanup
      $null = $LASTEXITCODE
    }
  }
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

# ---- defaults / resolve
$repoRoot = Resolve-RepoRoot
$script:ComposeFileResolved = Resolve-ComposeFile -Provided $ComposeFile -RepoRoot $repoRoot
$script:ProjectNameResolved = Resolve-ProjectName -Provided $ProjectName

$SqlWorktreeResolved = Resolve-SqlWorktree -Provided $SqlWorktree -RepoRoot $repoRoot

$BootstrapAbs = Resolve-RelOrAbsFile -BaseDir $SqlWorktreeResolved -Value $BootstrapSqlPath -DefaultRel "scripts/sql/bootstrap_min_apply.sql"
$SuiteAbs     = Resolve-RelOrAbsFile -BaseDir $SqlWorktreeResolved -Value $SuiteFile       -DefaultRel "scripts/sql/verify/suites/bootstrap_min.txt"

$VerifyScriptAbs = Resolve-VerifyScriptPath -Provided $VerifyScriptPath -RepoRoot $repoRoot -SqlWorktreeResolved $SqlWorktreeResolved
$pwshExe = Get-PwshExe

# Evidence directories
if ([string]::IsNullOrWhiteSpace($EvidenceRoot)) {
  $EvidenceRoot = Join-Path $repoRoot "ops\_local\evidence"
}

$rid = "freshdb_" + (Get-Date -Format "yyyyMMdd_HHmmss")
if (-not [string]::IsNullOrWhiteSpace($EvidenceDir)) {
  $evDir = (Resolve-Path -LiteralPath $EvidenceDir).Path
  $drillDir = Join-Path $evDir "fresh_db_drill"
} else {
  $evDir = Join-Path $EvidenceRoot $rid
  $drillDir = Join-Path $evDir "fresh_db_drill"
}
Ensure-Dir $drillDir

$logFile   = Join-Path $drillDir "drill.log"
$verifyLog = Join-Path $drillDir "verify.log"

# ---- run
Push-Location $repoRoot
try {
  $tempDb = New-TempDbName
  (Write-Log "FreshDB: temp db = $tempDb") | Tee-Object -FilePath $logFile -Append | Out-Host
  (Write-Log "FreshDB: repoRoot=$repoRoot composeFile=$($script:ComposeFileResolved) project=$($script:ProjectNameResolved)") | Tee-Object -FilePath $logFile -Append | Out-Host
  (Write-Log "FreshDB: sqlWorktree=$SqlWorktreeResolved") | Tee-Object -FilePath $logFile -Append | Out-Host
  (Write-Log "FreshDB: bootstrap=$BootstrapAbs") | Tee-Object -FilePath $logFile -Append | Out-Host
  (Write-Log "FreshDB: suite=$SuiteAbs") | Tee-Object -FilePath $logFile -Append | Out-Host
  (Write-Log "FreshDB: verifyScript=$VerifyScriptAbs") | Tee-Object -FilePath $logFile -Append | Out-Host

  $ok = $false
  try {
    (Write-Log "FreshDB: create db $tempDb") | Tee-Object -FilePath $logFile -Append | Out-Host
    Invoke-ComposePsql -DatabaseName $AdminDb -Sql ("CREATE DATABASE `"$tempDb`";")

    (Write-Log "FreshDB: apply bootstrap (staged) $BootstrapAbs") | Tee-Object -FilePath $logFile -Append | Out-Host
    $stage = "$SqlStageBase/$rid"
    Invoke-ComposePsqlFileWithStage -DatabaseName $tempDb -FilePath $BootstrapAbs -StageDir $stage

    # 3) run verify suite (host-side)
    $env:FF_TEMP_DB = $tempDb

    (Write-Log "FreshDB: run verify suite (cwd=C-sql) $SuiteAbs") | Tee-Object -FilePath $logFile -Append | Out-Host

    $verifyKeys = Get-ScriptParamKeys -ScriptPath $VerifyScriptAbs
    (Write-Log ("FreshDB: verify params detected: " + ($verifyKeys -join ", "))) | Tee-Object -FilePath $logFile -Append | Out-Host

    $verifyArgs = New-Object System.Collections.Generic.List[string]
    if ($verifyKeys -contains "SuiteFile") { $verifyArgs.AddRange([string[]]@("-SuiteFile",$SuiteAbs)) | Out-Null }

    # Prefer passing target DB if supported
    if ($verifyKeys -contains "PgDb") { $verifyArgs.AddRange([string[]]@("-PgDb",$tempDb)) | Out-Null }
    elseif ($verifyKeys -contains "DbName") { $verifyArgs.AddRange([string[]]@("-DbName",$tempDb)) | Out-Null }

    if ($verifyKeys -contains "PgUser") { $verifyArgs.AddRange([string[]]@("-PgUser",$PgUser)) | Out-Null }
    if ($verifyKeys -contains "PreferProject") { $verifyArgs.AddRange([string[]]@("-PreferProject",$script:ProjectNameResolved)) | Out-Null }
    if ($AllowProjectMismatch.IsPresent -and ($verifyKeys -contains "AllowProjectMismatch")) { $verifyArgs.Add("-AllowProjectMismatch") | Out-Null }

    # Run from SqlWorktree so suite relative paths resolve
    $cwdBefore = (Get-Location).Path
    try {
      Set-Location -LiteralPath $SqlWorktreeResolved
      & $pwshExe -NoProfile -File $VerifyScriptAbs @($verifyArgs.ToArray()) *>&1 | Tee-Object -FilePath $verifyLog | Out-Host
    } finally {
      Set-Location -LiteralPath $cwdBefore
    }

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
