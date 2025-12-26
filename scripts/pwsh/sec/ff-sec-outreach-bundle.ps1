#requires -Version 7.0
<#
FoxProFlow • Security Lane • Outreach Bundle (evidence-first)
file: scripts/pwsh/sec/ff-sec-outreach-bundle.ps1

Goal:
  Build a single bundle markdown from an outreach evidence folder (outreach_<stamp>),
  concatenating subject + email_short (optionally email_full/call/checklist).

Inputs:
  -EvidenceDir: explicit path to outreach_<stamp>
  -If omitted, auto-picks the newest ops/_local/evidence/outreach_*

Outputs (inside EvidenceDir by default):
  - bundle_outreach_<stamp>.md
  - bundle_meta.json

Usage:
  pwsh -NoProfile -File .\scripts\pwsh\sec\ff-sec-outreach-bundle.ps1
  pwsh -NoProfile -File .\scripts\pwsh\sec\ff-sec-outreach-bundle.ps1 -EvidenceDir ".\ops\_local\evidence\outreach_20251226_075539"
  pwsh -NoProfile -File .\scripts\pwsh\sec\ff-sec-outreach-bundle.ps1 -IncludeFull -IncludeCall -IncludeChecklist -OpenFile

Notes:
  - READ-ONLY relative to repo: only writes bundle files to evidence folder.
  - No external deps.
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$EvidenceDir = "",
  [string]$EvidenceRoot = "",

  [switch]$IncludeFull,
  [switch]$IncludeCall,
  [switch]$IncludeChecklist,

  [switch]$OpenFolder,
  [switch]$OpenFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }

function Ensure-Dir([string]$p) {
  if ([string]::IsNullOrWhiteSpace($p)) { return }
  New-Item -ItemType Directory -Force -Path $p | Out-Null
}

