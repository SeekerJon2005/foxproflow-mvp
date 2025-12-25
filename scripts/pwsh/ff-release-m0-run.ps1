#requires -Version 7.0
<#
FoxProFlow RUN • Release M0 runner-wrapper
file: scripts/pwsh/ff-release-m0-run.ps1

Purpose:
  Backward-compatible wrapper that delegates to ff-release-m0.ps1
  so legacy automation keeps working.

Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$BaseUrl = $(if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8080" }),

  # legacy name in older calls
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

$repoRoot = Repo-Root
$ComposeFile = Resolve-ComposeFile -repoRoot $repoRoot -composeFile $ComposeFile

if ([string]::IsNullOrWhiteSpace($ReleaseId)) {
  $ReleaseId = "m0_" + (Get-Date -Format "yyyyMMdd_HHmmss")
}

$main = Join-Path $PSScriptRoot "ff-release-m0.ps1"
if (-not (Test-Path -LiteralPath $main)) {
  throw "Missing main script: $main"
}

if ($ArchitectKey) { $env:FF_ARCHITECT_KEY = $ArchitectKey }

$pwshExe = Get-PwshExe

# build args to forward
$args = New-Object System.Collections.Generic.List[string]
$args.AddRange([string[]]@(
  "-BaseUrl", $BaseUrl,
  "-ComposeFile", $ComposeFile,
  "-ProjectName", $PreferProject,
  "-ReleaseId", $ReleaseId,
  "-WaitApiTimeoutSec", [string]$WaitApiTimeoutSec,
  "-WaitApiPollSec", [string]$WaitApiPollSec
)) | Out-Null

if ($MigrateMode) { $args.AddRange([string[]]@("-MigrateMode", $MigrateMode)) | Out-Null }
if ($MigrateScript) { $args.AddRange([string[]]@("-MigrateScript", $MigrateScript)) | Out-Null }
if ($SqlMigrationsDir) { $args.AddRange([string[]]@("-SqlMigrationsDir", $SqlMigrationsDir)) | Out-Null }
if ($SqlFixpacksAutoDir) { $args.AddRange([string[]]@("-SqlFixpacksAutoDir", $SqlFixpacksAutoDir)) | Out-Null }

if ($ApplyGateFixpacks) { $args.Add("-ApplyGateFixpacks") | Out-Null }
if ($VerifyDbContract) { $args.Add("-VerifyDbContract") | Out-Null }

if ($NoBackup) { $args.Add("-NoBackup") | Out-Null }
if ($NoBuild) { $args.Add("-NoBuild") | Out-Null }
if ($NoDeploy) { $args.Add("-NoDeploy") | Out-Null }
if ($NoSmoke) { $args.Add("-NoSmoke") | Out-Null }
if ($NoRollback) { $args.Add("-NoRollback") | Out-Null }

# delegate
$out = & $pwshExe -NoProfile -ExecutionPolicy Bypass -File $main @($args.ToArray()) 2>&1
$code = $LASTEXITCODE

$out | Write-Output
exit $code

