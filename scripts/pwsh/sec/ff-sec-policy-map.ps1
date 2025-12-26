#requires -Version 7.0
<#
FoxProFlow • Security Lane • Policy Map builder (read-only)
file: scripts/pwsh/sec/ff-sec-policy-map.ps1

Purpose:
  - Convert OpenAPI path inventory -> canonical FlowSec actions/policies candidates.
  - Produce a ranked list (P0/P1/P2) without changing any code or DB.
  - Output: markdown + json.

Inputs:
  - Either EvidenceDir containing openapi_paths.txt
  - Or explicit PathsFile

Run:
  pwsh -NoProfile -File .\scripts\pwsh\sec\ff-sec-policy-map.ps1 `
    -EvidenceDir ".\ops\_local\evidence\sec_preflight_YYYYMMDD_HHMMSS"

Notes:
  - We don't know HTTP methods from openapi_paths.txt alone (paths list). If you want method-aware mapping,
    run with -OpenApiJsonFile (from evidence openapi.json) and we'll extract methods too.
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$EvidenceDir = "",
  [string]$PathsFile = "",
  [string]$OpenApiJsonFile = "",

  [string]$OutDir = "",
  [string]$OutBaseName = "security_policy_map_v0",

  [switch]$PrintSummaryOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }

function Get-RepoRoot {
  return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Load-Paths {
  param([string]$ev, [string]$pf)

  if (-not [string]::IsNullOrWhiteSpace($pf)) {
    $p = (Resolve-Path -LiteralPath $pf).Path
    return [pscustomobject]@{ evidence_dir=""; paths_file=$p; paths=@((Get-Content -LiteralPath $p) | Where-Object { $_ -and $_.Trim() -ne "" } | ForEach-Object { $_.Trim() }) }
  }

  if ([string]::IsNullOrWhiteSpace($ev)) { throw "Provide -EvidenceDir or -PathsFile." }
  $evp = (Resolve-Path -LiteralPath $ev).Path
  $pathsFile2 = Join-Path $evp "openapi_paths.txt"
  if (-not (Test-Path -LiteralPath $pathsFile2)) { throw "Missing openapi_paths.txt in EvidenceDir: $evp" }

  return [pscustomobject]@{ evidence_dir=$evp; paths_file=$pathsFile2; paths=@((Get-Content -LiteralPath $pathsFile2) | Where-Object { $_ -and $_.Trim() -ne "" } | ForEach-Object { $_.Trim() }) }
}

function Try-Load-OpenApi {
  param([string]$path)
  if ([string]::IsNullOrWhiteSpace($path)) { return $null }
  if (-not (Test-Path -LiteralPath $path)) { return $null }
  try {
    $raw = Get-Content -Raw -LiteralPath $path
    return ($raw | ConvertFrom-Json -Depth 100)
  } catch {
    return $null
  }
}

function Get-Domain([string]$p) {
  if ($p -match '^/api/([^/]+)/') { return $matches[1] }
  return "(root/other)"
}

function Score-Path([string]$p) {
  # Higher score => higher risk/priority for FlowSec gates.
  $s = 0

  # domain weighting
  if ($p -match '^/api/devfactory/') { $s += 40 }
  elseif ($p -match '^/api/autoplan') { $s += 35 }
  elseif ($p -match '^/api/devorders') { $s += 30 }
  elseif ($p -match '^/api/trips') { $s += 25 }
  elseif ($p -match '^/api/eri') { $s += 22 }
  elseif ($p -match '^/api/crm') { $s += 20 }
  elseif ($p -match '^/api/driver') { $s += 18 }
  else { $s += 10 }

  # action keywords
  if ($p -match '(?i)/autofix/') { $s += 60 }
  if ($p -match '(?i)/confirm\b') { $s += 50 }
  if ($p -match '(?i)/run\b') { $s += 45 }
  if ($p -match '(?i)/apply\b') { $s += 45 }
  if ($p -match '(?i)/link/') { $s += 40 }
  if ($p -match '(?i)/orders\b') { $s += 25 }
  if ($p -match '(?i)/intent\b') { $s += 30 }
  if ($p -match '(?i)/bootstrap') { $s += 20 }

  # read-ish hints (reduce)
  if ($p -match '(?i)/kpi\b') { $s -= 10 }
  if ($p -match '(?i)/health\b') { $s -= 15 }
  if ($p -match '(?i)/smoke\b') { $s -= 15 }
  if ($p -match '(?i)/recent\b') { $s -= 5 }
  if ($p -match '(?i)/vitrine\b') { $s -= 5 }
  if ($p -match '(?i)/catalog\b') { $s -= 5 }

  if ($s -lt 0) { $s = 0 }
  return $s
}

function Classify-Priority([int]$score) {
  if ($score -ge 90) { return "P0" }
  if ($score -ge 60) { return "P1" }
  if ($score -ge 35) { return "P2" }
  return "P3"
}

function Action-From-Path([string]$p) {
  # Canonical action name: {domain}.{verb}
  # Verb is derived from endpoint semantics.
  $domain = Get-Domain $p

  $verb = "read"
  if ($p -match '(?i)/autofix/(enable|disable|run)') { $verb = "autofix_admin" }
  elseif ($p -match '(?i)/confirm\b') { $verb = "apply" }
  elseif ($p -match '(?i)/run\b') { $verb = "apply" }
  elseif ($p -match '(?i)/link/') { $verb = "link_write" }
  elseif ($p -match '(?i)/orders\b' -and $p -notmatch '(?i)/recent\b') { $verb = "write" }
  elseif ($p -match '(?i)/intent\b') { $verb = "write" }
  elseif ($p -match '(?i)/bootstrap') { $verb = "admin" }
  elseif ($p -match '(?i)/kpi\b|/health\b|/smoke\b|/recent\b|/catalog\b|/vitrine\b') { $verb = "read" }

  # sanitize domain
  $d = ($domain -replace '[^a-zA-Z0-9_]+','_').ToLowerInvariant()
  $v = ($verb -replace '[^a-zA-Z0-9_]+','_').ToLowerInvariant()
  return "$d.$v"
}

function Policy-From-Action([string]$action) {
  # Minimal v0 mapping: action -> required policy name (same string)
  return $action
}

# --- Resolve inputs ---
$repoRoot = Get-RepoRoot
if ([string]::IsNullOrWhiteSpace($OutDir)) {
  $OutDir = Join-Path $repoRoot "docs\ops\security"
}
Ensure-Dir $OutDir

$loaded = Load-Paths -ev $EvidenceDir -pf $PathsFile
$paths = $loaded.paths
$evDir = $loaded.evidence_dir

$openapiObj = $null
if (-not [string]::IsNullOrWhiteSpace($OpenApiJsonFile)) {
  $openapiObj = Try-Load-OpenApi -path $OpenApiJsonFile
} elseif ($evDir) {
  $candidate = Join-Path $evDir "openapi.json"
  $openapiObj = Try-Load-OpenApi -path $candidate
}

# optional: extract methods if openapi.json provided
$methodsByPath = @{}
if ($openapiObj -and $openapiObj.paths) {
  foreach ($pp in $openapiObj.paths.PSObject.Properties) {
    $pathKey = [string]$pp.Name
    $methods = @()
    try {
      $node = $pp.Value
      foreach ($mp in $node.PSObject.Properties) {
        $mn = [string]$mp.Name
        if ($mn -match '^(get|post|put|patch|delete|options|head)$') { $methods += $mn.ToUpperInvariant() }
      }
    } catch {}
    $methodsByPath[$pathKey] = @($methods | Sort-Object -Unique)
  }
}

$rows = New-Object System.Collections.Generic.List[object]
foreach ($p in $paths) {
  $score = Score-Path $p
  $prio = Classify-Priority $score
  $action = Action-From-Path $p
  $policy = Policy-From-Action $action
  $methods = @()
  if ($methodsByPath.ContainsKey($p)) { $methods = $methodsByPath[$p] }

  $rows.Add([pscustomobject]@{
    path = $p
    domain = (Get-Domain $p)
    methods = $methods
    score = $score
    priority = $prio
    action = $action
    policy = $policy
  }) | Out-Null
}

$rowsSorted = @($rows | Sort-Object @{Expression="score";Descending=$true}, @{Expression="path";Descending=$false})

# domain stats
$domainStats = $rowsSorted | Group-Object domain | Sort-Object Count -Descending |
  Select-Object @{n="count";e={$_.Count}}, @{n="domain";e={$_.Name}}

if ($PrintSummaryOnly) {
  $domainStats | Select-Object -First 20 | Format-Table -AutoSize
  ($rowsSorted | Where-Object priority -eq "P0" | Select-Object -First 25 path, action, policy, score) | Format-Table -AutoSize
  exit 0
}

# Write markdown
$md = New-Object System.Collections.Generic.List[string]
$md.Add("# FoxProFlow • Security Lane • Policy Map v0") | Out-Null
$md.Add(("Дата: {0}" -f (Get-Date -Format "yyyy-MM-dd"))) | Out-Null
$md.Add("Создал: Архитектор Яцков Евгений Анатольевич") | Out-Null
$md.Add("") | Out-Null
if ($evDir) {
  $md.Add("Evidence folder:") | Out-Null
  $md.Add($evDir) | Out-Null
  $md.Add("") | Out-Null
}

$md.Add("## 1) Domain stats") | Out-Null
$md.Add("") | Out-Null
$md.Add("| Count | Domain |") | Out-Null
$md.Add("|---:|---|") | Out-Null
foreach ($d in ($domainStats | Select-Object -First 50)) {
  $md.Add(("| {0} | {1} |" -f $d.count, $d.domain)) | Out-Null
}
$md.Add("") | Out-Null

$md.Add("## 2) P0 endpoints (highest risk / first gates)") | Out-Null
$md.Add("") | Out-Null
foreach ($r in ($rowsSorted | Where-Object priority -eq "P0")) {
  $m = ""
  if ($r.methods -and $r.methods.Count -gt 0) { $m = " [" + ($r.methods -join ",") + "]" }
  $md.Add(("* {0}{1} → action `{2}` policy `{3}` (score={4})" -f $r.path, $m, $r.action, $r.policy, $r.score)) | Out-Null
}
$md.Add("") | Out-Null

$md.Add("## 3) P1 endpoints") | Out-Null
$md.Add("") | Out-Null
foreach ($r in ($rowsSorted | Where-Object priority -eq "P1")) {
  $m = ""
  if ($r.methods -and $r.methods.Count -gt 0) { $m = " [" + ($r.methods -join ",") + "]" }
  $md.Add(("* {0}{1} → action `{2}` (score={3})" -f $r.path, $m, $r.action, $r.score)) | Out-Null
}
$md.Add("") | Out-Null

$md.Add("## 4) Action/Policy dictionary (unique)") | Out-Null
$md.Add("") | Out-Null
$uniqActions = $rowsSorted | Group-Object action | Sort-Object Count -Descending
foreach ($a in $uniqActions) {
  $md.Add(("* `{0}`  (endpoints={1})" -f $a.Name, $a.Count)) | Out-Null
}
$md.Add("") | Out-Null

$md.Add("## 5) Notes") | Out-Null
$md.Add("- v0 mapping is heuristic; methods-aware mapping is enabled if openapi.json is available in evidence.") | Out-Null
$md.Add("- This document does NOT apply gates; it proposes action/policy names and priorities only.") | Out-Null

$outMd = Join-Path $OutDir ($OutBaseName + ".md")
$outJson = Join-Path $OutDir ($OutBaseName + ".json")

($md.ToArray() -join "`r`n") | Set-Content -LiteralPath $outMd -Encoding utf8NoBOM

$payload = [pscustomobject]@{
  ts = Now-Iso
  evidence_dir = $evDir
  paths_file = $loaded.paths_file
  paths_count = $paths.Count
  domain_stats = $domainStats
  items = $rowsSorted
}
($payload | ConvertTo-Json -Depth 64) | Set-Content -LiteralPath $outJson -Encoding utf8NoBOM

Write-Host ("[SEC POLICY MAP] written: {0}" -f $outMd) -ForegroundColor Green
Write-Host ("[SEC POLICY MAP] json:    {0}" -f $outJson) -ForegroundColor Green