function Repo-Root {
  (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Resolve-EvidenceRoot([string]$root, [string]$repoRoot) {
  if (-not [string]::IsNullOrWhiteSpace($root)) {
    if (Test-Path -LiteralPath $root) { return (Resolve-Path -LiteralPath $root).Path }
    return $root
  }
  $cand = Join-Path $repoRoot "ops\_local\evidence"
  return $cand
}

function Pick-LatestOutreachDir([string]$evRoot) {
  if (-not (Test-Path -LiteralPath $evRoot)) { return $null }
  $d = Get-ChildItem -LiteralPath $evRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "outreach_*" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($d) { return $d.FullName }
  return $null
}

function Load-Json([string]$path) {
  $raw = Get-Content -Raw -LiteralPath $path -ErrorAction Stop
  return ($raw | ConvertFrom-Json -Depth 100)
}

function Slug([string]$s) {
  if ([string]::IsNullOrWhiteSpace($s)) { return "company" }
  $t = $s.Trim().ToLowerInvariant() -replace '[^a-z0-9а-яё]+','_'
  $t = $t -replace '_+','_'
  $t = $t.Trim('_')
  if ($t.Length -gt 48) { $t = $t.Substring(0,48) }
  if ([string]::IsNullOrWhiteSpace($t)) { return "company" }
  return $t
}

# --- Resolve evidence dir ---
$repoRoot = Repo-Root
$evRoot = Resolve-EvidenceRoot -root $EvidenceRoot -repoRoot $repoRoot

if ([string]::IsNullOrWhiteSpace($EvidenceDir)) {
  $EvidenceDir = Pick-LatestOutreachDir -evRoot $evRoot
  if ([string]::IsNullOrWhiteSpace($EvidenceDir)) {
    throw "No outreach_* evidence folders found in: $evRoot. Provide -EvidenceDir explicitly."
  }
} else {
  if (Test-Path -LiteralPath $EvidenceDir) {
    $EvidenceDir = (Resolve-Path -LiteralPath $EvidenceDir).Path
  }
}

if (-not (Test-Path -LiteralPath $EvidenceDir)) {
  throw "EvidenceDir not found: $EvidenceDir"
}

# Derive stamp from folder name if possible
$folderName = Split-Path $EvidenceDir -Leaf
$stamp = $folderName
if ($folderName -match '^outreach_(\d{8}_\d{6})$') { $stamp = $matches[1] }

# --- Load all outreach json ---
$items = @()
$files = Get-ChildItem -LiteralPath $EvidenceDir -File -Filter "outreach_*.json" -ErrorAction SilentlyContinue | Sort-Object Name
if (-not $files -or $files.Count -eq 0) {
  throw "No outreach_*.json files found in: $EvidenceDir"
}

foreach ($f in $files) {
  try {
    $j = Load-Json $f.FullName
    $items += [pscustomobject]@{
      file = $f.FullName
      company = [string]$j.company
      segment = [string]$j.segment
      contact_role = [string]$j.contact_role
      subject = $(if ($j.subjects -and $j.subjects.Count -gt 0) { [string]$j.subjects[0] } else { "" })
      email_short = [string]$j.email_short
      email_full  = [string]$j.email_full
      call_opener = [string]$j.call_opener
      call_script = [string]$j.call_script
      checklist  = [string]$j.checklist
      references = $j.references
      cta = $j.cta
    }
  } catch {
    $items += [pscustomobject]@{
      file = $f.FullName
      company = ""
      segment = ""
      contact_role = ""
      subject = ""
      email_short = ""
      email_full = ""
      call_opener = ""
      call_script = ""
      checklist = ""
      references = $null
      cta = $null
      error = $_.Exception.Message
    }
  }
}

# --- Build bundle markdown ---
$nl = [Environment]::NewLine
$bundle = New-Object System.Collections.Generic.List[string]

$bundle.Add("# FoxProFlow • Security Lane • Outreach Bundle") | Out-Null
$bundle.Add(("ts: {0}" -f (Now-Iso))) | Out-Null
$bundle.Add(("evidence_dir: {0}" -f $EvidenceDir)) | Out-Null
$bundle.Add(("count: {0}" -f $items.Count)) | Out-Null
$bundle.Add("") | Out-Null

# Index table
$bundle.Add("## Index") | Out-Null
$bundle.Add("") | Out-Null
$bundle.Add("| # | Company | Segment | Role | Subject |") | Out-Null
$bundle.Add("|---:|---|---|---|---|") | Out-Null

for ($i=0; $i -lt $items.Count; $i++) {
  $it = $items[$i]
  $n = $i + 1
  $company = $(if ($it.company) { $it.company } else { "(unknown)" })
  $seg = $(if ($it.segment) { $it.segment } else { "" })
  $role = $(if ($it.contact_role) { $it.contact_role } else { "" })
  $subj = $(if ($it.subject) { $it.subject } else { "" })
  # escape pipe
  $subj = $subj -replace '\|','/'
  $bundle.Add(("| {0} | {1} | {2} | {3} | {4} |" -f $n, $company, $seg, $role, $subj)) | Out-Null
}
$bundle.Add("") | Out-Null

# Each company section
for ($i=0; $i -lt $items.Count; $i++) {
  $it = $items[$i]
  $n = $i + 1
  $company = $(if ($it.company) { $it.company } else { ("Item#{0}" -f $n) })
  $slug = Slug $company

  $bundle.Add(("---")) | Out-Null
  $bundle.Add(("## {0}. {1}" -f $n, $company)) | Out-Null
  $bundle.Add(("segment: {0}" -f $it.segment)) | Out-Null
  if ($it.contact_role) { $bundle.Add(("role: {0}" -f $it.contact_role)) | Out-Null }
  $bundle.Add("") | Out-Null

  if ($it.subject) {
    $bundle.Add("### Subject") | Out-Null
    $bundle.Add($it.subject) | Out-Null
    $bundle.Add("") | Out-Null
  }

  $bundle.Add("### Email (short)") | Out-Null
  $bundle.Add("") | Out-Null
  $bundle.Add($it.email_short) | Out-Null
  $bundle.Add("") | Out-Null

  if ($IncludeFull) {
    $bundle.Add("### Email (full)") | Out-Null
    $bundle.Add("") | Out-Null
    $bundle.Add($it.email_full) | Out-Null
    $bundle.Add("") | Out-Null
  }

  if ($IncludeCall) {
    $bundle.Add("### Call opener (20 sec)") | Out-Null
    $bundle.Add($it.call_opener) | Out-Null
    $bundle.Add("") | Out-Null

    $bundle.Add("### Call script (5 min)") | Out-Null
    $bundle.Add($it.call_script) | Out-Null
    $bundle.Add("") | Out-Null
  }

  if ($IncludeChecklist) {
    $bundle.Add("### First-call checklist") | Out-Null
    $bundle.Add($it.checklist) | Out-Null
    $bundle.Add("") | Out-Null
  }

  $bundle.Add(("source_json: {0}" -f (Split-Path $it.file -Leaf))) | Out-Null
}

$bundlePath = Join-Path $EvidenceDir ("bundle_outreach_{0}.md" -f $stamp)
$metaPath   = Join-Path $EvidenceDir ("bundle_meta_{0}.json" -f $stamp)

($bundle.ToArray() -join $nl) | Set-Content -LiteralPath $bundlePath -Encoding utf8NoBOM

$meta = [pscustomobject]@{
  ts = Now-Iso
  evidence_dir = $EvidenceDir
  count = $items.Count
  include_full = [bool]$IncludeFull
  include_call = [bool]$IncludeCall
  include_checklist = [bool]$IncludeChecklist
  outputs = [pscustomobject]@{
    bundle_md = $bundlePath
    meta_json = $metaPath
  }
  items = @(
    $items | ForEach-Object {
      [pscustomobject]@{
        company = $_.company
        segment = $_.segment
        subject = $_.subject
        file = $_.file
      }
    }
  )
}

($meta | ConvertTo-Json -Depth 32) | Set-Content -LiteralPath $metaPath -Encoding utf8NoBOM

Write-Host "[OUTREACH BUNDLE] OK" -ForegroundColor Green
Write-Host ("evidence: {0}" -f $EvidenceDir)
Write-Host ("bundle:   {0}" -f $bundlePath)

if ($OpenFolder) {
  explorer.exe $EvidenceDir | Out-Null
}
if ($OpenFile) {
  notepad $bundlePath | Out-Null
}
