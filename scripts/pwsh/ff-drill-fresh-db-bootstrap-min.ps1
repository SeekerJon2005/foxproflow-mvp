#requires -Version 7.0
<#
FoxProFlow RUN • Fresh DB Drill • bootstrap_min
file: scripts/pwsh/ff-drill-fresh-db-bootstrap-min.ps1

Procedure (reproducible):
  1) create temp DB
  2) apply scripts/sql/bootstrap_min_apply.sql (prefer C-sql worktree)
     NOTE: bootstrap may contain psql includes (\i/\ir). This script expands them on host (inline) before sending to container.
  3) verify suite bootstrap_min (try run_verify_suite.ps1; fallback to direct suite apply into temp DB)
  4) drop temp DB

Outputs:
  PASS/FAIL (exit 0/1/2) + evidence dir.

Lane: A-RUN only. No src/** edits. No scripts/sql/** edits.

Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$ComposeFile = "",
  [string]$ProjectName = $(if ($env:FF_COMPOSE_PROJECT) { $env:FF_COMPOSE_PROJECT } elseif ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "" }),

  [string]$TempDbName = "",

  [string]$BootstrapSqlFile = "",
  [string]$SuiteFile = "",
  [string]$VerifyRunnerScript = "",

  [string]$EvidenceDir = "",

  [switch]$KeepTempDb
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

function Write-Step([string]$msg) { Write-Host ("`n==> " + $msg) -ForegroundColor Cyan }
function Write-Warn([string]$msg) { Write-Host ("WARN: " + $msg) -ForegroundColor Yellow }
function Write-Ok([string]$msg)   { Write-Host ("OK: " + $msg) -ForegroundColor Green }
function Write-Fail([string]$msg) { Write-Host ("FAIL: " + $msg) -ForegroundColor Red }

function Resolve-ComposeFile([string]$repoRoot, [string]$composeFile) {
  if ([string]::IsNullOrWhiteSpace($composeFile)) { $composeFile = Join-Path $repoRoot "docker-compose.yml" }
  if (-not (Test-Path -LiteralPath $composeFile)) { throw "ComposeFile not found: $composeFile" }
  return (Resolve-Path -LiteralPath $composeFile).Path
}

function Resolve-SiblingWorktree([string]$repoRoot, [string]$siblingName) {
  $parent = Split-Path $repoRoot -Parent
  if ([string]::IsNullOrWhiteSpace($parent)) { return $null }
  $cand = Join-Path $parent $siblingName
  if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }
  return $null
}

function Resolve-SqlRoot([string]$repoRoot) {
  $cSqlRoot = Resolve-SiblingWorktree -repoRoot $repoRoot -siblingName "C-sql"
  if ($cSqlRoot) {
    $p = Join-Path $cSqlRoot "scripts\sql"
    if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
  }
  $p2 = Join-Path $repoRoot "scripts\sql"
  if (Test-Path -LiteralPath $p2) { return (Resolve-Path -LiteralPath $p2).Path }
  throw "scripts/sql not found in C-sql nor in current repoRoot"
}

function Resolve-VerifyRunner([string]$repoRoot) {
  $cSqlRoot = Resolve-SiblingWorktree -repoRoot $repoRoot -siblingName "C-sql"
  if ($cSqlRoot) {
    $p = Join-Path $cSqlRoot "scripts\sql\verify\run_verify_suite.ps1"
    if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
  }
  $p2 = Join-Path $repoRoot "scripts\sql\verify\run_verify_suite.ps1"
  if (Test-Path -LiteralPath $p2) { return (Resolve-Path -LiteralPath $p2).Path }
  throw "verify runner not found: scripts/sql/verify/run_verify_suite.ps1"
}

function Get-PwshExe() {
  try {
    if ($IsWindows) {
      $cand = Join-Path $PSHOME "pwsh.exe"
      if (Test-Path -LiteralPath $cand) { return $cand }
    }
  } catch { }
  return "pwsh"
}

function Get-ScriptParamNames([string]$scriptPath) {
  try {
    $tok = $null; $err = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tok, [ref]$err)
    if ($err -and $err.Count -gt 0) { return @() }
    $pb = $ast.ParamBlock
    if (-not $pb) { return @() }
    $names = @()
    foreach ($p in $pb.Parameters) { $names += $p.Name.VariablePath.UserPath }
    return $names
  } catch { return @() }
}

function Sanitize-TempDbName([string]$name) {
  if ([string]::IsNullOrWhiteSpace($name)) { return $name }
  $n = ($name.Trim().ToLowerInvariant() -replace '[^a-z0-9_]', '_')
  if (-not $n.StartsWith("tmp_")) { $n = "tmp_" + $n }
  if ($n.Length -gt 60) { $n = $n.Substring(0,60) }
  return $n
}

# -----------------------------
# psql include expansion (\i/\ir)
# -----------------------------
function Try-ParsePsqlInclude([string]$line) {
  # supports: \i file.sql, \ir file.sql (psql meta-commands)
  $m = [regex]::Match($line, '^\s*\\i(r)?\s+(.+?)\s*$')
  if (-not $m.Success) { return $null }

  $p = $m.Groups[2].Value.Trim()

  # strip inline comments for unquoted paths
  $p = ($p -replace '\s+--.*$', '').Trim()

  # strip quotes
  if (($p.StartsWith('"') -and $p.EndsWith('"')) -or ($p.StartsWith("'") -and $p.EndsWith("'"))) {
    if ($p.Length -ge 2) { $p = $p.Substring(1, $p.Length - 2) }
  }

  if ([string]::IsNullOrWhiteSpace($p)) { return $null }
  return $p
}

function Expand-PsqlIncludes([string]$sqlFile, [hashtable]$seen = $null) {
  if (-not $seen) { $seen = @{} }
  if (-not (Test-Path -LiteralPath $sqlFile)) { throw "SQL file not found: $sqlFile" }

  $full = (Resolve-Path -LiteralPath $sqlFile).Path
  if ($seen.ContainsKey($full)) {
    return ("-- SKIP RECURSIVE INCLUDE: {0}`n" -f $full)
  }
  $seen[$full] = $true

  $baseDir = Split-Path $full -Parent
  $sb = New-Object System.Text.StringBuilder

  $lines = Get-Content -LiteralPath $full -Encoding UTF8
  foreach ($line in $lines) {
    $incRel = Try-ParsePsqlInclude $line
    if ($incRel) {
      $incPath = $incRel
      if (-not [System.IO.Path]::IsPathRooted($incPath)) { $incPath = Join-Path $baseDir $incPath }

      if (-not (Test-Path -LiteralPath $incPath)) {
        throw ("psql include not found: {0} (resolved: {1}) referenced from {2}" -f $incRel, $incPath, $full)
      }

      $incFull = (Resolve-Path -LiteralPath $incPath).Path
      [void]$sb.AppendLine(("-- BEGIN INCLUDE: {0} => {1}" -f $incRel, $incFull))
      [void]$sb.Append((Expand-PsqlIncludes -sqlFile $incFull -seen $seen))
      [void]$sb.AppendLine(("-- END INCLUDE: {0}" -f $incRel))
      continue
    }

    [void]$sb.AppendLine($line)
  }

  return $sb.ToString()
}

# -----------------------------
# psql helpers
# -----------------------------
function Invoke-PsqlSqlFile([string]$composeFile, [string]$projectName, [string]$dbName, [string]$sqlFile, [string]$logPath) {
  if (-not (Test-Path -LiteralPath $sqlFile)) { throw "SQL file not found: $sqlFile" }

  # Expand \i/\ir on host so psql inside container does not need host paths.
  $sqlText = Expand-PsqlIncludes -sqlFile $sqlFile -seen @{}

  $dcArgv = @(
    "compose","--ansi","never","-f",$composeFile,"-p",$projectName,
    "exec","-T","postgres",
    "psql","-U","admin","-d",$dbName,"-X","-v","ON_ERROR_STOP=1","-f","-"
  )

  $out = $sqlText | & docker @dcArgv 2>&1
  $code = $LASTEXITCODE

  if ($logPath) {
    $logDir = Split-Path $logPath -Parent
    if ($logDir) {
      $expandedName = "expanded_" + [System.IO.Path]::GetFileName($sqlFile)
      Set-Utf8 (Join-Path $logDir $expandedName) $sqlText
    }

    Set-Utf8 $logPath ("ts={0}`ndb={1}`nfile={2}`nargv=docker {3}`n`n{4}`nexit_code={5}`n" -f `
      (Now-Iso), $dbName, $sqlFile, ($dcArgv -join " "), ($out | Out-String), $code)
  }

  return [pscustomobject]@{ code=$code; out=($out|Out-String) }
}

function Invoke-PsqlStdin([string]$composeFile, [string]$projectName, [string]$dbName, [string]$sqlText, [string]$logPath) {
  $dcArgv = @(
    "compose","--ansi","never","-f",$composeFile,"-p",$projectName,
    "exec","-T","postgres",
    "psql","-U","admin","-d",$dbName,"-X","-v","ON_ERROR_STOP=1","-f","-"
  )

  $out = $sqlText | & docker @dcArgv 2>&1
  $code = $LASTEXITCODE

  if ($logPath) {
    Set-Utf8 $logPath ("ts={0}`ndb={1}`nargv=docker {2}`n`n{3}`nexit_code={4}`n" -f `
      (Now-Iso), $dbName, ($dcArgv -join " "), ($out | Out-String), $code)
  }

  return [pscustomobject]@{ code=$code; out=($out|Out-String) }
}

# -----------------------------
# verify suite helpers
# -----------------------------
function Resolve-SuiteSqlRoot([string]$suiteFile) {
  $suiteDir  = Split-Path $suiteFile -Parent   # ...\scripts\sql\verify\suites
  $verifyDir = Split-Path $suiteDir  -Parent   # ...\scripts\sql\verify
  $sqlRoot   = Split-Path $verifyDir -Parent   # ...\scripts\sql
  return $sqlRoot
}

function Resolve-SuiteItem([string]$sqlRoot, [string]$line) {
  $p = $line.Trim()
  if ([string]::IsNullOrWhiteSpace($p)) { return $null }
  if ($p.StartsWith("#")) { return $null }

  if ([System.IO.Path]::IsPathRooted($p)) {
    return (Test-Path -LiteralPath $p) ? (Resolve-Path -LiteralPath $p).Path : $null
  }

  $c1 = Join-Path $sqlRoot $p
  if (Test-Path -LiteralPath $c1) { return (Resolve-Path -LiteralPath $c1).Path }

  $c2 = Join-Path (Join-Path $sqlRoot "verify") $p
  if (Test-Path -LiteralPath $c2) { return (Resolve-Path -LiteralPath $c2).Path }

  return $null
}

function Run-VerifySuite([string]$repoRoot, [string]$composeFile, [string]$projectName, [string]$dbName, [string]$suiteFile, [string]$evidenceDir) {
  $runner = if ($VerifyRunnerScript) { $VerifyRunnerScript } else { (Resolve-VerifyRunner -repoRoot $repoRoot) }
  if (-not (Test-Path -LiteralPath $runner)) { throw "Verify runner not found: $runner" }

  $log = Join-Path $evidenceDir "verify_suite_runner.log"
  $pwshExe = Get-PwshExe
  $params = Get-ScriptParamNames $runner

  # Set env for DB targeting (even if runner supports param, env is harmless)
  $env:PGDATABASE = $dbName
  $env:FF_DB_NAME = $dbName

  $args = New-Object System.Collections.Generic.List[string]
  if ($params -contains "SuiteFile") { $args.AddRange([string[]]@("-SuiteFile", $suiteFile)) | Out-Null }
  else { throw "verify runner has no -SuiteFile parameter: $runner" }

  if ($params -contains "EvidenceDir") { $args.AddRange([string[]]@("-EvidenceDir", $evidenceDir)) | Out-Null }
  elseif ($params -contains "OutDir")  { $args.AddRange([string[]]@("-OutDir", $evidenceDir)) | Out-Null }

  if ($params -contains "ComposeFile") { $args.AddRange([string[]]@("-ComposeFile", $composeFile)) | Out-Null }
  if ($params -contains "ProjectName") { $args.AddRange([string[]]@("-ProjectName", $projectName)) | Out-Null }
  elseif ($params -contains "Project") { $args.AddRange([string[]]@("-Project", $projectName)) | Out-Null }

  # Optional explicit DB param (best effort)
  $dbParam = $null
  foreach ($cand in @("DbName","Database","DatabaseName","Db")) { if ($params -contains $cand) { $dbParam = $cand; break } }
  if ($dbParam) { $args.AddRange([string[]]@("-$dbParam", $dbName)) | Out-Null }

  $argv = @("-NoProfile","-ExecutionPolicy","Bypass","-File",$runner) + $args.ToArray()
  $out = & $pwshExe @argv 2>&1
  $code = $LASTEXITCODE

  Set-Utf8 $log ("ts={0}`nrunner={1}`nargv={2}`n`n{3}`nexit_code={4}`n" -f (Now-Iso), $runner, ("$pwshExe " + ($argv -join " ")), ($out | Out-String), $code)
  if ($code -eq 0) { return $true }

  Write-Warn "verify runner failed — fallback: apply suite items directly into temp DB"
  $fb = Join-Path $evidenceDir "verify_suite_fallback.log"
  $sqlRoot = Resolve-SuiteSqlRoot $suiteFile
  Add-Utf8 $fb ("ts={0}`nsuite_file={1}`nsql_root={2}`n" -f (Now-Iso), $suiteFile, $sqlRoot)

  $lines = Get-Content -LiteralPath $suiteFile -ErrorAction Stop
  foreach ($ln in $lines) {
    $f = Resolve-SuiteItem -sqlRoot $sqlRoot -line $ln
    if (-not $f) { continue }
    $name = [System.IO.Path]::GetFileName($f)
    $logPath = Join-Path $evidenceDir ("verify_{0}.log" -f $name)
    $r = Invoke-PsqlSqlFile -composeFile $composeFile -projectName $projectName -dbName $dbName -sqlFile $f -logPath $logPath
    Add-Utf8 $fb ("apply={0} exit={1}`n" -f $f, $r.code)
    if ($r.code -ne 0) { throw "verify suite fallback failed on $name" }
  }

  return $true
}

# -----------------------------
# Main
# -----------------------------
$repoRoot = Repo-Root
$ComposeFile = Resolve-ComposeFile -repoRoot $repoRoot -composeFile $ComposeFile

if ([string]::IsNullOrWhiteSpace($ProjectName)) {
  throw "ProjectName is empty. Provide -ProjectName or set FF_COMPOSE_PROJECT/COMPOSE_PROJECT_NAME."
}

$sqlRoot = Resolve-SqlRoot -repoRoot $repoRoot

if ([string]::IsNullOrWhiteSpace($BootstrapSqlFile)) { $BootstrapSqlFile = Join-Path $sqlRoot "bootstrap_min_apply.sql" }
if ([string]::IsNullOrWhiteSpace($SuiteFile))        { $SuiteFile = Join-Path $sqlRoot "verify\suites\bootstrap_min.txt" }

if (-not (Test-Path -LiteralPath $BootstrapSqlFile)) { throw "bootstrap sql not found: $BootstrapSqlFile" }
if (-not (Test-Path -LiteralPath $SuiteFile))        { throw "suite file not found: $SuiteFile" }

if ([string]::IsNullOrWhiteSpace($TempDbName)) {
  $TempDbName = ("tmp_bootmin_{0}" -f (Now-Stamp)).ToLowerInvariant()
} else {
  $TempDbName = Sanitize-TempDbName $TempDbName
}

if ([string]::IsNullOrWhiteSpace($EvidenceDir)) {
  $EvidenceDir = Join-Path $repoRoot ("ops\_local\evidence\fresh_db_bootstrap_min_{0}" -f (Now-Stamp))
}
Ensure-Dir $EvidenceDir
Write-Output ("evidence: " + $EvidenceDir)

$started = Now-Iso
$exitCode = 0
$ok = $false
$failReason = ""

try {
  Write-Step "CREATE TEMP DB"
  $createLog = Join-Path $EvidenceDir "create_db.log"

  # Idempotent create: terminate + drop if exists, then create
  $sqlCreate = @"
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$TempDbName' AND pid <> pg_backend_pid();

DROP DATABASE IF EXISTS $TempDbName;

CREATE DATABASE $TempDbName WITH OWNER admin;
"@
  $r1 = Invoke-PsqlStdin -composeFile $ComposeFile -projectName $ProjectName -dbName "postgres" -sqlText $sqlCreate -logPath $createLog
  if ($r1.code -ne 0) { throw "create temp db failed (exit=$($r1.code))" }

  Write-Step "APPLY bootstrap_min_apply.sql"
  $applyLog = Join-Path $EvidenceDir "apply_bootstrap_min.log"
  $r2 = Invoke-PsqlSqlFile -composeFile $ComposeFile -projectName $ProjectName -dbName $TempDbName -sqlFile $BootstrapSqlFile -logPath $applyLog
  if ($r2.code -ne 0) { throw "bootstrap_min apply failed (exit=$($r2.code))" }

  Write-Step "VERIFY SUITE bootstrap_min"
  Run-VerifySuite -repoRoot $repoRoot -composeFile $ComposeFile -projectName $ProjectName -dbName $TempDbName -suiteFile $SuiteFile -evidenceDir $EvidenceDir | Out-Null

  $ok = $true
}
catch {
  $ok = $false
  $exitCode = 1
  $failReason = $_.Exception.Message
  try {
    Set-Utf8 (Join-Path $EvidenceDir "drill_error.txt") ("ts={0}`nerror={1}`n`n{2}" -f (Now-Iso), $failReason, ($_.Exception.ToString()))
  } catch {}
}
finally {
  try {
    if (-not $KeepTempDb) {
      Write-Step "DROP TEMP DB"
      $dropLog = Join-Path $EvidenceDir "drop_db.log"
      $sqlDrop = @"
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$TempDbName' AND pid <> pg_backend_pid();

DROP DATABASE IF EXISTS $TempDbName;
"@
      $rd = Invoke-PsqlStdin -composeFile $ComposeFile -projectName $ProjectName -dbName "postgres" -sqlText $sqlDrop -logPath $dropLog
      if ($rd.code -ne 0) {
        Write-Warn "drop temp db failed (see drop_db.log)"
        if ($exitCode -eq 0) { $exitCode = 2 }
      }
    } else {
      Write-Warn ("KeepTempDb: leaving db '{0}'" -f $TempDbName)
    }
  } catch {
    Write-Warn ("drop block threw: " + $_.Exception.Message)
    if ($exitCode -eq 0) { $exitCode = 2 }
  }

  $ended = Now-Iso
  $summary = [pscustomobject]@{
    ts_started   = $started
    ts_ended     = $ended
    ok           = [bool]$ok
    exit_code    = [int]$exitCode
    fail_reason  = [string]$failReason
    compose_file = $ComposeFile
    project_name = $ProjectName
    temp_db      = $TempDbName
    bootstrap_sql = $BootstrapSqlFile
    suite_file    = $SuiteFile
    verify_runner = $(if ($VerifyRunnerScript) { $VerifyRunnerScript } else { "auto" })
    evidence_dir  = $EvidenceDir
    keep_temp_db  = [bool]$KeepTempDb
  }

  try {
    $json = ($summary | ConvertTo-Json -Depth 40)
    Set-Utf8 (Join-Path $EvidenceDir "summary.json") $json
  } catch {}
}

if ($ok -and $exitCode -eq 0) {
  Write-Ok "FRESH DB DRILL OK"
  exit 0
} else {
  Write-Fail ("FRESH DB DRILL FAILED (exit={0}): {1}" -f $exitCode, $failReason)
  exit $exitCode
}
