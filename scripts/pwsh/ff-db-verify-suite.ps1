#requires -Version 7.0
<#
FoxProFlow RUN • DB Verify Suite Runner (Deterministic v4)
file: scripts/pwsh/ff-db-verify-suite.ps1

Guarantees:
- No prompts.
- Deterministic resolve: first existing candidate wins.
- missing entry ONLY when resolved_files.Count == 0.
- No scalar .Count traps (arrays are always wrapped via @()).
- Evidence always written: meta/plan/summary/resolve_debug/error.
- JSON depth <= 60 (PS7 limit 100).

Hard rules:
- SQL executed ONLY via stdin: psql -f -
- No single-transaction flags (CONCURRENTLY-safe).

Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$ComposeFile = "",
  [string]$ProjectName = "",
  [string]$SuiteFile = "",
  [string]$EvidenceDir = "",
  [string]$RepoRoot = "",

  [string]$Service = "postgres",
  [string]$DbName  = "foxproflow",
  [string]$DbUser  = "admin",

  [switch]$StopOnFirstFail
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$VERSION = "2025-12-25.det.v4"

function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function Set-Utf8([string]$Path, [string]$Text) { $d = Split-Path $Path -Parent; if($d){Ensure-Dir $d}; $Text | Set-Content -LiteralPath $Path -Encoding utf8NoBOM }

