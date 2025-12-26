#requires -Version 7.0
<#
FoxProFlow • FlowMeta utility
file: scripts/pwsh/ff-context-pack.ps1

Goal:
  Create a safe-by-default "Context Pack" for debugging:
    - git status/log/diffstat
    - docker compose ps
    - API health endpoints (IPv4 base)
  Optionally:
    - docker compose logs (explicit switch)
    - env snapshot (names only; values redacted; explicit switch)

Outputs:
  - run folder in <OutDir>\<rid>\
  - zip archive <OutDir>\<rid>.zip

Principles:
  - deny-by-default for secrets
  - degradable: if docker/api/git not available, capture errors and continue
#>

[CmdletBinding()]
param(
  [int]$SinceHours = 24,

  [string]$ApiBase = "http://127.0.0.1:8080",

  [string]$OutDir = (Join-Path (Get-Location).Path "_contextpacks"),

  [string]$ComposeFile = (Join-Path (Get-Location).Path "docker-compose.yml"),

  [int]$DockerLogsTail = 250,

  [string[]]$DockerLogServices = @("api", "worker", "beat"),

  [switch]$IncludeDockerLogs,

  [switch]$IncludeEnvSnapshot,

  [switch]$OpenOutDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string]$msg) { Write-Host "[CTX] $msg" -ForegroundColor Cyan }
function Write-Warn([string]$msg) { Write-Host "[CTX][WARN] $msg" -ForegroundColor Yellow }

function Ensure-Dir([string]$path) {
  New-Item -ItemType Directory -Path $path -Force | Out-Null
}

function Save-Text([string]$path, [string[]]$lines) {
  $dir = Split-Path -Parent $path
  if ($dir) { Ensure-Dir $dir }
  $lines | Out-File -FilePath $path -Encoding utf8
}

function Save-CommandOutput([string]$path, [scriptblock]$cmd) {
  try {
    $out = & $cmd 2>&1
    if ($null -eq $out) { $out = @() }
    Save-Text -path $path -lines $out
  } catch {
    Save-Text -path $path -lines @("ERROR: $($_.Exception.Message)")
  }
}

function Try-HttpGetJson([string]$url, [string]$outFile) {
  try {
    $obj = Invoke-RestMethod -Method Get -Uri $url -TimeoutSec 8
    ($obj | ConvertTo-Json -Depth 50) | Out-File -FilePath $outFile -Encoding utf8
  } catch {
    Save-Text -path $outFile -lines @("ERROR: $($_.Exception.Message)", "URL: $url")
  }
}

function Get-EnvSnapshot() {
  # Safe-by-default: values always redacted. We store presence + length only.
  $items = Get-ChildItem env: | Sort-Object Name
  $snap = foreach ($i in $items) {
    $val = [string]$i.Value
    [pscustomobject]@{
      name     = $i.Name
      present  = $true
      length   = $val.Length
      value    = "<redacted>"
    }
  }
  return $snap
}

$rid = "ctx_" + (Get-Date -Format "yyyyMMdd_HHmmss")
Ensure-Dir $OutDir
$runDir = Join-Path $OutDir $rid
Ensure-Dir $runDir

Write-Info "Context Pack RID: $rid"
Write-Info "OutDir: $OutDir"
Write-Info "RunDir: $runDir"

$meta = [ordered]@{
  rid                 = $rid
  created_utc         = (Get-Date).ToUniversalTime().ToString("o")
  created_local       = (Get-Date).ToString("o")
  cwd                 = (Get-Location).Path
  ps_version          = $PSVersionTable.PSVersion.ToString()
  user                = $env:USERNAME
  computer            = $env:COMPUTERNAME
  since_hours         = $SinceHours
  api_base            = $ApiBase
  compose_file        = $ComposeFile
  include_docker_logs = [bool]$IncludeDockerLogs
  include_env_snapshot= [bool]$IncludeEnvSnapshot
}

