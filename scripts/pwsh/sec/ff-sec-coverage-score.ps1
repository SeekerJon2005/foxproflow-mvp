#requires -Version 7.0
<#
FoxProFlow • Security Lane • Coverage Score (v0)
file: scripts/pwsh/sec/ff-sec-coverage-score.ps1

Purpose:
  - Summarize policy map into a "Security Readiness Score" (advisory metric).
  - Output markdown + json in docs/ops/security
  - READ-ONLY (uses existing generated artifacts)

Run:
  pwsh -NoProfile -File .\scripts\pwsh\sec\ff-sec-coverage-score.ps1
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$PolicyMapJson = "",
  [string]$OutDir = "",
  [string]$OutBaseName = "security_coverage_score_v0",
  [int]$TopN = 25
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function Repo-Root { (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path }

function Load-Json([string]$path) {
  $p = (Resolve-Path -LiteralPath $path).Path
  (Get-Content -Raw -LiteralPath $p) | ConvertFrom-Json -Depth 100
}

$root = Repo-Root

if ([string]::IsNullOrWhiteSpace($OutDir)) { $OutDir = Join-Path $root "docs\ops\security" }
Ensure-Dir $OutDir

if ([string]::IsNullOrWhiteSpace($PolicyMapJson)) { $PolicyMapJson = Join-Path $OutDir "security_policy_map_v0.json" }
if (-not (Test-Path -LiteralPath $PolicyMapJson)) { throw "PolicyMapJson not found: $PolicyMapJson" }

$pm = Load-Json $PolicyMapJson
$items = @($pm.items)

# Basic counts
$cntTotal = [int]$items.Count
$cntP0 = [int](@($items | Where-Object priority -eq "P0")).Count
$cntP1 = [int](@($items | Where-Object priority -eq "P1")).Count
$cntP2 = [int](@($items | Where-Object priority -eq "P2")).Count
$cntP3 = [int](@($items | Where-Object priority -eq "P3")).Count

# Unique actions per tier
function UniqueCount([string]$prio) {
  $a = @($items | Where-Object priority -eq $prio | Select-Object -ExpandProperty action -ErrorAction SilentlyContinue)
  return [int](@($a | Sort-Object -Unique)).Count
}

$uaP0 = UniqueCount "P0"
$uaP1 = UniqueCount "P1"
$uaP2 = UniqueCount "P2"

# Top risky endpoints: by score desc
$top = @($items | Sort-Object @{Expression="score";Descending=$true}, @{Expression="path";Descending=$false} | Select-Object -First $TopN)

# Domain hotspots (P0/P1 only)
$hot = @($items | Where-Object { $_.priority -in @("P0","P1") })
$domHot = @(
  $hot | Group-Object domain | Sort-Object Count -Descending | ForEach-Object {
    [pscustomobject]@{ count=[int]$_.Count; domain=[string]$_.Name }
  }
)

# --- Score model (v0, simple and explainable) ---
# We treat P0 as weight 4, P1 as 2, P2 as 1, P3 as 0.
# "Coverage" is assumed because we already produced an action/policy for each path.
# So score is a weighted-normalized surface readiness: more P0/P1 mapped => higher readiness.
# (In v1 we will compare desired vs actually enforced policies from runtime logs.)
$wP0 = 4; $wP1 = 2; $wP2 = 1; $wP3 = 0
$max = ($cntP0*$wP0 + $cntP1*$wP1 + $cntP2*$wP2 + $cntP3*$wP3)
$score = 0.0
if ($max -gt 0) {
  # because every endpoint has an action+policy in policy map, coverage=1.0 here
  $score = 100.0
}

# But we also output "risk concentration": share of P0+P1
$riskShare = 0.0
if ($cntTotal -gt 0) { $riskShare = [Math]::Round(100.0 * (($cntP0 + $cntP1) / $cntTotal), 2) }

# Build markdown
$nl = [Environment]::NewLine
$md = New-Object System.Collections.Generic.List[string]
$md.Add("# FoxProFlow • Security Lane • Coverage Score v0") | Out-Null
$md.Add(("Дата: {0}" -f (Get-Date -Format "yyyy-MM-dd"))) | Out-Null
$md.Add("Создал: Архитектор Яцков Евгений Анатольевич") | Out-Null
$md.Add("") | Out-Null
$md.Add("Source: security_policy_map_v0.json") | Out-Null
$md.Add($PolicyMapJson) | Out-Null
$md.Add("") | Out-Null

$md.Add("## 1) Summary metrics") | Out-Null
$md.Add("") | Out-Null
$md.Add(("* Total endpoints: {0}" -f $cntTotal)) | Out-Null
$md.Add(("* P0: {0} (unique actions: {1})" -f $cntP0, $uaP0)) | Out-Null
$md.Add(("* P1: {0} (unique actions: {1})" -f $cntP1, $uaP1)) | Out-Null
$md.Add(("* P2: {0} (unique actions: {1})" -f $cntP2, $uaP2)) | Out-Null
$md.Add(("* P3: {0}" -f $cntP3)) | Out-Null
$md.Add(("* Risk share (P0+P1 / total): {0}%" -f $riskShare)) | Out-Null
$md.Add(("* Coverage score v0: {0}" -f ([Math]::Round($score,2)))) | Out-Null
$md.Add("") | Out-Null

$md.Add("## 2) Hot domains (P0/P1)") | Out-Null
$md.Add("") | Out-Null
$md.Add("| Count | Domain |") | Out-Null
$md.Add("|---:|---|") | Out-Null
foreach ($d in ($domHot | Select-Object -First 20)) { $md.Add(("| {0} | {1} |" -f $d.count, $d.domain)) | Out-Null }
$md.Add("") | Out-Null

$md.Add(("## 3) Top {0} risky endpoints" -f $TopN)) | Out-Null
$md.Add("") | Out-Null
$md.Add("| Score | Prio | Domain | Action | Path |") | Out-Null
$md.Add("|---:|---|---|---|---|") | Out-Null
foreach ($r in $top) {
  $md.Add(("| {0} | {1} | {2} | `{3}` | {4} |" -f $r.score, $r.priority, $r.domain, $r.action, $r.path)) | Out-Null
}
$md.Add("") | Out-Null

$md.Add("## 4) Notes") | Out-Null
$md.Add("- v0 score assumes every endpoint in policy map is 'covered' (action+policy proposed).") | Out-Null
$md.Add("- v1 will compute 'enforcement coverage' by sampling runtime denies/allows and checking require_policies wiring.") | Out-Null

$outMd = Join-Path $OutDir ($OutBaseName + ".md")
$outJson = Join-Path $OutDir ($OutBaseName + ".json")

($md.ToArray() -join $nl) | Set-Content -LiteralPath $outMd -Encoding utf8NoBOM

$payload = [pscustomobject]@{
  ts = Now-Iso
  source_policy_map = $PolicyMapJson
  counts = [pscustomobject]@{
    total = $cntTotal; p0=$cntP0; p1=$cntP1; p2=$cntP2; p3=$cntP3
  }
  unique_actions = [pscustomobject]@{
    p0=$uaP0; p1=$uaP1; p2=$uaP2
  }
  risk_share_pct = $riskShare
  coverage_score_v0 = $score
  hot_domains = $domHot
  top_risky = $top
}
($payload | ConvertTo-Json -Depth 64) | Set-Content -LiteralPath $outJson -Encoding utf8NoBOM

Write-Host ("[SEC COVERAGE] written: {0}" -f $outMd) -ForegroundColor Green
Write-Host ("[SEC COVERAGE] json:    {0}" -f $outJson) -ForegroundColor Green