function Norm-Seps([string]$p) {
  if ([string]::IsNullOrWhiteSpace($p)) { return $p }
  return ($IsWindows ? ($p -replace '/','\') : $p)
}

function Clean-Entry([string]$s) {
  if ($null -eq $s) { return "" }
  $t = $s

  $t = $t -replace "^\uFEFF",""                       # BOM
  $t = [regex]::Replace($t, '[\p{Cc}\p{Cf}]', '')     # control+format (zero-width etc.)
  $t = $t -replace "\u00A0",""                        # NBSP

  $t = $t.Trim()
  if ($t -eq "") { return "" }

  if ($t.StartsWith("#") -or $t.StartsWith(";") -or $t.StartsWith("--")) { return "" }

  $t = $t -replace '\s+#.*$',''
  $t = $t -replace '\s+--.*$',''
  $t = $t -replace '\s+;.*$',''
  $t = $t.Trim()
  if ($t -eq "") { return "" }

  if (($t.StartsWith('"') -and $t.EndsWith('"')) -or ($t.StartsWith("'") -and $t.EndsWith("'"))) {
    if ($t.Length -ge 2) { $t = $t.Substring(1, $t.Length-2).Trim() }
  }

  $t = Norm-Seps $t
  $t = $t -replace '^\.[\\/]+',''   # drop leading .\

  if ($IsWindows -and $t.StartsWith('\') -and -not $t.StartsWith('\\')) {
    $t = $t.TrimStart('\')
  }

  if ($IsWindows) {
    if ($t.StartsWith('\\')) {
      $rest = $t.Substring(2) -replace '\\{2,}','\'
      $t = '\\' + $rest
    } else {
      $t = $t -replace '\\{2,}','\'
    }
  }

  return $t
}

function Resolve-RepoRoot([string]$rr) {
  if (-not [string]::IsNullOrWhiteSpace($rr)) {
    $p = Norm-Seps $rr
    if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
    return $p
  }
  try { return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path } catch { return "" }
}

function Resolve-SuiteFile([string]$suiteFile, [string]$repoRoot) {
  if ([string]::IsNullOrWhiteSpace($suiteFile)) { throw "SuiteFile is required." }
  $sf = Norm-Seps $suiteFile
  if (Test-Path -LiteralPath $sf) { return (Resolve-Path -LiteralPath $sf).Path }
  if ($repoRoot) {
    $cand = Join-Path $repoRoot $sf
    if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }
  }
  $cand2 = Join-Path (Get-Location).Path $sf
  if (Test-Path -LiteralPath $cand2) { return (Resolve-Path -LiteralPath $cand2).Path }
  throw "SuiteFile not found: $suiteFile"
}

function Derive-WorktreeRootFromSuite([string]$suiteFilePath) {
  $p = Norm-Seps $suiteFilePath
  $m = [regex]::Match($p, '^(.*)[\\/]scripts[\\/]sql[\\/]verify[\\/]suites[\\/].+$', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  if ($m.Success) { return $m.Groups[1].Value }
  return ""
}

function Find-GitRoot([string]$startDir) {
  $d = $startDir
  while ($d -and (Test-Path -LiteralPath $d)) {
    $g = Join-Path $d ".git"
    if (Test-Path -LiteralPath $g) { return $d }
    $p = Split-Path $d -Parent
    if ($p -eq $d) { break }
    $d = $p
  }
  return ""
}

function Resolve-ComposeFile([string]$composeFile, [string]$repoRoot) {
  if (-not [string]::IsNullOrWhiteSpace($composeFile)) {
    $c = Norm-Seps $composeFile
    if (-not (Test-Path -LiteralPath $c)) { throw "ComposeFile not found: $composeFile" }
    return (Resolve-Path -LiteralPath $c).Path
  }
  if ($repoRoot) {
    $p = Join-Path $repoRoot "docker-compose.yml"
    if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
  }
  throw "ComposeFile is required."
}

function Resolve-ProjectName([string]$pn) {
  if (-not [string]::IsNullOrWhiteSpace($pn)) { return $pn }
  if ($env:FF_PROJECT) { return $env:FF_PROJECT }
  if ($env:FF_COMPOSE_PROJECT) { return $env:FF_COMPOSE_PROJECT }
  if ($env:COMPOSE_PROJECT_NAME) { return $env:COMPOSE_PROJECT_NAME }
  return "foxproflow-mvp20"
}

function Unique-List([string[]]$items) {
  $seen = @{}
  $out = New-Object System.Collections.Generic.List[string]
  foreach ($x in ($items ?? @())) {
    if ([string]::IsNullOrWhiteSpace($x)) { continue }
    $k = Norm-Seps $x
    if (-not $seen.ContainsKey($k)) { $seen[$k] = $true; $out.Add($k) | Out-Null }
  }
  return @($out.ToArray())
}

function Make-Candidates([string]$entry, [string]$worktreeRoot, [string]$repoRoot, [string]$cwd) {
  $e = Clean-Entry $entry
  if ($e -eq "") { return @() }

  $cands = New-Object System.Collections.Generic.List[string]

  if ([System.IO.Path]::IsPathRooted($e)) {
    $cands.Add($e) | Out-Null
  } else {
    if ($worktreeRoot) { $cands.Add((Join-Path $worktreeRoot $e)) | Out-Null } # FIRST
    if ($repoRoot)     { $cands.Add((Join-Path $repoRoot $e)) | Out-Null }
    if ($cwd)          { $cands.Add((Join-Path $cwd $e)) | Out-Null }
    $cands.Add($e) | Out-Null
  }

  return (Unique-List @($cands.ToArray()))
}

function Resolve-CandidatesToFiles([string[]]$candidates) {
  $dbg = @()
  $chosen = $null
  $files = @()

  foreach ($c in ($candidates ?? @())) {
    if ([string]::IsNullOrWhiteSpace($c)) { continue }

    # wildcard
    if ($c -match '[\*\?]') {
      $items = @(Get-ChildItem -Path $c -File -ErrorAction SilentlyContinue)
      $dbg += [pscustomobject]@{ candidate=$c; kind="wildcard"; exists=($items.Count -gt 0); count=$items.Count }
      if ($items.Count -gt 0) {
        $chosen = $c
        $files = @($items | Sort-Object FullName | Select-Object -ExpandProperty FullName)
        break
      }
      continue
    }

    $exists = $false
    try { $exists = Test-Path -LiteralPath $c } catch { $exists = $false }
    $dbg += [pscustomobject]@{ candidate=$c; kind="literal"; exists=$exists }
    if (-not $exists) { continue }

    $full = (Resolve-Path -LiteralPath $c).Path
    $item = Get-Item -LiteralPath $full -ErrorAction Stop

    if ($item.PSIsContainer) {
      $found = @(Get-ChildItem -LiteralPath $full -File -Filter "*.sql" -Recurse -ErrorAction SilentlyContinue | Sort-Object FullName)
      $dbg += [pscustomobject]@{ candidate=$full; kind="dir"; exists=$true; sql_count=$found.Count }
      $chosen = $full
      $files = @($found | Select-Object -ExpandProperty FullName)
      break
    }

    $chosen = $full
    $files = @($full)
    break
  }

  return [pscustomobject]@{
    chosen = $chosen
    files = @($files)
    debug = $dbg
  }
}

function Invoke-Psql-Stdin([string]$sqlText, [string]$label, [string]$logPath) {
  $argv = @(
    "compose","--ansi","never",
    "-f",$ComposeFile,
    "-p",$ProjectName,
    "exec","-T",$Service,
    "psql","-U",$DbUser,"-d",$DbName,
    "-X","-v","ON_ERROR_STOP=1",
    "-f","-"
  )
  $out = $sqlText | & docker @argv 2>&1
  $code = $LASTEXITCODE
  if ($logPath) {
    Set-Utf8 $logPath ("== VERIFY SQL via STDIN ==`nlabel={0}`nts={1}`nargv=docker {2}`n`n{3}`nexit_code={4}`n" -f `
      $label, (Now-Iso), ($argv -join " "), ($out | Out-String), $code)
  }
  return $code
}

# ---------------- RUN ----------------
$started = Now-Iso
$exitCode = 0
$failReason = ""
$plan = @()
$results = @()
$missing = @()
$resolveDebug = @()
$suiteName = "suite"

$RepoRoot    = Resolve-RepoRoot $RepoRoot
$SuiteFile   = Resolve-SuiteFile -suiteFile $SuiteFile -repoRoot $RepoRoot
$ComposeFile = Resolve-ComposeFile -composeFile $ComposeFile -repoRoot $RepoRoot
$ProjectName = Resolve-ProjectName $ProjectName

$suiteDir = Split-Path $SuiteFile -Parent
$worktreeRoot = Derive-WorktreeRootFromSuite $SuiteFile
$gitRoot = Find-GitRoot $suiteDir
$cwd = (Get-Location).Path
$suiteName = [System.IO.Path]::GetFileNameWithoutExtension($SuiteFile)

if ($EvidenceDir) { Ensure-Dir $EvidenceDir }

try {
  $lines = Get-Content -LiteralPath $SuiteFile -ErrorAction Stop
  $entries = @()
  foreach ($ln in $lines) {
    $e = Clean-Entry $ln
    if ($e) { $entries += $e }
  }

  $allFiles = @()

  foreach ($e in $entries) {
    $cands = Make-Candidates -entry $e -worktreeRoot $worktreeRoot -repoRoot $RepoRoot -cwd $cwd
    $r = Resolve-CandidatesToFiles -candidates $cands

    $resolveDebug += [pscustomobject]@{
      entry = $e
      candidates = $cands
      chosen = $r.chosen
      resolved_count = $r.files.Count
      resolved_files = $r.files
      debug = $r.debug
    }

    if ($r.files.Count -eq 0) {
      $missing += $e
    } else {
      $allFiles += $r.files
    }
  }

  # uniq plan stable
  $seen = @{}
  $planList = New-Object System.Collections.Generic.List[string]
  foreach ($f in $allFiles) {
    if (-not $seen.ContainsKey($f)) { $seen[$f] = $true; $planList.Add($f) | Out-Null }
  }
  $plan = @($planList.ToArray())

  if ($missing.Count -gt 0) {
    throw ("Verify suite has missing entries: " + ($missing -join "; "))
  }
  if ($plan.Count -eq 0) {
    throw "Verify suite resolved to 0 sql files."
  }

  $ok = $true
  for ($i=0; $i -lt $plan.Count; $i++) {
    $sqlFile = $plan[$i]
    $log = if ($EvidenceDir) { Join-Path $EvidenceDir ("verify_{0:000}_{1}.log" -f ($i+1), ([IO.Path]::GetFileName($sqlFile))) } else { "" }
    $sql = Get-Content -Raw -LiteralPath $sqlFile -Encoding UTF8
    $code = Invoke-Psql-Stdin -sqlText $sql -label $sqlFile -logPath $log
    $pass = ($code -eq 0)
    $results += [pscustomobject]@{ idx=($i+1); file=$sqlFile; ok=$pass; exit_code=$code }
    if (-not $pass) { $ok = $false; if ($StopOnFirstFail) { break } }
  }
  if (-not $ok) { $exitCode = 1 }

} catch {
  $failReason = $_.Exception.Message
  $exitCode = 1
} finally {
  if ($EvidenceDir) {
    $meta = [pscustomobject]@{
      version = $VERSION
      suite = $suiteName
      suite_file = $SuiteFile
      ts_started = $started
      ts_ended = Now-Iso
      ok = ($exitCode -eq 0)
      fail_reason = $failReason
      compose_file = $ComposeFile
      project_name = $ProjectName
      repo_root = $RepoRoot
      suite_dir = $suiteDir
      worktree_root = $worktreeRoot
      git_root = $gitRoot
      cwd = $cwd
      missing = $missing
      plan_count = $plan.Count
    }
    Set-Utf8 (Join-Path $EvidenceDir ("verify_suite_{0}_meta.json" -f $suiteName)) ($meta | ConvertTo-Json -Depth 60)
    Set-Utf8 (Join-Path $EvidenceDir ("verify_suite_{0}_plan.txt" -f $suiteName)) (($plan | ForEach-Object { $_ }) -join "`n")
    Set-Utf8 (Join-Path $EvidenceDir ("verify_suite_{0}_resolve_debug.json" -f $suiteName)) ($resolveDebug | ConvertTo-Json -Depth 30)
    $summary = [pscustomobject]@{
      suite = $suiteName
      ok = ($exitCode -eq 0)
      fail_reason = $failReason
      results = $results
    }
    Set-Utf8 (Join-Path $EvidenceDir ("verify_suite_{0}_summary.json" -f $suiteName)) ($summary | ConvertTo-Json -Depth 60)
    if ($failReason) { Set-Utf8 (Join-Path $EvidenceDir ("verify_suite_{0}_error.txt" -f $suiteName)) $failReason }
  }
}

if ($exitCode -eq 0) { exit 0 } else { Write-Error $failReason; exit 1 }
