#requires -Version 7.0
<#
FoxProFlow • FlowSec Gate Tool — Secrets Scanner
file: scripts/pwsh/sec/ff-sec-scan-secrets.ps1

Scans staged/unstaged changes for common secret patterns.
Exit codes:
  0 = OK
  2 = WARN (soft findings)
  3 = FAIL (hard findings)

Advisory-first:
  - Use -Advisory to always exit 0 (prints findings).
#>

[CmdletBinding()]
param(
  [ValidateSet("staged","unstaged","all","files")]
  [string]$Mode = "all",

  [string[]]$Files = @(),

  # If empty, resolved via: git rev-parse --show-toplevel
  [string]$RepoRoot = "",

  [string]$AllowlistPath = "scripts/pwsh/sec/ff-sec-allowlist.txt",

  # advisory-first: never fail the pipeline, but still prints findings
  [switch]$Advisory,

  # skip very large files to keep scan fast
  [int]$MaxFileBytes = 2000000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string]$msg)  { Write-Host "[INFO] $msg" }
function Write-Warn([string]$msg)  { Write-Host "[WARN] $msg" }
function Write-Fail([string]$msg)  { Write-Host "[FAIL] $msg" }

function Resolve-RepoRoot([string]$rr) {
  if ($rr -and (Test-Path $rr)) { return (Resolve-Path $rr).Path }
  $root = (& git rev-parse --show-toplevel 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $root) {
    throw "Not a git repo (git rev-parse failed). Run this from a repo worktree."
  }
  return ($root.Trim())
}

function Load-Allowlist([string]$root, [string]$relPath) {
  $full = if ([IO.Path]::IsPathRooted($relPath)) { $relPath } else { Join-Path $root $relPath }
  $allow = [ordered]@{
    FileRegex = @()
    MatchRegex = @()
    FullPath = $full
  }
  if (-not (Test-Path $full)) { return $allow }

  $lines = Get-Content -LiteralPath $full -ErrorAction Stop
  foreach ($ln in $lines) {
    $t = $ln.Trim()
    if (-not $t -or $t.StartsWith("#")) { continue }
    if ($t -match '^\s*FILE\s*:(.+)$') {
      $allow.FileRegex += $Matches[1].Trim()
      continue
    }
    if ($t -match '^\s*MATCH\s*:(.+)$') {
      $allow.MatchRegex += $Matches[1].Trim()
      continue
    }
    # default bucket: match record
    $allow.MatchRegex += $t
  }
  return $allow
}

function Test-IsTextFile([byte[]]$bytes) {
  if (-not $bytes -or $bytes.Count -eq 0) { return $true }
  # NUL byte is a strong signal of binary
  return (-not ($bytes -contains 0))
}

function Mask-Value([string]$v) {
  if (-not $v) { return "" }
  $s = $v.Trim()
  if ($s.Length -le 10) { return "***" }
  $head = $s.Substring(0, 4)
  $tail = $s.Substring($s.Length - 4, 4)
  return "$head****$tail"
}

function Get-StagedFiles([string]$root) {
  Push-Location $root
  try {
    $out = (& git diff --cached --name-only 2>$null)
    if ($LASTEXITCODE -ne 0) { return @() }
    return @($out | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_.Trim() })
  } finally { Pop-Location }
}

function Get-UnstagedFiles([string]$root) {
  Push-Location $root
  try {
    $out = (& git diff --name-only 2>$null)
    if ($LASTEXITCODE -ne 0) { return @() }
    return @($out | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_.Trim() })
  } finally { Pop-Location }
}

function Get-TextFromIndex([string]$root, [string]$relPath) {
  Push-Location $root
  try {
    $txt = (& git show ":$relPath" 2>$null)
    if ($LASTEXITCODE -ne 0) { return $null }
    if ($txt -is [Array]) { return ($txt -join "`n") }
    return [string]$txt
  } finally { Pop-Location }
}

