#requires -Version 7.0
<#
FoxProFlow • DevFactory commercial smoke (C0)
file: scripts/pwsh/ff-smoke-devfactory-commercial.ps1

Non-disruptive checks:
  - GET /health/extended (ready=true)
  - GET /api/crm/smoke/ping
  - GET /api/devfactory/orders/recent?limit=1&include_result=0   (must exist)

Writes JSON report to EvidenceDir (if provided).

Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$BaseUrl = "http://127.0.0.1:8080",
  [string]$ArchitectKey = $(if ($env:FF_ARCHITECT_KEY) { $env:FF_ARCHITECT_KEY } else { "" }),
  [string]$EvidenceDir = "",
  [int]$TimeoutSec = 12
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }

function Invoke-Curl([string]$url, [string[]]$headers, [int]$timeoutSec) {
  $tmp = New-TemporaryFile
  try {
    $h = @()
    foreach ($x in ($headers ?? @())) { $h += @("-H", $x) }

    $httpCodeStr = & curl.exe -4 --http1.1 --noproxy 127.0.0.1 -sS -m $timeoutSec -w "%{http_code}" -o $tmp.FullName @h $url 2>&1
    $body = Get-Content -Raw -ErrorAction SilentlyContinue $tmp.FullName

    $m = [regex]::Match(($httpCodeStr | Out-String), "(\d{3})\s*$")
    $code = if ($m.Success) { [int]$m.Groups[1].Value } else { 0 }

    return [pscustomobject]@{ code=$code; body=$body; raw=($httpCodeStr | Out-String) }
  } finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $tmp.FullName
  }
}

$BaseUrl = $BaseUrl.TrimEnd("/")
if ($BaseUrl -match "localhost") { $BaseUrl = $BaseUrl -replace "localhost","127.0.0.1" }

$hdr = @()
if ($ArchitectKey) {
  $hdr += "X-Architect-Key: $ArchitectKey"
  $hdr += "X-FF-Architect-Key: $ArchitectKey"
  $hdr += "Authorization: Bearer $ArchitectKey"
}

$checks = New-Object System.Collections.Generic.List[object]
$ok = $true

function Add-CheckResult([string]$name, [bool]$pass, [int]$code, [string]$url, [string]$note) {
  $checks.Add([pscustomobject]@{
    name = $name
    ok = $pass
    http_code = $code
    url = $url
    ts = Now-Iso
    note = $note
  }) | Out-Null
}

# 1) health/extended
try {
  $u = "$BaseUrl/health/extended"
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $r = Invoke-Curl -url $u -headers $hdr -timeoutSec $TimeoutSec
  $sw.Stop()

  if ($r.code -ge 200 -and $r.code -lt 300) {
    $ready = $false
    try { $j = $r.body | ConvertFrom-Json -Depth 64; $ready = ($j.ready -eq $true) } catch { }
    if ($ready) {
      Add-CheckResult "health_extended_ready" $true $r.code $u ("ms={0}" -f $sw.ElapsedMilliseconds)
    } else {
      $ok = $false
      Add-CheckResult "health_extended_ready" $false $r.code $u ("ready!=true; ms={0}" -f $sw.ElapsedMilliseconds)
    }
  } else {
    $ok = $false
    Add-CheckResult "health_extended_ready" $false $r.code $u ("bad http; ms={0}" -f $sw.ElapsedMilliseconds)
  }
} catch {
  $ok = $false
  Add-CheckResult "health_extended_ready" $false 0 "$BaseUrl/health/extended" ("exception: {0}" -f $_.Exception.Message)
}

# 2) CRM smoke ping
try {
  $u = "$BaseUrl/api/crm/smoke/ping"
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $r = Invoke-Curl -url $u -headers $hdr -timeoutSec $TimeoutSec
  $sw.Stop()

  if ($r.code -ge 200 -and $r.code -lt 300) {
    $pass = $false
    try { $j = $r.body | ConvertFrom-Json -Depth 32; $pass = ($j.ok -eq $true) } catch { }
    if ($pass) {
      Add-CheckResult "crm_smoke_ping" $true $r.code $u ("ms={0}" -f $sw.ElapsedMilliseconds)
    } else {
      $ok = $false
      Add-CheckResult "crm_smoke_ping" $false $r.code $u ("ok!=true; ms={0}" -f $sw.ElapsedMilliseconds)
    }
  } else {
    $ok = $false
    Add-CheckResult "crm_smoke_ping" $false $r.code $u ("bad http; ms={0}" -f $sw.ElapsedMilliseconds)
  }
} catch {
  $ok = $false
  Add-CheckResult "crm_smoke_ping" $false 0 "$BaseUrl/api/crm/smoke/ping" ("exception: {0}" -f $_.Exception.Message)
}

# 3) DevFactory orders vitrine (required)
try {
  $u = "$BaseUrl/api/devfactory/orders/recent?limit=1&include_result=0"
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $r = Invoke-Curl -url $u -headers $hdr -timeoutSec $TimeoutSec
  $sw.Stop()

  if ($r.code -eq 401 -or $r.code -eq 403) {
    $ok = $false
    $note = $ArchitectKey ? "auth denied with provided ArchitectKey" : "auth denied (provide -ArchitectKey)"
    Add-CheckResult "devfactory_orders_recent" $false $r.code $u ($note + ("; ms={0}" -f $sw.ElapsedMilliseconds))
  }
  elseif ($r.code -ge 200 -and $r.code -lt 300) {
    $hasItems = $false
    try {
      $j = $r.body | ConvertFrom-Json -Depth 64
      $hasItems = ($null -ne $j.items)
    } catch { }
    if ($hasItems) {
      Add-CheckResult "devfactory_orders_recent" $true $r.code $u ("items exists; ms={0}" -f $sw.ElapsedMilliseconds)
    } else {
      $ok = $false
      Add-CheckResult "devfactory_orders_recent" $false $r.code $u ("no items field; ms={0}" -f $sw.ElapsedMilliseconds)
    }
  } else {
    $ok = $false
    Add-CheckResult "devfactory_orders_recent" $false $r.code $u ("bad http; ms={0}" -f $sw.ElapsedMilliseconds)
  }
} catch {
  $ok = $false
  Add-CheckResult "devfactory_orders_recent" $false 0 "$BaseUrl/api/devfactory/orders/recent?limit=1&include_result=0" ("exception: {0}" -f $_.Exception.Message)
}

$report = [pscustomobject]@{
  smoke = "devfactory_commercial_c0"
  ts = Now-Iso
  base_url = $BaseUrl
  ok = $ok
  checks = @($checks.ToArray())
}

if ($EvidenceDir) {
  Ensure-Dir $EvidenceDir
  ($report | ConvertTo-Json -Depth 64) | Set-Content -LiteralPath (Join-Path $EvidenceDir "smoke_devfactory_commercial.json") -Encoding utf8NoBOM
}

if ($ok) { exit 0 } else { exit 1 }
