#requires -Version 7.0
<#
FoxProFlow • Security Lane • Surface Map builder (read-only)
file: scripts/pwsh/sec/ff-sec-surface-map.ps1

Input: evidence folder containing openapi_paths.txt (from ff-sec-preflight)
Output: markdown + json summary (no secrets)

Run:
  pwsh -NoProfile -File .\scripts\pwsh\sec\ff-sec-surface-map.ps1 `
    -EvidenceDir ".\ops\_local\evidence\sec_preflight_20251226_043007"
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$EvidenceDir,
  [string]$OutDir = "",
  [string]$OutBaseName = "security_surface_map_v0",
  [switch]$PrintTopOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }

$ev = (Resolve-Path -LiteralPath $EvidenceDir).Path
$pathsFile = Join-Path $ev "openapi_paths.txt"
if (-not (Test-Path -LiteralPath $pathsFile)) { throw "Missing openapi_paths.txt in: $ev" }

if ([string]::IsNullOrWhiteSpace($OutDir)) {
  $OutDir = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
  $OutDir = Join-Path $OutDir "docs\ops\security"
}
Ensure-Dir $OutDir

$paths = @((Get-Content -LiteralPath $pathsFile -ErrorAction Stop) | Where-Object { $_ -and $_.Trim() -ne "" } | ForEach-Object { $_.Trim() })

# domain stats
$domains = $paths | ForEach-Object {
  if ($_ -match '^/api/([^/]+)/') { $matches[1] } else { "(root/other)" }
}
$top = $domains | Group-Object | Sort-Object Count -Descending

if ($PrintTopOnly) {
  $top | Select-Object -First 30 Count, Name | Format-Table -AutoSize
  exit 0
}

# group by domain
$byDomain = @{}
for ($i=0; $i -lt $paths.Count; $i++) {
  $p = $paths[$i]
  $d = "(root/other)"
  if ($p -match '^/api/([^/]+)/') { $d = $matches[1] }
  if (-not $byDomain.ContainsKey($d)) { $byDomain[$d] = New-Object System.Collections.Generic.List[string] }
  $byDomain[$d].Add($p) | Out-Null
}

# simple P0 candidate heuristic
$p0 = @(
  $paths | Where-Object { $_ -match '(?i)/(run|confirm|autofix|link/|orders\b|intent\b)' } | Sort-Object
)

$md = New-Object System.Collections.Generic.List[string]
$md.Add("# FoxProFlow • Security Lane • Security Surface Map v0") | Out-Null
$md.Add(("Дата: {0}" -f (Get-Date -Format "yyyy-MM-dd"))) | Out-Null
$md.Add("Создал: Архитектор Яцков Евгений Анатольевич") | Out-Null
$md.Add("") | Out-Null
$md.Add("Evidence folder:") | Out-Null
$md.Add($ev) | Out-Null
$md.Add("") | Out-Null

$md.Add("## 1) Top domains by OpenAPI path count") | Out-Null
$md.Add("") | Out-Null
$md.Add("| Count | Domain |") | Out-Null
$md.Add("|---:|---|") | Out-Null
foreach ($g in ($top | Select-Object -First 30)) {
  $md.Add(("| {0} | {1} |" -f $g.Count, $g.Name)) | Out-Null
}
$md.Add("") | Out-Null

$md.Add("## 2) P0 candidates (heuristic)") | Out-Null
$md.Add("") | Out-Null
foreach ($x in $p0) { $md.Add(("* {0}" -f $x)) | Out-Null }
$md.Add("") | Out-Null

$md.Add("## 3) Domains (paths)") | Out-Null
$md.Add("") | Out-Null
foreach ($k in ($byDomain.Keys | Sort-Object)) {
  $md.Add(("### {0} ({1})" -f $k, $byDomain[$k].Count)) | Out-Null
  foreach ($p in $byDomain[$k]) { $md.Add(("* {0}" -f $p)) | Out-Null }
  $md.Add("") | Out-Null
}

$outMd = Join-Path $OutDir ($OutBaseName + ".md")
$outJson = Join-Path $OutDir ($OutBaseName + ".json")

$mdText = ($md.ToArray() -join "`r`n")
$mdText | Set-Content -LiteralPath $outMd -Encoding utf8NoBOM

$payload = [pscustomobject]@{
  ts = Now-Iso
  evidence_dir = $ev
  paths_count = $paths.Count
  top_domains = @($top | Select-Object Count, Name)
  p0_candidates = $p0
}
($payload | ConvertTo-Json -Depth 32) | Set-Content -LiteralPath $outJson -Encoding utf8NoBOM

Write-Host ("[SEC SURFACE MAP] written: {0}" -f $outMd) -ForegroundColor Green
Write-Host ("[SEC SURFACE MAP] json:    {0}" -f $outJson) -ForegroundColor Green
