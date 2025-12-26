#requires -Version 7.0
<#
FoxProFlow • Security Lane • Read-only Preflight (evidence-first)
file: scripts/pwsh/sec/ff-sec-preflight.ps1

Goal:
  - Collect security-relevant facts without changing the system.
  - Produce an evidence pack folder for later audit/sales/pilot kit.
  - Detect obvious misconfigurations that will break secure operations
    (missing keys, insecure defaults, drift signals).

Rules:
  - READ-ONLY: no docker compose up/down, no SQL, no file edits (except writing evidence output).
  - No secret values printed. Only presence/shape checks.
  - Prefer IPv4-safe URLs: http://127.0.0.1:8080

Run:
  pwsh -NoProfile -File .\scripts\pwsh\sec\ff-sec-preflight.ps1
#>

[CmdletBinding()]
param(
  [string]$BaseUrl = $(if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8080" }),
  [string]$ProjectName = $(if ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "foxproflow-mvp20" }),
  [string]$ComposeFile = "",

  [string]$EvidenceRoot = "",
  [int]$TimeoutSec = 10,

  [switch]$JsonOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Now-Stamp { Get-Date -Format "yyyyMMdd_HHmmss" }
function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }

function Ensure-Dir([string]$p) {
  if ([string]::IsNullOrWhiteSpace($p)) { return }
  New-Item -ItemType Directory -Force -Path $p | Out-Null
}

function Join-Url([string]$base, [string]$path) {
  $b = $base.TrimEnd("/")
  $p = $path.TrimStart("/")
  return "$b/$p"
}

function Get-EnvPresence([string]$name) {
  # Always returns a stable object with .present and .length (no secret values printed)
  $v = [Environment]::GetEnvironmentVariable($name)
  if ($null -eq $v) { $v = "" }
  $v = [string]$v
  $t = $v.Trim()
  [pscustomobject]@{
    name    = $name
    present = [bool](-not [string]::IsNullOrWhiteSpace($t))
    length  = [int]($t.Length)
  }
}

function Env-Present([object[]]$checks, [string]$name) {
  $x = $checks | Where-Object { $_.name -eq $name } | Select-Object -First 1
  if ($null -eq $x) { return $false }
  return [bool]$x.present
}

function DcExec([string[]]$args) {
  # Read-only docker compose wrapper, argv-safe.
  $argv = @("compose", "--ansi", "never")
  if (-not [string]::IsNullOrWhiteSpace($ComposeFile)) {
    $argv += @("-f", $ComposeFile)
  }
  if (-not [string]::IsNullOrWhiteSpace($ProjectName)) {
    $argv += @("-p", $ProjectName)
  }
  $argv += $args
  & docker @argv 2>&1
}

function Try-ParseJson([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return $null }
  try { return ($text | ConvertFrom-Json -Depth 64) } catch { return $null }
}

function Shorten([string]$s, [int]$maxLen = 240) {
  if ([string]::IsNullOrWhiteSpace($s)) { return "" }
  $t = ($s.Trim() -replace "\s+"," ")
  if ($t.Length -le $maxLen) { return $t }
  return ($t.Substring(0, $maxLen) + "…")
}

