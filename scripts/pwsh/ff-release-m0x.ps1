#requires -Version 7.0
<#
FoxProFlow RUN • Release Gate M0 wrapper (FlowMeta evidence on failure)
file: scripts/pwsh/ff-release-m0x.ps1

Goal:
  Run ff-release-m0.ps1 in a child pwsh process, and if it fails:
    - capture FlowMeta scoreboard
    - capture Context Pack (optional docker logs/env snapshot)

Why child pwsh:
  If ff-release-m0.ps1 uses 'exit', it would terminate the caller script.
  Child pwsh isolates that and allows evidence capture after failure.

Usage example:
  $rid = "m0_" + (Get-Date -Format "yyyyMMdd_HHmmss")
  pwsh -NoProfile -File .\scripts\pwsh\ff-release-m0x.ps1 -ContextIncludeDockerLogs `
    -ReleaseId $rid -NoBackup -NoBuild -NoDeploy -NoSmoke -MigrateMode sql_dirs -ApplyGateFixpacks -VerifyDbContract

Notes:
  - Wrapper params are OPTIONAL.
  - All unknown params are passed through to ff-release-m0.ps1.
#>

[CmdletBinding(PositionalBinding = $false)]
param(
  [switch]$CaptureOnFail = $true,

  [int]$ContextSinceHours = 24,
  [string]$ApiBase = "http://127.0.0.1:8080",
  [string]$ComposeFile = (Join-Path (Get-Location).Path "docker-compose.yml"),

  [switch]$ContextIncludeDockerLogs,
  [switch]$ContextIncludeEnvSnapshot,
  [switch]$ContextOpenOutDir,

  [int]$ContextDockerLogsTail = 250,
  [string[]]$ContextDockerLogServices = @("api", "worker", "beat"),

  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$PassThruArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string]$msg) { Write-Host "[M0X] $msg" -ForegroundColor Cyan }
function Write-Warn([string]$msg) { Write-Host "[M0X][WARN] $msg" -ForegroundColor Yellow }

$pwshExe = (Get-Command pwsh -ErrorAction Stop).Source
$inner = Join-Path $PSScriptRoot "ff-release-m0.ps1"
if (-not (Test-Path $inner)) { throw "Inner script not found: $inner" }

Write-Info "Inner: $inner"
Write-Info "CaptureOnFail: $CaptureOnFail"
Write-Info "PassThruArgs: $($PassThruArgs.Count)"

# Run inner gate in child pwsh to survive 'exit' inside ff-release-m0.ps1
$exitCode = 1
try {
  & $pwshExe -NoProfile -File $inner @PassThruArgs
  $exitCode = $LASTEXITCODE
  if ($null -eq $exitCode) { $exitCode = 1 }
} catch {
  Write-Warn "Inner execution failed: $($_.Exception.Message)"
  $exitCode = 1
}

if ($exitCode -eq 0) {
  Write-Info "Release gate OK (exitCode=0)."
  exit 0
}

Write-Warn "Release gate FAILED (exitCode=$exitCode)."

if (-not $CaptureOnFail) {
  Write-Warn "CaptureOnFail disabled -> skipping evidence capture."
  exit $exitCode
}

Write-Info "Capturing FlowMeta evidence..."

# -------------------------
# Scoreboard (best effort)
# -------------------------
$scoreScript = Join-Path $PSScriptRoot "ff-flowmeta-scoreboard.ps1"
if (Test-Path $scoreScript) {
  try {
    # Let scoreboard decide how to query health. We just pass parameters.
    & $scoreScript -SinceHours $ContextSinceHours -ApiBase $ApiBase -ComposeFile $ComposeFile | Out-Null

    $scoreLatest = Join-Path (Get-Location).Path "_flowmeta\latest_scoreboard.json"
    if (Test-Path $scoreLatest) {
      Write-Info "Scoreboard saved: $scoreLatest"
    } else {
      Write-Warn "Scoreboard ran, but latest file not found: $scoreLatest"
    }
  } catch {
    Write-Warn "Scoreboard failed: $($_.Exception.Message)"
  }
} else {
  Write-Warn "Scoreboard script not found: $scoreScript"
}

# -------------------------
# Context Pack (best effort)
# -------------------------
$ctxScript = Join-Path $PSScriptRoot "ff-context-pack.ps1"
if (Test-Path $ctxScript) {
  try {
    # IMPORTANT FIX:
    # Do NOT pass parameter names as strings in an array (PowerShell treats them as positional values).
    # Use splatting (hashtable) to bind by parameter name correctly.
    $ctxOutDir = Join-Path (Get-Location).Path "_contextpacks"

    $ctxSplat = @{
      SinceHours        = $ContextSinceHours
      ApiBase           = $ApiBase
      ComposeFile       = $ComposeFile
      OutDir            = $ctxOutDir
      DockerLogsTail    = $ContextDockerLogsTail
      DockerLogServices = $ContextDockerLogServices
    }

    if ($ContextIncludeDockerLogs)  { $ctxSplat["IncludeDockerLogs"]  = $true }
    if ($ContextIncludeEnvSnapshot) { $ctxSplat["IncludeEnvSnapshot"] = $true }
    if ($ContextOpenOutDir)         { $ctxSplat["OpenOutDir"]         = $true }

    # We don't rely on capturing Write-Host output from ff-context-pack.ps1;
    # instead, we locate the newest artifacts in OutDir after execution.
    & $ctxScript @ctxSplat | Out-Null

    $zip = $null
    $dir = $null

    if (Test-Path $ctxOutDir) {
      $zip = Get-ChildItem -Path $ctxOutDir -File -Filter "ctx_*.zip" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1

      $dir = Get-ChildItem -Path $ctxOutDir -Directory -Filter "ctx_*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    }

    if ($dir) { Write-Info "ContextPack RunDir: $($dir.FullName)" }
    if ($zip) { Write-Info "ContextPack Zip:    $($zip.FullName)" }

    if (-not $zip) {
      Write-Warn "ContextPack finished, but no ctx_*.zip found in: $ctxOutDir"
    }
  } catch {
    Write-Warn "ContextPack failed: $($_.Exception.Message)"
  }
} else {
  Write-Warn "Context pack script not found: $ctxScript"
}

exit $exitCode