($meta | ConvertTo-Json -Depth 10) | Out-File -FilePath (Join-Path $runDir "meta.json") -Encoding utf8

# --- Host info (best effort)
Save-CommandOutput (Join-Path $runDir "host.txt") {
  @(
    "DateLocal:  " + (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "DateUTC:    " + (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss")
    "PSVersion:  " + $PSVersionTable.PSVersion.ToString()
    "OS:         " + [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
    "Arch:       " + [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    "Machine:    " + $env:COMPUTERNAME
    "User:       " + $env:USERNAME
    "CWD:        " + (Get-Location).Path
  )
}

# --- Git (best effort)
Save-CommandOutput (Join-Path $runDir "git_status.txt") { git status -sb }
Save-CommandOutput (Join-Path $runDir "git_log_10.txt") { git log -10 --oneline }
Save-CommandOutput (Join-Path $runDir "git_diff_stat.txt") { git diff --stat }

# --- Docker compose ps (best effort)
Save-CommandOutput (Join-Path $runDir "docker_compose_ps.txt") { docker compose --ansi never -f $ComposeFile ps -a }

# --- API health (best effort)
Try-HttpGetJson -url ("$ApiBase/health") -outFile (Join-Path $runDir "api_health.json")
Try-HttpGetJson -url ("$ApiBase/health/extended") -outFile (Join-Path $runDir "api_health_extended.json")

# --- Optional: docker logs (explicit)
if ($IncludeDockerLogs) {
  Write-Info "Including docker compose logs (tail=$DockerLogsTail) for: $($DockerLogServices -join ', ')"
  foreach ($svc in $DockerLogServices) {
    $p = Join-Path $runDir ("docker_logs_{0}.txt" -f $svc)
    Save-CommandOutput $p { docker compose --ansi never -f $ComposeFile logs --no-color --tail $DockerLogsTail $svc }
  }
} else {
  Write-Info "Docker logs: skipped (use -IncludeDockerLogs to include)."
}

# --- Optional: env snapshot (explicit; values redacted)
if ($IncludeEnvSnapshot) {
  Write-Info "Including env snapshot (values redacted)."
  try {
    $snap = Get-EnvSnapshot
    ($snap | ConvertTo-Json -Depth 5) | Out-File -FilePath (Join-Path $runDir "env_snapshot.json") -Encoding utf8
  } catch {
    Save-Text -path (Join-Path $runDir "env_snapshot.json") -lines @("ERROR: $($_.Exception.Message)")
  }
} else {
  Write-Info "Env snapshot: skipped (use -IncludeEnvSnapshot to include)."
}

# --- Files manifest (sha256)
try {
  $files = Get-ChildItem -Path $runDir -File -Recurse
  $manifest = foreach ($f in $files) {
    $rel = $f.FullName.Substring($runDir.Length).TrimStart("\","/").Replace("\","/")
    [pscustomobject]@{
      path   = $rel
      bytes  = $f.Length
      sha256 = (Get-FileHash -Algorithm SHA256 -Path $f.FullName).Hash
    }
  }
  ($manifest | ConvertTo-Json -Depth 5) | Out-File -FilePath (Join-Path $runDir "manifest_files.json") -Encoding utf8
} catch {
  Write-Warn "Manifest hash failed: $($_.Exception.Message)"
}

# --- Zip it
$zipPath = Join-Path $OutDir ("{0}.zip" -f $rid)
try {
  if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
  Compress-Archive -Path (Join-Path $runDir "*") -DestinationPath $zipPath -Force
  Write-Info "ZIP created: $zipPath"
} catch {
  Write-Warn "ZIP failed: $($_.Exception.Message)"
}

if ($OpenOutDir) {
  try { Invoke-Item $OutDir } catch { }
}

Write-Host ""
Write-Host "DONE." -ForegroundColor Green
Write-Host ("RunDir: {0}" -f $runDir)
Write-Host ("Zip:    {0}" -f $zipPath)