function Get-TextFromDisk([string]$root, [string]$relPath, [int]$maxBytes) {
  $full = Join-Path $root $relPath
  if (-not (Test-Path -LiteralPath $full)) { return $null }

  $fi = Get-Item -LiteralPath $full -ErrorAction Stop
  if ($fi.Length -gt $maxBytes) { return "__SKIP_LARGE__" }

  # quick binary check
  $fs = [System.IO.File]::Open($full, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
  try {
    $buf = New-Object byte[] 4096
    $read = $fs.Read($buf, 0, $buf.Length)
    if ($read -gt 0) {
      $slice = $buf[0..($read-1)]
      if (-not (Test-IsTextFile $slice)) { return "__SKIP_BINARY__" }
    }
  } finally {
    $fs.Dispose()
  }

  return Get-Content -LiteralPath $full -Raw -ErrorAction Stop
}

function New-Regex([string]$pattern) {
  return [regex]::new($pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
}

$hard = @(
  @{ Name="PRIVATE_KEY_BLOCK"; Rx = New-Regex('-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----|-----BEGIN PRIVATE KEY-----|-----BEGIN PGP PRIVATE KEY BLOCK-----') },
  @{ Name="AWS_ACCESS_KEY_ID"; Rx = New-Regex('\b(AKIA|ASIA)[0-9A-Z]{16}\b') },
  @{ Name="GITHUB_TOKEN"; Rx = New-Regex('\b(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,})\b') },
  @{ Name="SLACK_TOKEN"; Rx = New-Regex('\b(xox[baprs]-[0-9A-Za-z-]{10,})\b') },
  @{ Name="STRIPE_LIVE_KEY"; Rx = New-Regex('\b(sk_live_[0-9a-zA-Z]{20,})\b') },
  @{ Name="OPENAI_KEY"; Rx = New-Regex('\b(sk-[A-Za-z0-9]{20,})\b') },
  @{ Name="GOOGLE_API_KEY"; Rx = New-Regex('\b(AIzaSy[0-9A-Za-z\-_]{30,})\b') },
  @{ Name="JWT_TOKEN"; Rx = New-Regex('\b(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,})\b') }
)

$soft = @(
  @{ Name="GENERIC_SECRET_ASSIGN"; Rx = New-Regex('(?i)\b(password|passwd|pwd|secret|token|apikey|api_key|private_key)\b\s*[:=]\s*([^\s#;]{8,})') },
  @{ Name="CONNECTION_STRING_HINT"; Rx = New-Regex('(?i)\b(postgres(ql)?|redis|amqp|mongodb|mysql)\:\/\/[^ \t\r\n]+') }
)

$root = Resolve-RepoRoot $RepoRoot
$allow = Load-Allowlist $root $AllowlistPath

Write-Info "RepoRoot: $root"
if (Test-Path -LiteralPath $allow.FullPath) { Write-Info "Allowlist: $($allow.FullPath)" } else { Write-Info "Allowlist: (none)" }

$targets = [ordered]@{
  staged   = @()
  unstaged = @()
}

switch ($Mode) {
  "files" {
    if (-not $Files -or $Files.Count -eq 0) { throw "Mode=files requires -Files" }
    # treat provided as disk files by default
    $targets.unstaged = @($Files)
  }
  "staged"   { $targets.staged   = Get-StagedFiles $root }
  "unstaged" { $targets.unstaged = Get-UnstagedFiles $root }
  "all" {
    $targets.staged   = Get-StagedFiles $root
    $targets.unstaged = Get-UnstagedFiles $root
  }
}

# normalize and de-dupe per scope
$targets.staged   = @($targets.staged   | Where-Object { $_ } | ForEach-Object { $_.Replace('\','/').Trim() } | Select-Object -Unique)
$targets.unstaged = @($targets.unstaged | Where-Object { $_ } | ForEach-Object { $_.Replace('\','/').Trim() } | Select-Object -Unique)

function Is-AllowFile([string]$rel) {
  foreach ($re in $allow.FileRegex) {
    if ([regex]::IsMatch($rel, $re, "IgnoreCase")) { return $true }
  }
  return $false
}

function Is-AllowMatch([string]$record) {
  foreach ($re in $allow.MatchRegex) {
    if ([regex]::IsMatch($record, $re, "IgnoreCase")) { return $true }
  }
  return $false
}

$findingsHard = New-Object System.Collections.Generic.List[object]
$findingsSoft = New-Object System.Collections.Generic.List[object]

function Scan-Text([string]$scope, [string]$relPath, [string]$text) {
  if ($text -eq "__SKIP_LARGE__") {
    $rec = "SKIP_LARGE|$scope|$relPath|0|0|FILE_TOO_LARGE"
    if (-not (Is-AllowMatch $rec)) {
      $findingsSoft.Add([pscustomobject]@{ level="WARN"; scope=$scope; file=$relPath; line=0; kind="FILE_TOO_LARGE"; value=""; note="Skipped large file" })
    }
    return
  }
  if ($text -eq "__SKIP_BINARY__") {
    $rec = "SKIP_BINARY|$scope|$relPath|0|0|FILE_BINARY"
    if (-not (Is-AllowMatch $rec)) {
      $findingsSoft.Add([pscustomobject]@{ level="WARN"; scope=$scope; file=$relPath; line=0; kind="FILE_BINARY"; value=""; note="Skipped binary file" })
    }
    return
  }
  if ($null -eq $text) { return }

  $lines = $text -split "`n"
  for ($i=0; $i -lt $lines.Count; $i++) {
    $ln = $lines[$i]
    $lineNo = $i + 1

    foreach ($p in $hard) {
      $m = $p.Rx.Matches($ln)
      if ($m.Count -gt 0) {
        foreach ($mm in $m) {
          $val = [string]$mm.Value
          $rec = "$($p.Name)|$scope|$relPath|$lineNo|HARD|$val"
          if (Is-AllowMatch $rec) { continue }
          $findingsHard.Add([pscustomobject]@{ level="FAIL"; scope=$scope; file=$relPath; line=$lineNo; kind=$p.Name; value=(Mask-Value $val); note="" })
        }
      }
    }

    foreach ($p in $soft) {
      $m = $p.Rx.Matches($ln)
      if ($m.Count -gt 0) {
        foreach ($mm in $m) {
          $val = [string]$mm.Value
          $rec = "$($p.Name)|$scope|$relPath|$lineNo|SOFT|$val"
          if (Is-AllowMatch $rec) { continue }
          $findingsSoft.Add([pscustomobject]@{ level="WARN"; scope=$scope; file=$relPath; line=$lineNo; kind=$p.Name; value=(Mask-Value $val); note="" })
        }
      }
    }
  }
}

# scan staged content
foreach ($f in $targets.staged) {
  if (Is-AllowFile $f) { Write-Info "Allowlisted file (skip): $f"; continue }
  $txt = Get-TextFromIndex $root $f
  Scan-Text "staged" $f $txt
}

# scan working tree content
foreach ($f in $targets.unstaged) {
  if (Is-AllowFile $f) { Write-Info "Allowlisted file (skip): $f"; continue }
  $txt = Get-TextFromDisk $root $f $MaxFileBytes
  Scan-Text "unstaged" $f $txt
}

# print report
if ($findingsHard.Count -eq 0 -and $findingsSoft.Count -eq 0) {
  Write-Info "Secrets scan: OK (no findings)."
  exit 0
}

Write-Host ""
Write-Host "=== FlowSec Secrets Scan Report ==="
if ($findingsHard.Count -gt 0) {
  Write-Host ""
  Write-Host "Hard findings (FAIL):"
  $findingsHard | Sort-Object file,line,kind | Format-Table -AutoSize scope,file,line,kind,value,note
}
if ($findingsSoft.Count -gt 0) {
  Write-Host ""
  Write-Host "Soft findings (WARN):"
  $findingsSoft | Sort-Object file,line,kind | Format-Table -AutoSize scope,file,line,kind,value,note
}
Write-Host ""

if ($Advisory) {
  Write-Warn "Advisory mode: exiting 0 despite findings."
  exit 0
}

if ($findingsHard.Count -gt 0) { exit 3 }
exit 2
