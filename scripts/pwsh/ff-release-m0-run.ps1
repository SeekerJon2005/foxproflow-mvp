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
  [Alias("ProjectName")]
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

# Silence docker compose warnings about missing pgAdmin env vars (local-only; no compose/env changes)
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_EMAIL))    { $env:PGADMIN_EMAIL    = "disabled@local" }
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_PASSWORD)) { $env:PGADMIN_PASSWORD = "disabled" }

function Repo-Root {
  (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

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
  # normalize trailing slash
  while ($u.EndsWith("/")) { $u = $u.Substring(0, $u.Length - 1) }
  # keep strict: expect http(s)
  if ($u -notmatch '^https?://') {
    throw "BaseUrl must start with http:// or https://, got: $u"
  }
  return $u
}

function Normalize-ReleaseId([string]$rid) {
  if ([string]::IsNullOrWhiteSpace($rid)) { return $rid }
  $rid = $rid.Trim()
  # keep docker-tag + filename safe: [A-Za-z0-9_.-]
  $rid = ($rid -replace '[^A-Za-z0-9_.-]', '_').Trim('_')
  if ([string]::IsNullOrWhiteSpace($rid)) { throw "ReleaseId sanitized to empty. Provide a valid ReleaseId." }
  return $rid
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
if (-not (Test-Path -LiteralPath $main)) {
  throw "Missing main script: $main"
}

if ($ArchitectKey) { $env:FF_ARCHITECT_KEY = $ArchitectKey }

$pwshExe = Get-PwshExe

Write-Verbose ("RepoRoot: {0}" -f $repoRoot)
Write-Verbose ("ComposeFile: {0}" -f $ComposeFile)
Write-Verbose ("ProjectName: {0}" -f $PreferProject)
Write-Verbose ("BaseUrl: {0}" -f $BaseUrl)
Write-Verbose ("ReleaseId: {0}" -f $ReleaseId)
Write-Verbose ("Main: {0}" -f $main)

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

if ($MigrateMode)       { $args.AddRange([string[]]@("-MigrateMode", $MigrateMode)) | Out-Null }
if ($MigrateScript)     { $args.AddRange([string[]]@("-MigrateScript", $MigrateScript)) | Out-Null }
if ($SqlMigrationsDir)  { $args.AddRange([string[]]@("-SqlMigrationsDir", $SqlMigrationsDir)) | Out-Null }
if ($SqlFixpacksAutoDir){ $args.AddRange([string[]]@("-SqlFixpacksAutoDir", $SqlFixpacksAutoDir)) | Out-Null }

if ($ApplyGateFixpacks) { $args.Add("-ApplyGateFixpacks") | Out-Null }
if ($VerifyDbContract)  { $args.Add("-VerifyDbContract")  | Out-Null }

if ($NoBackup)   { $args.Add("-NoBackup")   | Out-Null }
if ($NoBuild)    { $args.Add("-NoBuild")    | Out-Null }
if ($NoDeploy)   { $args.Add("-NoDeploy")   | Out-Null }
if ($NoSmoke)    { $args.Add("-NoSmoke")    | Out-Null }
if ($NoRollback) { $args.Add("-NoRollback") | Out-Null }

Write-Verbose ("Delegate: {0} -NoProfile -ExecutionPolicy Bypass -File `"{1}`" <args...>" -f $pwshExe, $main)

# delegate (stream output; preserve exit code)
& $pwshExe -NoProfile -ExecutionPolicy Bypass -File $main @($args.ToArray()) 2>&1
$code = $LASTEXITCODE
exit $code
