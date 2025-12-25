#requires -Version 7.0
<#
FoxProFlow • Smoke M0
file: scripts/pwsh/ff-smoke-m0.ps1

Compatibility:
- Accepts -ReportPath (used by ff-release-m0.ps1)
- Writes JSON report to ReportPath (or stdout if not provided)

Checks (strict):
- GET /health/extended -> ready=true
- GET /api/crm/smoke/ping -> ok=true
- GET /api/devfactory/orders/recent?limit=1&include_result=0 -> ok=true

Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$BaseUrl = "http://127.0.0.1:8080",

  [ValidateSet("strict","soft","off")]
  [string]$KpiMode = "strict",

  [string]$ReportPath = "",

  [int]$TimeoutSec = 12,

  [string]$ArchitectKey = $(if ($env:FF_ARCHITECT_KEY) { $env:FF_ARCHITECT_KEY } else { "" })
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }

function Curl-Get([string]$url, [string[]]$headers, [int]$timeoutSec) {
  $tmp = New-TemporaryFile
  try {
    $h = @()
    foreach ($x in ($headers ?? @())) { $h += @("-H", $x) }

    $httpCodeStr = & curl.exe -4 --http1.1 --noproxy 127.0.0.1 -sS -m $timeoutSec -w "%{http_code}" -o $tmp.FullName @h $url 2>&1
    $body = Get-Content -Raw -ErrorAction SilentlyContinue $tmp.FullName
    $m = [regex]::Match(($httpCodeStr | Out-String), "(\d{3})\s*$")
    $code = if ($m.Success) { [int]$m.Groups[1].Value } else { 0 }
    return [pscustomobject]@{ code=$code; body=$body; raw=($httpCodeStr|Out-String) }
  } finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $tmp.FullName
  }
}

function Add-Check([System.Collections.Generic.List[object]]$arr, [string]$name, [bool]$ok, [int]$code, [string]$url, [string]$note) {
  $arr.Add([pscustomobject]@{
    name = $name
    ok = $ok
    http_code = $code
    url = $url
    ts = Now-Iso
    note = $note
  }) | Out-Null
}

$BaseUrl = $BaseUrl.TrimEnd("/")
if ($BaseUrl -match "localhost") { $BaseUrl = $BaseUrl -replace "localhost","127.0.0.1" }

$hdr = @()
if ($ArchitectKey) {
  $hdr += "X-Architect-Key: $ArchitectKey"
  $hdr += "X-FF-Architect-Key: $ArchitectKey"
  $hdr += "Authorization: Bearer $ArchitectKey"
}

$checks = New-Object "System.Collections.Generic.List[object]"
$ok = $true

if ($KpiMode -eq "off") {
  $report = [pscustomobject]@{
    smoke = "m0"
    mode = $KpiMode
    ts = Now-Iso
    base_url = $BaseUrl
    ok = $true
    checks = @()
    note = "KpiMode=off"
  }
  $json = $report | ConvertTo-Json -Depth 50
  if ($ReportPath) {
    Ensure-Dir (Split-Path $ReportPath -Parent)
    $json | Set-Content -LiteralPath $ReportPath -Encoding utf8NoBOM
  } else {
    $json
  }
  exit 0
}

# 1) health/extended
try {
  $u = "$BaseUrl/health/extended"
  $r = Curl-Get -url $u -headers $hdr -timeoutSec $TimeoutSec
  if ($r.code -ge 200 -and $r.code -lt 300) {
    $ready = $false
    try { $j = $r.body | ConvertFrom-Json -Depth 64; $ready = ($j.ready -eq $true) } catch { }
    if ($ready) {
      Add-Check $checks "health_extended_ready" $true $r.code $u "ready=true"
    } else {
      $ok = $false
      Add-Check $checks "health_extended_ready" $false $r.code $u "ready!=true"
    }
  } else {
    $ok = $false
    Add-Check $checks "health_extended_ready" $false $r.code $u "bad http"
  }
} catch {
  $ok = $false
  Add-Check $checks "health_extended_ready" $false 0 "$BaseUrl/health/extended" ("exception: {0}" -f $_.Exception.Message)
}

# 2) CRM smoke ping
try {
  $u = "$BaseUrl/api/crm/smoke/ping"
  $r = Curl-Get -url $u -headers $hdr -timeoutSec $TimeoutSec
  if ($r.code -ge 200 -and $r.code -lt 300) {
    $pass = $false
    try { $j = $r.body | ConvertFrom-Json -Depth 32; $pass = ($j.ok -eq $true) } catch { }
    if ($pass) {
      Add-Check $checks "crm_smoke_ping" $true $r.code $u "ok=true"
    } else {
      $ok = $false
      Add-Check $checks "crm_smoke_ping" $false $r.code $u "ok!=true"
    }
  } else {
    $ok = $false
    Add-Check $checks "crm_smoke_ping" $false $r.code $u "bad http"
  }
} catch {
  $ok = $false
  Add-Check $checks "crm_smoke_ping" $false 0 "$BaseUrl/api/crm/smoke/ping" ("exception: {0}" -f $_.Exception.Message)
}

# 3) DevFactory orders recent
try {
  $u = "$BaseUrl/api/devfactory/orders/recent?limit=1&include_result=0"
  $r = Curl-Get -url $u -headers $hdr -timeoutSec $TimeoutSec
  if ($r.code -ge 200 -and $r.code -lt 300) {
    $pass = $false
    try { $j = $r.body | ConvertFrom-Json -Depth 64; $pass = ($j.ok -eq $true) } catch { }
    if ($pass) {
      Add-Check $checks "devfactory_orders_recent" $true $r.code $u "ok=true"
    } else {
      if ($KpiMode -eq "strict") { $ok = $false }
      Add-Check $checks "devfactory_orders_recent" $false $r.code $u "ok!=true"
    }
  } else {
    if ($KpiMode -eq "strict") { $ok = $false }
    Add-Check $checks "devfactory_orders_recent" $false $r.code $u "bad http"
  }
} catch {
  if ($KpiMode -eq "strict") { $ok = $false }
  Add-Check $checks "devfactory_orders_recent" $false 0 "$BaseUrl/api/devfactory/orders/recent?limit=1&include_result=0" ("exception: {0}" -f $_.Exception.Message)
}

$report = [pscustomobject]@{
  smoke = "m0"
  mode = $KpiMode
  ts = Now-Iso
  base_url = $BaseUrl
  ok = $ok
  checks = @($checks.ToArray())
}

$json = $report | ConvertTo-Json -Depth 80
if ($ReportPath) {
  Ensure-Dir (Split-Path $ReportPath -Parent)
  $json | Set-Content -LiteralPath $ReportPath -Encoding utf8NoBOM
} else {
  $json
}

if ($ok) { exit 0 } else { exit 1 }