function Invoke-HttpJson([string]$url) {
  $sw = [System.Diagnostics.Stopwatch]::StartNew()

  $body = ""
  $code = 0
  $err  = ""
  $json = $null

  # Prefer curl.exe if present (IPv4 + http1.1 + no proxy), else fallback to Invoke-WebRequest
  $curl = Get-Command curl.exe -ErrorAction SilentlyContinue

  try {
    if ($curl) {
      $tmp = [System.IO.Path]::GetTempFileName()
      try {
        $httpCodeStr = & curl.exe -4 --http1.1 --noproxy 127.0.0.1 `
          -sS -m $TimeoutSec -w "%{http_code}" -o $tmp $url 2>&1

        $m = [regex]::Match($httpCodeStr, "(\d{3})\s*$")
        if ($m.Success) { $code = [int]$m.Groups[1].Value } else { $code = 0 }

        $body = Get-Content -Raw -Path $tmp -ErrorAction SilentlyContinue

        if ($code -eq 0 -and -not [string]::IsNullOrWhiteSpace($httpCodeStr)) {
          $err = $httpCodeStr.Trim()
        }
      } finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $tmp
      }
    } else {
      $resp = Invoke-WebRequest -Uri $url -TimeoutSec $TimeoutSec -SkipHttpErrorCheck
      $code = [int]$resp.StatusCode
      $body = [string]$resp.Content
    }

    $json = Try-ParseJson $body

    $sw.Stop()
    return [pscustomobject]@{
      url       = $url
      http_code = [int]$code
      ok        = [bool]($code -ge 200 -and $code -lt 300)
      ms        = [int]$sw.ElapsedMilliseconds
      err       = $err
      json      = $json
      body_snip = (Shorten $body 240)
    }
  } catch {
    $sw.Stop()
    return [pscustomobject]@{
      url       = $url
      http_code = 0
      ok        = $false
      ms        = [int]$sw.ElapsedMilliseconds
      err       = $_.Exception.Message
      json      = $null
      body_snip = ""
    }
  }
}

# --- Resolve repo root + compose file default ---
$WorktreeRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path

if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
  $ComposeFile = Join-Path $WorktreeRoot "docker-compose.yml"
}
if (-not (Test-Path -LiteralPath $ComposeFile)) {
  throw "ComposeFile not found: $ComposeFile"
}

# --- Evidence folder ---
if ([string]::IsNullOrWhiteSpace($EvidenceRoot)) {
  $EvidenceRoot = Join-Path $WorktreeRoot "ops\_local\evidence"
}
$runId = "sec_preflight_" + (Now-Stamp)
$evDir = Join-Path $EvidenceRoot $runId
Ensure-Dir $evDir

# --- Collect facts ---
$meta = [ordered]@{
  ts            = Now-Iso
  lane          = "security"
  script        = (Resolve-Path $PSCommandPath).Path
  worktree_root = $WorktreeRoot
  compose_file  = $ComposeFile
  compose_project = $ProjectName
  base_url      = $BaseUrl
  timeout_sec   = [int]$TimeoutSec
}

# Env presence (shell-level only; values are never printed)
$envChecks = @(
  Get-EnvPresence "FF_ARCHITECT_KEY",
  Get-EnvPresence "FF_AUTH_TOKEN",
  Get-EnvPresence "POSTGRES_PASSWORD",
  Get-EnvPresence "REDIS_PASSWORD"
)

$securityPostureHints = [ordered]@{
  ff_architect_key_present    = (Env-Present $envChecks "FF_ARCHITECT_KEY")
  ff_auth_token_present       = (Env-Present $envChecks "FF_AUTH_TOKEN")
  postgres_password_present   = (Env-Present $envChecks "POSTGRES_PASSWORD")
  redis_password_present      = (Env-Present $envChecks "REDIS_PASSWORD")
}

# Docker/Compose facts (read-only)
$dockerVersion = ""
try { $dockerVersion = (& docker version 2>&1 | Out-String) } catch { $dockerVersion = "docker version failed: $($_.Exception.Message)" }

$composePs = ""
$composeServices = ""
$composePsOk = $true
try {
  $composePs = DcExec @("ps")
  $composeServices = DcExec @("config", "--services")
} catch {
  $composePsOk = $false
  $composePs = "docker compose ps failed: $($_.Exception.Message)"
  $composeServices = "docker compose config --services failed: $($_.Exception.Message)"
}

# HTTP facts (read-only)
$health  = Invoke-HttpJson (Join-Url $BaseUrl "/health/extended")
$openapi = Invoke-HttpJson (Join-Url $BaseUrl "/openapi.json")

# OpenAPI paths (read-only; no secrets)
$openapiPaths = @()
try {
  if ($openapi.ok -and $openapi.json -and $openapi.json.paths) {
    $openapiPaths = @($openapi.json.paths.PSObject.Properties.Name)
  }
} catch { $openapiPaths = @() }

$securitySurface = [ordered]@{
  has_openapi = [bool]$openapi.ok
  paths_cnt   = [int]$openapiPaths.Count
  paths_security_related = @(
    $openapiPaths |
      Where-Object { $_ -match 'flowsec|sec|auth|policy|immune|autofix|devfactory' } |
      Sort-Object
  )
}

# Risk flags (signals to follow up; no apply)
$riskFlags = New-Object System.Collections.Generic.List[string]
if (-not $composePsOk) { $riskFlags.Add("RISK: docker compose commands failed (compose project may be misconfigured).") | Out-Null }
if (-not $health.ok)   { $riskFlags.Add("RISK: /health/extended not OK (cannot trust runtime posture).") | Out-Null }
if (-not $openapi.ok)  { $riskFlags.Add("RISK: /openapi.json not OK (cannot map API surface).") | Out-Null }

if (-not $securityPostureHints.ff_architect_key_present) {
  $riskFlags.Add("NOTE: FF_ARCHITECT_KEY not present in shell env (may be only in compose env_file/.secrets.env).") | Out-Null
}
if (-not $securityPostureHints.ff_auth_token_present) {
  $riskFlags.Add("NOTE: FF_AUTH_TOKEN not present in shell env (may be only in compose env_file/.secrets.env).") | Out-Null
}

# Build JSON report
$report = [ordered]@{
  meta          = $meta
  env_presence  = $envChecks
  posture_hints = $securityPostureHints
  docker        = [ordered]@{
    version = $dockerVersion
  }
  compose       = [ordered]@{
    ps       = $composePs
    services = $composeServices
    ok       = [bool]$composePsOk
  }
  http = [ordered]@{
    health_extended = $health
    openapi = [ordered]@{
      url       = $openapi.url
      http_code = $openapi.http_code
      ok        = $openapi.ok
      ms        = $openapi.ms
      err       = $openapi.err
    }
  }
  surface     = $securitySurface
  risk_flags  = @($riskFlags.ToArray())
}

# Write artifacts
$reportPath = Join-Path $evDir "sec_preflight_report.json"
($report | ConvertTo-Json -Depth 64) | Set-Content -LiteralPath $reportPath -Encoding utf8NoBOM

Set-Content -LiteralPath (Join-Path $evDir "docker_version.txt") -Value ($dockerVersion | Out-String) -Encoding utf8NoBOM
Set-Content -LiteralPath (Join-Path $evDir "compose_ps.txt") -Value ($composePs | Out-String) -Encoding utf8NoBOM
Set-Content -LiteralPath (Join-Path $evDir "compose_services.txt") -Value ($composeServices | Out-String) -Encoding utf8NoBOM

# Save health (full JSON if parseable)
if ($health.json) {
  ($health.json | ConvertTo-Json -Depth 64) | Set-Content -LiteralPath (Join-Path $evDir "health_extended.json") -Encoding utf8NoBOM
} else {
  Set-Content -LiteralPath (Join-Path $evDir "health_extended_snip.txt") -Value ($health.body_snip) -Encoding utf8NoBOM
}

# Save OpenAPI full JSON + paths list (safe; no secrets)
if ($openapi.ok) {
  # Re-fetch raw (already in body_snip only). We keep parsed data, but also best-effort store full doc.
  # If curl is available, fetch raw; else store parsed JSON only.
  $raw = ""
  try {
    $curl2 = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl2) {
      $raw = & curl.exe -4 --http1.1 --noproxy 127.0.0.1 -sS -m $TimeoutSec (Join-Url $BaseUrl "/openapi.json") 2>$null
    }
  } catch { $raw = "" }

  if (-not [string]::IsNullOrWhiteSpace($raw)) {
    Set-Content -LiteralPath (Join-Path $evDir "openapi.json") -Value $raw -Encoding utf8NoBOM
  } elseif ($openapi.json) {
    ($openapi.json | ConvertTo-Json -Depth 64) | Set-Content -LiteralPath (Join-Path $evDir "openapi.json") -Encoding utf8NoBOM
  }
}

if ($openapiPaths.Count -gt 0) {
  ($openapiPaths | Sort-Object) | Set-Content -LiteralPath (Join-Path $evDir "openapi_paths.txt") -Encoding utf8NoBOM
}

# Print summary
$summaryOk = [bool]($composePsOk -and $health.ok -and $openapi.ok)

$summary = [ordered]@{
  ok          = $summaryOk
  evidence_dir = $evDir
  report      = $reportPath
  risk_flags  = @($riskFlags.ToArray())
}

if ($JsonOnly) {
  ($summary | ConvertTo-Json -Depth 16) | Write-Output
} else {
  Write-Host "[SEC PREFLIGHT] ok=$($summary.ok)" -ForegroundColor $(if ($summary.ok) { "Green" } else { "Yellow" })
  Write-Host "[SEC PREFLIGHT] evidence: $($summary.evidence_dir)"
  Write-Host "[SEC PREFLIGHT] report:   $($summary.report)"
  if ($summary.risk_flags.Count -gt 0) {
    Write-Host "[SEC PREFLIGHT] flags:" -ForegroundColor Yellow
    $summary.risk_flags | ForEach-Object { Write-Host ("  - {0}" -f $_) -ForegroundColor Yellow }
  }
}

if ($summaryOk) { exit 0 }
if (-not $composePsOk) { exit 3 }
exit 2
