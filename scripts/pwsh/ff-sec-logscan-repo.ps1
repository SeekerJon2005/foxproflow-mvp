#requires -Version 7.0
<#
FoxProFlow • FlowSec • Secrets/PII logscan
file: scripts/pwsh/ff-sec-logscan-repo.ps1

Purpose:
- Scan repo/staged/path for high-risk secrets (S3/S4) and optional PII.
- Output findings WITHOUT leaking secrets.
- Exit codes:
  0 = PASS
  2 = FINDINGS (block gate)
  1 = ERROR

Notes:
- Mode=Staged reads STAGED blobs (git cat-file :path) when possible.
- Optional allowlist file (regex per line): scripts/pwsh/sec/ff-sec-allowlist.txt
  Prefixes supported:
    re:<regex>
    literal:<text>
  Comments: lines starting with # ; --
#>

[CmdletBinding(PositionalBinding = $false)]
param(
  [ValidateSet("Staged", "Tracked", "Path")]
  [string]$Mode = "Tracked",

  [ValidateSet("Secrets", "PII", "SecretsAndPII")]
  [string]$Scan = "Secrets",

  [string]$TargetPath = "",

  [int]$MaxFindings = 50,

  [int]$MaxFileBytes = 1048576, # 1 MB

  [string]$EvidenceDir = "",

  [string]$AllowlistPath = "",

  [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Say([string]$msg) { if (-not $Quiet) { Write-Host "[secscan] $msg" } }
function Warn([string]$msg) { if (-not $Quiet) { Write-Host "[secscan][warn] $msg" } }
function Fail([string]$msg) { Write-Host "[secscan][fail] $msg" }

function Get-RepoRoot() {
  $root = (& git rev-parse --show-toplevel 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $root) { throw "git rev-parse --show-toplevel failed (run inside a git repo)." }
  return $root.Trim()
}

function Is-BinaryLike([string]$path) {
  $ext = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
  $bin = @(
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico",
    ".pdf", ".zip", ".7z", ".rar", ".tar", ".gz", ".bz2",
    ".exe", ".dll", ".so", ".dylib", ".pdb",
    ".mp3", ".mp4", ".mov", ".avi", ".mkv",
    ".woff", ".woff2", ".ttf", ".otf",
    ".db", ".sqlite", ".bin"
  )
  return ($bin -contains $ext)
}

function Should-SkipPath([string]$fullPath) {
  $p = $fullPath.Replace("/", "\")
  if ($p -match "\\\.git\\") { return $true }
  if ($p -match "\\node_modules\\") { return $true }
  if ($p -match "\\venv\\") { return $true }
  if ($p -match "\\\.venv\\") { return $true }
  if ($p -match "\\__pycache__\\") { return $true }
  if ($p -match "\\\.pytest_cache\\") { return $true }
  if ($p -match "\\\.mypy_cache\\") { return $true }
  if ($p -match "\\ops\\_local\\") { return $true }
  if ($p -match "\\tmp\\") { return $true }
  if ($p -match "\\artifacts\\") { return $true }
  return $false
}

function Is-SuspectSecretFile([string]$relPath) {
  $p = ($relPath ?? "").Replace("/", "\").ToLowerInvariant()
  $name = [System.IO.Path]::GetFileName($p)

  if ($name -match '^\.env\.(example|sample|template)$') { return $false }

  $badNames = @(".env", ".secrets.env", ".env.secrets", "secrets.env", ".env.local", ".env.production", ".env.prod")
  if ($badNames -contains $name) { return $true }

  $ext = [System.IO.Path]::GetExtension($p)
  $susExt = @(".pem", ".key", ".pfx", ".p12", ".jks", ".keystore", ".ppk")
  if ($susExt -contains $ext) { return $true }

  if ($name -match '^id_rsa$|^id_ed25519$') { return $true }
  if ($p -match "\\ssh\\") { return $true }

  return $false
}

function Redact-Email([string]$email) {
  if (-not $email) { return "<redacted_email>" }
  $parts = $email.Split("@")
  if ($parts.Count -ne 2) { return "<redacted_email>" }
  return "<redacted_email@{0}>" -f $parts[1]
}

function Add-Finding([ref]$arr, [string]$kind, [string]$pattern, [string]$relPath, [int]$lineNo, [string]$note) {
  $arr.Value += [pscustomobject]@{
    kind    = $kind
    pattern = $pattern
    file    = $relPath
    line    = $lineNo
    note    = $note
  }
}

function Load-AllowlistRegexes([string]$repoRoot, [string]$explicitPath) {
  $path = $null

  if ($explicitPath) {
    $p = $explicitPath
    if (-not [System.IO.Path]::IsPathRooted($p)) { $p = Join-Path $repoRoot $p }
    if (Test-Path -LiteralPath $p) { $path = $p }
  }

  if (-not $path) {
    $cand = Join-Path $repoRoot "scripts\pwsh\sec\ff-sec-allowlist.txt"
    if (Test-Path -LiteralPath $cand) { $path = $cand }
  }

  if (-not $path) { return @() }

  $lines = @()
  try { $lines = @(Get-Content -LiteralPath $path -Encoding UTF8 -ErrorAction Stop) } catch { $lines = @(Get-Content -LiteralPath $path -ErrorAction SilentlyContinue) }

  $out = New-Object System.Collections.Generic.List[object]
  foreach ($ln in $lines) {
    $t = ($ln ?? "").Trim()
    if (-not $t) { continue }
    if ($t.StartsWith("#") -or $t.StartsWith(";") -or $t.StartsWith("--")) { continue }

    $mode = "regex"
    $pat = $t

    if ($t.StartsWith("re:")) { $mode = "regex"; $pat = $t.Substring(3).Trim() }
    elseif ($t.StartsWith("literal:")) { $mode = "literal"; $pat = $t.Substring(8).Trim() }

    if (-not $pat) { continue }

    try {
      if ($mode -eq "literal") {
        $out.Add([regex]::new([regex]::Escape($pat), [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)) | Out-Null
      } else {
        $out.Add([regex]::new($pat, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)) | Out-Null
      }
    } catch {
      Warn ("Allowlist pattern invalid, skipped: {0}" -f $t)
    }
  }

  return @($out.ToArray())
}

function AllowlistedLine([regex[]]$allow, [string]$line) {
  if (-not $allow -or $allow.Count -eq 0) { return $false }
  foreach ($r in $allow) {
    try { if ($r.IsMatch($line)) { return $true } } catch {}
  }
  return $false
}

function Get-StagedNames() {
  $names = @(& git diff --cached --name-only --diff-filter=ACMR 2>$null)
  if ($LASTEXITCODE -ne 0) { throw "git diff --cached failed" }
  return @($names | ForEach-Object { ($_ ?? "").Trim() } | Where-Object { $_ })
}

function Get-TrackedNames() {
  $names = @(& git ls-files 2>$null)
  if ($LASTEXITCODE -ne 0) { throw "git ls-files failed" }
  return @($names | ForEach-Object { ($_ ?? "").Trim() } | Where-Object { $_ })
}

function Git-BlobSize([string]$spec) {
  $s = (& git cat-file -s $spec 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $s) { return -1 }
  $t = ($s | Out-String).Trim()
  [int64]$n = 0
  if ([int64]::TryParse($t, [ref]$n)) { return $n }
  return -1
}

function Get-StagedBlobLines([string]$relPath) {
  $spec = ":$relPath"
  $out = @(& git cat-file -p $spec 2>$null)
  if ($LASTEXITCODE -ne 0) { return @() }
  return @($out | ForEach-Object { [string]$_ })
}

function Get-StagedAddedLines([string]$relPath) {
  $diff = @(& git diff --cached -U0 -- $relPath 2>$null)
  if ($LASTEXITCODE -ne 0) { return @() }

  $added = New-Object System.Collections.Generic.List[string]
  foreach ($dl in $diff) {
    $s = [string]$dl
    if ($s.StartsWith("+++")) { continue }
    if ($s.StartsWith("+")) { $added.Add($s.Substring(1)) | Out-Null }
  }
  return @($added.ToArray())
}

# -------- collect files --------
$repoRoot = $null
$files = @()

if ($Mode -ne "Path") { $repoRoot = Get-RepoRoot } else { if (-not $TargetPath) { throw "Mode=Path requires -TargetPath" } }

if ($Mode -eq "Staged") {
  foreach ($n in (Get-StagedNames)) { $files += [pscustomobject]@{ rel = $n; full = (Join-Path $repoRoot $n) } }
} elseif ($Mode -eq "Tracked") {
  foreach ($n in (Get-TrackedNames)) { $files += [pscustomobject]@{ rel = $n; full = (Join-Path $repoRoot $n) } }
} else {
  $root = (Resolve-Path -LiteralPath $TargetPath).Path
  foreach ($it in (Get-ChildItem -LiteralPath $root -File -Recurse -ErrorAction Stop)) {
    $rel = $it.FullName.Substring($root.Length).TrimStart("\")
    $files += [pscustomobject]@{ rel = $rel; full = $it.FullName }
  }
}

$files = @($files | Sort-Object full -Unique)

# -------- patterns --------
$wantSecrets = ($Scan -eq "Secrets" -or $Scan -eq "SecretsAndPII")
$wantPII     = ($Scan -eq "PII" -or $Scan -eq "SecretsAndPII")

$rxPrivateKeyLine   = [regex]::new('-----BEGIN (?:RSA|EC|OPENSSH|PRIVATE) KEY-----', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
$rxPrivateKeyQuoted = [regex]::new("['""]\s*-----BEGIN ", [System.Text.RegularExpressions.RegexOptions]::None)

$rxAwsAccessKeyId   = [regex]::new('\b(?:AKIA|ASIA)[0-9A-Z]{16}\b', [System.Text.RegularExpressions.RegexOptions]::None)
$rxGitHubPat        = [regex]::new('\bghp_[A-Za-z0-9]{36,}\b', [System.Text.RegularExpressions.RegexOptions]::None)
$rxGitHubFGPat      = [regex]::new('\bgithub_pat_[A-Za-z0-9_]{20,}\b', [System.Text.RegularExpressions.RegexOptions]::None)
$rxGitLabPat        = [regex]::new('\bglpat-[A-Za-z0-9_-]{20,}\b', [System.Text.RegularExpressions.RegexOptions]::None)
$rxSlackToken       = [regex]::new('\bxox[baprs]-[A-Za-z0-9-]{10,}\b', [System.Text.RegularExpressions.RegexOptions]::None)
$rxStripeLive       = [regex]::new('\bsk_live_[0-9a-zA-Z]{20,}\b', [System.Text.RegularExpressions.RegexOptions]::None)

$rxKeyAssign = [regex]::new(
  '(?i)^\s*([A-Z0-9_]*?(?:password|passwd|pwd|token|api[_-]?key|private[_-]?key|secret(?:[_-]?(?:key|token|value))?)[A-Z0-9_]*)\s*[:=]\s*(.+?)\s*$',
  [System.Text.RegularExpressions.RegexOptions]::None
)

$redactedValues = @("<redacted>","redacted","***","null","none","disabled","changeme","your_api_key_here","replace_me","todo")

$rxEnvGetterAny = [regex]::new('(?i)\bos\.getenv\(|\bos\.environ\.get\(|\bgetenv\(|process\.env\.|Environment\.GetEnvironmentVariable\(|\$env:', [System.Text.RegularExpressions.RegexOptions]::None)
$rxEnvDefaultPy = [regex]::new('(?i)os\.(?:getenv|environ\.get)\(\s*["''][A-Za-z0-9_]+["'']\s*,\s*["'']([^"'']{8,})["'']\s*\)', [System.Text.RegularExpressions.RegexOptions]::None)
$rxEnvDefaultJs = [regex]::new('(?i)process\.env\.[A-Za-z0-9_]+\s*\|\|\s*["'']([^"'']{8,})["'']', [System.Text.RegularExpressions.RegexOptions]::None)

$rxEmail = [regex]::new('(?i)\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b', [System.Text.RegularExpressions.RegexOptions]::None)
$rxPhone = [regex]::new('(?x)\b(?:\+?\d[\d\-\s\(\)]{8,}\d)\b', [System.Text.RegularExpressions.RegexOptions]::None)

$findings = @()
$scanned = 0
$skipped = 0

$allow = @()
if ($Mode -ne "Path") { $allow = Load-AllowlistRegexes -repoRoot $repoRoot -explicitPath $AllowlistPath }

Say ("Mode={0} Scan={1}" -f $Mode, $Scan)

foreach ($f in $files) {
  if (Should-SkipPath $f.full) { $skipped++; continue }
  if ($wantSecrets -and (Is-SuspectSecretFile $f.rel)) {
    Add-Finding ([ref]$findings) "secrets" "suspect_secret_file" $f.rel 0 "file name/ext indicates secret material"
    if ($findings.Count -ge $MaxFindings) { break }
    continue
  }
  if (Is-BinaryLike $f.full) { $skipped++; continue }

  $lines = @()
  try {
    if ($Mode -eq "Staged") {
      $spec = ":$($f.rel)"
      $sz = Git-BlobSize $spec
      if ($sz -gt 0 -and $sz -gt $MaxFileBytes) { $lines = @(Get-StagedAddedLines -relPath $f.rel) }
      else { $lines = @(Get-StagedBlobLines -relPath $f.rel) }
    } else {
      if (-not (Test-Path -LiteralPath $f.full)) { $skipped++; continue }
      $lines = @(Get-Content -LiteralPath $f.full -ErrorAction Stop)
    }
  } catch { $skipped++; continue }

  $scanned++

  for ($i = 0; $i -lt $lines.Count; $i++) {
    $ln = $i + 1
    $line = [string]$lines[$i]
    if (-not $line) { continue }
    if (AllowlistedLine $allow $line) { continue }

    if ($wantSecrets) {
      if ($rxPrivateKeyLine.IsMatch($line)) {
        if ($rxPrivateKeyQuoted.IsMatch($line)) { continue }
        Add-Finding ([ref]$findings) "secrets" "private_key_block" $f.rel $ln "private key block marker"
      }

      if ($rxAwsAccessKeyId.IsMatch($line)) { Add-Finding ([ref]$findings) "secrets" "aws_access_key_id" $f.rel $ln "token_like" }
      if ($rxGitHubPat.IsMatch($line))      { Add-Finding ([ref]$findings) "secrets" "github_pat" $f.rel $ln "token_like" }
      if ($rxGitHubFGPat.IsMatch($line))    { Add-Finding ([ref]$findings) "secrets" "github_finegrained_pat" $f.rel $ln "token_like" }
      if ($rxGitLabPat.IsMatch($line))      { Add-Finding ([ref]$findings) "secrets" "gitlab_pat" $f.rel $ln "token_like" }
      if ($rxSlackToken.IsMatch($line))     { Add-Finding ([ref]$findings) "secrets" "slack_token" $f.rel $ln "token_like" }
      if ($rxStripeLive.IsMatch($line))     { Add-Finding ([ref]$findings) "secrets" "stripe_live_key" $f.rel $ln "token_like" }

      $m = $rxKeyAssign.Match($line)
      if ($m.Success) {
        $key = ($m.Groups[1].Value ?? "").Trim()
        $val = ($m.Groups[2].Value ?? "").Trim()
        $keyLower = $key.ToLowerInvariant()

        if ($keyLower -match '(^skip_|_present$|_exists$|_enabled$|_scan$|secrets_scan)') { continue }

        $val = ($val -split '\s[#;]\s', 2)[0].Trim()
        $valTrim = $val.Trim("`"","'"," ")
        if (-not $valTrim) { continue }

        if ($valTrim -match '^\$\{[^}]+\}$') { continue }
        if ($valTrim -match '^\$[A-Za-z_][A-Za-z0-9_]*$') { continue }
        if ($valTrim -match '^\$\([^)]+\)$') { continue }

        $defaultLit = $null
        $mDefPy = $rxEnvDefaultPy.Match($valTrim)
        if ($mDefPy.Success) { $defaultLit = $mDefPy.Groups[1].Value }
        else {
          $mDefJs = $rxEnvDefaultJs.Match($valTrim)
          if ($mDefJs.Success) { $defaultLit = $mDefJs.Groups[1].Value }
        }

        if (-not $defaultLit) {
          if ($rxEnvGetterAny.IsMatch($valTrim)) { continue }
        }

        $valEffective = $(if ($defaultLit) { $defaultLit } else { $valTrim })

        $isRedacted = $false
        foreach ($rv in $redactedValues) {
          if ($valEffective.Equals($rv, [System.StringComparison]::OrdinalIgnoreCase)) { $isRedacted = $true; break }
        }

        if (-not $isRedacted -and $valEffective.Length -ge 8) {
          $note = if ($defaultLit) { ("{0} default_literal_len={1}" -f $key, $valEffective.Length) } else { ("{0} value_len={1}" -f $key, $valEffective.Length) }
          Add-Finding ([ref]$findings) "secrets" "key_assignment" $f.rel $ln $note
        }
      }
    }

    if ($wantPII) {
      if ($rxEmail.IsMatch($line)) { Add-Finding ([ref]$findings) "pii" "email" $f.rel $ln (Redact-Email $rxEmail.Match($line).Value) }
      if ($rxPhone.IsMatch($line)) { Add-Finding ([ref]$findings) "pii" "phone" $f.rel $ln ("<redacted_phone len={0}>" -f $rxPhone.Match($line).Value.Length) }
    }

    if ($findings.Count -ge $MaxFindings) { break }
  }

  if ($findings.Count -ge $MaxFindings) { break }
}

Say ("Files scanned: {0} (skipped: {1})" -f $scanned, $skipped)

if ($findings.Count -gt 0) {
  Fail ("FINDINGS: {0} (showing up to {1})" -f $findings.Count, $MaxFindings)
  foreach ($x in ($findings | Select-Object -First $MaxFindings)) {
    if ($x.line -gt 0) { Write-Host ("[finding] {0}:{1} {2}/{3} {4}" -f $x.file, $x.line, $x.kind, $x.pattern, $x.note) }
    else { Write-Host ("[finding] {0} {1}/{2} {3}" -f $x.file, $x.kind, $x.pattern, $x.note) }
  }
} else {
  Say "PASS: no findings."
}

if ($EvidenceDir) {
  try {
    $ed = $EvidenceDir
    if ($Mode -ne "Path" -and -not [System.IO.Path]::IsPathRooted($ed)) { $ed = Join-Path $repoRoot $ed }
    New-Item -ItemType Directory -Force -Path $ed | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $ev = Join-Path $ed ("secscan_{0}.json" -f $stamp)

    $payload = [pscustomobject]@{
      ts = (Get-Date).ToString("o")
      mode = $Mode
      scan = $Scan
      files_scanned = $scanned
      files_skipped = $skipped
      findings_count = $findings.Count
      findings = ($findings | Select-Object -First $MaxFindings)
    }

    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ev -Encoding UTF8
    Say ("Evidence: {0}" -f $ev)
  } catch {
    Warn ("Evidence write failed: {0}" -f $_.Exception.Message)
  }
}

if ($findings.Count -gt 0) { exit 2 }
exit 0
