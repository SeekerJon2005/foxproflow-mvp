#requires -Version 7.0
<#
FoxProFlow • SQL Verify Suite Runner
file: scripts/sql/verify/run_verify_suite.ps1

Runs a suite file (list of verify SQL files) by calling run_verify_m0.ps1 per item.

Rules:
- ignores blank lines
- ignores lines starting with '#'
- allows both slashes; normalizes path for execution
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [string]$SuiteFile,

  [string]$PgContainer = "foxproflow-mvp20-postgres-1",
  [string]$PreferProject = "foxproflow-mvp20",
  [string]$PgUser = "admin",
  [string]$PgDb = "foxproflow",

  [switch]$AllowProjectMismatch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path  # repo root from scripts/sql/verify
$suitePath = Resolve-Path $SuiteFile

$lines = Get-Content $suitePath | ForEach-Object { $_.Trim() } | Where-Object {
  $_ -ne "" -and -not $_.StartsWith("#")
}

if ($lines.Count -eq 0) { throw "Suite is empty: $suitePath" }

foreach ($vfRaw in $lines) {
  $vf = $vfRaw -replace '\\','/'   # normalize
  Write-Host "==> VERIFY: $vf"

  $args = @(
    "-NoProfile","-File", (Join-Path $PSScriptRoot "run_verify_m0.ps1"),
    "-PgContainer",$PgContainer,
    "-PreferProject",$PreferProject,
    "-PgUser",$PgUser,
    "-PgDb",$PgDb,
    "-VerifyFile",$vf
  )
  if ($AllowProjectMismatch) { $args += "-AllowProjectMismatch" }

  pwsh @args
  if ($LASTEXITCODE -ne 0) { throw "VERIFY FAIL: $vf" }
}

Write-Host "==> SUITE PASS: $suitePath"
