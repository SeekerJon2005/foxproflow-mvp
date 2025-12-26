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

[CmdletBinding(PositionalBinding=$false)]
param(
  [switch]$CaptureOnFail = $true,

  [int]$ContextSinceHours = 24,
  [string]$ApiBase = "http://127.0.0.1:8080",
  [string]$ComposeFile = (Join-Path (Get-Location).Path "docker-compose.yml"),

  [switch]$ContextIncludeDockerLogs,
  [switch]$ContextIncludeEnvSnapshot,
  [switch]$ContextOpenOutDir,

  [int]$ContextDockerLogsTail = 250,
  [string[]]$ContextDockerLogServices = @("api","worker","beat"),

  [Parameter(ValueFromRemainingArguments=$true)]
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
& $pwshExe -NoProfile -File $inner @PassThruArgs
$exitCode = $LASTEXITCODE

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

# Scoreboard (best effort)
$scoreScript = Join-Path $PSScriptRoot "ff-flowmeta-scoreboard.ps1"
if (Test-Path $scoreScript) {
  try {
    & $scoreScript -SinceHours $ContextSinceHours -ApiBase $ApiBase -ComposeFile $ComposeFile | Out-Null
    Write-Info "Scoreboard saved: $(Join-Path (Get-Location).Path '_flowmeta\latest_scoreboard.json')"
  } catch {
    Write-Warn "Scoreboard failed: $($_.Exception.Message)"
  }
} else {
  Write-Warn "Scoreboard script not found: $scoreScript"
}

# Context Pack (best effort)
$ctxScript = Join-Path $PSScriptRoot "ff-context-pack.ps1"
if (Test-Path $ctxScript) {
  try {
    $ctxArgs = @(
      "-SinceHours", "$ContextSinceHours",
      "-ApiBase", $ApiBase,
      "-ComposeFile", $ComposeFile,
      "-DockerLogsTail", "$ContextDockerLogsTail"
    )

    if ($ContextDockerLogServices -and $ContextDockerLogServices.Count -gt 0) {
      $ctxArgs += @("-DockerLogServices") + $ContextDockerLogServices
    }
    if ($ContextIncludeDockerLogs) { $ctxArgs += "-IncludeDockerLogs" }
    if ($ContextIncludeEnvSnapshot) { $ctxArgs += "-IncludeEnvSnapshot" }
    if ($ContextOpenOutDir) { $ctxArgs += "-OpenOutDir" }

    $out = & $ctxScript @ctxArgs 2>&1

    $zipPath = $null
    $runDir = $null

    $zipLine = $out | Where-Object { $_ -match '^Zip:\s*' } | Select-Object -Last 1
    if ($zipLine -and ($zipLine -match '^Zip:\s*(.+)$')) { $zipPath = $Matches[1] }

    $runLine = $out | Where-Object { $_ -match '^RunDir:\s*' } | Select-Object -Last 1
    if ($runLine -and ($runLine -match '^RunDir:\s*(.+)$')) { $runDir = $Matches[1] }

    if ($runDir)  { Write-Info "ContextPack RunDir: $runDir" }
    if ($zipPath) { Write-Info "ContextPack Zip:    $zipPath" }
    if (-not $zipPath) { Write-Warn "ContextPack done, but zip path not parsed (see output above)." }
  } catch {
    Write-Warn "ContextPack failed: $($_.Exception.Message)"
  }
} else {
  Write-Warn "Context pack script not found: $ctxScript"
}

exit $exitCode
