#requires -Version 7.0
<#
FoxProFlow RUN • Release M0 runner-wrapper
file: scripts/pwsh/ff-release-m0-run.ps1

Purpose:
  Backward-compatible wrapper that delegates to ff-release-m0.ps1
  so legacy automation keeps working.

Key rules:
  - DO NOT use variable name $args (PowerShell automatic variable)
  - Forward No* switches by .IsPresent
  - Avoid .Count on non-array objects (use @() or avoid count entirely)

Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$BaseUrl = $(if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8080" }),

  # legacy name in older calls
  [Alias("ProjectName","Project")]
  [string]$PreferProject = $(if ($env:FF_PROJECT) { $env:FF_PROJECT } elseif ($env:FF_COMPOSE_PROJECT) { $env:FF_COMPOSE_PROJECT } elseif ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "foxproflow-mvp20" }),

  [string]$ComposeFile = "",
  [string]$ReleaseId = "",

  [string]$ArchitectKey = $(if ($env:FF_ARCHITECT_KEY) { $env:FF_ARCHITECT_KEY } else { "" }),

  [ValidateSet("", "skip", "sql_dirs", "bootstrap_all_min", "custom")]
  [string]$MigrateMode = "",
  [string]$MigrateScript = "",

  [string]$SqlMigrationsDir = "",
  [string]$SqlFixpacksAutoDir = "",
  [switch]$ApplyGateFixpacks,

  [switch]$VerifyDbContract,
  [switch]$VerifyDbContractPlus,

  # Fresh DB drill knobs (ff-release-m0.ps1)
  [switch]$SkipFreshDbDrill,
  [switch]$KeepFreshDbDrillDb,
  [string]$FreshDbSqlWorktree = "",

  # Worker tasks smoke knobs (ff-release-m0.ps1)
  [switch]$SkipWorkerTasksSmoke,

  # Gate flags (ff-release-m0.ps1)
  [switch]$NoBackup,
  [switch]$NoBuild,
  [switch]$NoDeploy,
  [switch]$NoSmoke,
  [switch]$NoRollback,

  [int]$WaitApiTimeoutSec = 120,
  [int]$WaitApiPollSec = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Silence docker compose warnings about missing pgAdmin env vars (local-only; no compose/env changes)
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_EMAIL))    { $env:PGADMIN_EMAIL    = "disabled@local" }
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_PASSWORD)) { $env:PGADMIN_PASSWORD = "disabled" }

function Repo-Root { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }

function Resolve-ComposeFile([string]$repoRoot, [string]$composeFile) {
  if ([string]::IsNullOrWhiteSpace($composeFile)) { $composeFile = Join-Path $repoRoot "docker-compose.yml" }
  if (-not (Test-Path -LiteralPath $composeFile)) { throw "ComposeFile not found: $composeFile" }
  return (Resolve-Path -LiteralPath $composeFile).Path
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

function Normalize-BaseUrl([string]$u) {
  if ([string]::IsNullOrWhiteSpace($u)) { return "http://127.0.0.1:8080" }
  $u = $u.Trim()
  if ($u -match "localhost") { $u = ($u -replace "localhost","127.0.0.1") }
  while ($u.EndsWith("/")) { $u = $u.Substring(0, $u.Length - 1) }
  if ($u -notmatch '^https?://') { throw "BaseUrl must start with http:// or https://, got: $u" }
  return $u
}

function Normalize-ReleaseId([string]$rid) {
  if ([string]::IsNullOrWhiteSpace($rid)) { return $rid }
  $rid = $rid.Trim()
  $rid = ($rid -replace '[^A-Za-z0-9_.-]', '_').Trim('_')
  if ([string]::IsNullOrWhiteSpace($rid)) { throw "ReleaseId sanitized to empty. Provide a valid ReleaseId." }
  return $rid
}

function Get-ScriptParamNames([string]$scriptPath) {
  try {
    $tok = $null; $err = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tok, [ref]$err)
    if (@($err).Length -gt 0) { return @() }
    $pb = $ast.ParamBlock
    if (-not $pb) { return @() }
    $names = foreach ($p in $pb.Parameters) { $p.Name.VariablePath.UserPath }
    return @($names)
  } catch {
    return @()
  }
}

$repoRoot = Repo-Root
$BaseUrl = Normalize-BaseUrl $BaseUrl
$ComposeFile = Resolve-ComposeFile -repoRoot $repoRoot -composeFile $ComposeFile

if ([string]::IsNullOrWhiteSpace($ReleaseId)) {
  $ReleaseId = "m0_" + (Get-Date -Format "yyyyMMdd_HHmmss")
} else {
  $ReleaseId = Normalize-ReleaseId $ReleaseId
}

$main = Join-Path $PSScriptRoot "ff-release-m0.ps1"
if (-not (Test-Path -LiteralPath $main)) { throw "Missing main script: $main" }

