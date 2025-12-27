#requires -Version 7.0
<#
FoxProFlow RUN • Scheduled weekly restore-drill wrapper
file: scripts/pwsh/ff-sched-weekly-restore-drill.ps1

Purpose:
  - run ff-restore-drill.ps1 from a stable working directory
  - append lightweight scheduler log (local-only)

Local log:
  ops/_local/evidence/_scheduler/weekly_restore_drill.log

Created by: Архитектор Яцков Евгений Анатольевич
Lane: A-RUN only
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function NowIso() { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function EnsureDir([string]$p) { if (-not (Test-Path -LiteralPath $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }

# repo root = ...\scripts\pwsh -> ..\..
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$SchedDir = Join-Path $RepoRoot "ops\_local\evidence\_scheduler"
EnsureDir $SchedDir
$SchedLog = Join-Path $SchedDir "weekly_restore_drill.log"

Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value ("`n=== {0} weekly_restore_drill start ===" -f (NowIso))
Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value ("repo=" + $RepoRoot)

# best-effort git head
try {
  $head = (& git rev-parse HEAD 2>$null | Out-String).Trim()
  if ($head) { Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value ("git_head=" + $head) }
} catch {}

if ($DryRun) {
  Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value ("dry_run=true")
  Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value ("=== {0} end (dry) ===" -f (NowIso))
  exit 0
}

# docker availability check (fail fast)
$dockerInfo = & docker info 2>&1
if ($LASTEXITCODE -ne 0) {
  Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value ("docker_info_exit=" + $LASTEXITCODE)
  Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value (($dockerInfo | Out-String).TrimEnd())
  Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value ("=== {0} end (FAIL: docker) ===" -f (NowIso))
  exit 2
}

$DrillScript = Join-Path $RepoRoot "scripts\pwsh\ff-restore-drill.ps1"
if (-not (Test-Path -LiteralPath $DrillScript)) {
  Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value ("missing_script=" + $DrillScript)
  Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value ("=== {0} end (FAIL: missing script) ===" -f (NowIso))
  exit 3
}

# run restore-drill (it will create its own evidence folder)
& pwsh -NoProfile -File $DrillScript 2>&1 | Tee-Object -FilePath $SchedLog -Append | Out-Null
$rc = $LASTEXITCODE

Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value ("exit_code=" + $rc)
Add-Content -LiteralPath $SchedLog -Encoding UTF8 -Value ("=== {0} end ===" -f (NowIso))

exit $rc