$mainParams = Get-ScriptParamNames $main
$paramDetectOk = (@($mainParams).Length -gt 0)

$supported = @{}
foreach ($p in $mainParams) { if ($p) { $supported[$p] = $true } }

function Supports([string]$name) {
  if (-not $paramDetectOk) { return $true }
  return $supported.ContainsKey($name)
}

function AddKV([System.Collections.Generic.List[string]]$lst, [string]$name, [string]$value) {
  if (-not (Supports $name)) { return }
  if ([string]::IsNullOrWhiteSpace($value)) { return }
  $lst.Add("-$name") | Out-Null
  $lst.Add($value) | Out-Null
}

function AddSw([System.Collections.Generic.List[string]]$lst, [string]$name, [bool]$present) {
  if (-not $present) { return }
  if (-not (Supports $name)) { return }
  $lst.Add("-$name") | Out-Null
}

if ($ArchitectKey) { $env:FF_ARCHITECT_KEY = $ArchitectKey }

$pwshExe = Get-PwshExe

Write-Verbose ("RepoRoot: {0}" -f $repoRoot)
Write-Verbose ("ComposeFile: {0}" -f $ComposeFile)
Write-Verbose ("PreferProject: {0}" -f $PreferProject)
Write-Verbose ("BaseUrl: {0}" -f $BaseUrl)
Write-Verbose ("ReleaseId: {0}" -f $ReleaseId)
Write-Verbose ("Main: {0}" -f $main)
Write-Verbose ("ParamDetectOk: {0}" -f $paramDetectOk)
if ($paramDetectOk) {
  Write-Verbose ("Main params: {0}" -f (($mainParams | Sort-Object) -join ", "))
}

# IMPORTANT: do not use $args automatic variable
$forwardArgs = New-Object System.Collections.Generic.List[string]

# BaseUrl mapping (main supports BaseUrl)
AddKV $forwardArgs "BaseUrl" $BaseUrl
AddKV $forwardArgs "ComposeFile" $ComposeFile
AddKV $forwardArgs "ProjectName" $PreferProject
AddKV $forwardArgs "ReleaseId" $ReleaseId
AddKV $forwardArgs "WaitApiTimeoutSec" ([string]$WaitApiTimeoutSec)
AddKV $forwardArgs "WaitApiPollSec" ([string]$WaitApiPollSec)

if ($MigrateMode) { AddKV $forwardArgs "MigrateMode" $MigrateMode }
if ($MigrateScript) { AddKV $forwardArgs "MigrateScript" $MigrateScript }
if ($SqlMigrationsDir) { AddKV $forwardArgs "SqlMigrationsDir" $SqlMigrationsDir }
if ($SqlFixpacksAutoDir) { AddKV $forwardArgs "SqlFixpacksAutoDir" $SqlFixpacksAutoDir }

AddSw $forwardArgs "ApplyGateFixpacks" ($ApplyGateFixpacks.IsPresent)
AddSw $forwardArgs "VerifyDbContract" ($VerifyDbContract.IsPresent)
AddSw $forwardArgs "VerifyDbContractPlus" ($VerifyDbContractPlus.IsPresent)

# Fresh DB drill
AddSw $forwardArgs "SkipFreshDbDrill" ($SkipFreshDbDrill.IsPresent)
AddSw $forwardArgs "KeepFreshDbDrillDb" ($KeepFreshDbDrillDb.IsPresent)
AddKV $forwardArgs "FreshDbSqlWorktree" $FreshDbSqlWorktree

# Worker tasks smoke
AddSw $forwardArgs "SkipWorkerTasksSmoke" ($SkipWorkerTasksSmoke.IsPresent)

# CRITICAL No* flags
AddSw $forwardArgs "NoBackup" ($NoBackup.IsPresent)
AddSw $forwardArgs "NoBuild" ($NoBuild.IsPresent)
AddSw $forwardArgs "NoDeploy" ($NoDeploy.IsPresent)
AddSw $forwardArgs "NoSmoke" ($NoSmoke.IsPresent)
AddSw $forwardArgs "NoRollback" ($NoRollback.IsPresent)

# Forward wrapper verbosity to main
if ($PSBoundParameters.ContainsKey("Verbose")) {
  $forwardArgs.Add("-Verbose") | Out-Null
}

Write-Verbose ("Forward args: {0}" -f ($forwardArgs.ToArray() -join " "))
Write-Verbose ("Delegate: {0} -NoProfile -ExecutionPolicy Bypass -File `"{1}`" <args...>" -f $pwshExe, $main)

& $pwshExe -NoProfile -ExecutionPolicy Bypass -File $main @($forwardArgs.ToArray()) 2>&1
$code = $LASTEXITCODE
exit $code
