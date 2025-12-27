#requires -Version 7.0
<#
FoxProFlow RUN • Backup helper
file: scripts/pwsh/ff-backup.ps1

Creates backup under ops/_backups/<stamp>:
  - manifest.json
  - digest.sha256
  - snapshot_docker-compose.yml
  - snapshot_<composeLeaf>.yml (for extra compose files, if provided)
  - snapshot_docker-compose.env.dynamic.yml (if exists; redacted by default)
  - snapshot_.env (if exists; redacted by default)
  - pg_<db>.dump (custom format)
  - pg_globals.sql (globals-only, no role passwords)

Prints: outDir: <ABS_PATH>   (for ff-release-m0.ps1 parser)

Lane: A-RUN only.

Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$BackupDir = "",

  # Back-compat: single compose file
  [string]$ComposeFile = "",

  # New: multiple compose files (override support)
  [string[]]$ComposeFiles = @(),

  [string]$ProjectName = $(if ($env:FF_COMPOSE_PROJECT) { $env:FF_COMPOSE_PROJECT } elseif ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "foxproflow-mvp20" }),

  [string]$PgService = "postgres",

  # If not explicitly passed, script tries to auto-detect from container env (POSTGRES_USER/POSTGRES_DB)
  [string]$PgUser = "admin",
  [string]$DbName = "foxproflow",

  # Keep tmp files inside container (for post-mortem debugging)
  [switch]$NoCleanupTmp,

  # Skip snapshots entirely (compose/env)
  [switch]$NoSnapshots,

  # If set — snapshots are copied as-is (NOT recommended; FlowSec-first default is redaction)
  [switch]$NoRedactSnapshots
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$SCRIPT_VERSION = "2025-12-27.v2"

# Silence docker compose warnings about missing pgAdmin env vars (local-only; no compose/env changes)
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_EMAIL))    { $env:PGADMIN_EMAIL    = "disabled@local" }
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_PASSWORD)) { $env:PGADMIN_PASSWORD = "disabled" }

function Now-Stamp { (Get-Date).ToString("yyyyMMdd-HHmmss") }
function Now-Iso   { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }

function Ensure-Dir([string]$p) {
  if ([string]::IsNullOrWhiteSpace($p)) { return }
  if (-not (Test-Path -LiteralPath $p)) {
    New-Item -ItemType Directory -Force -Path $p | Out-Null
  }
}

function Set-Utf8([string]$Path, [string]$Text) {
  $d = Split-Path $Path -Parent
  if ($d) { Ensure-Dir $d }
  $Text | Set-Content -LiteralPath $Path -Encoding utf8NoBOM
}

function Add-Utf8([string]$Path, [string]$Text) {
  $Text | Add-Content -LiteralPath $Path -Encoding utf8
}

function Find-RepoRoot([string]$from) {
  $d = (Resolve-Path -LiteralPath $from).Path
  if (-not (Test-Path -LiteralPath $d -PathType Container)) { $d = Split-Path $d -Parent }
  while ($true) {
    if (Test-Path -LiteralPath (Join-Path $d ".git")) { return $d }
    if (Test-Path -LiteralPath (Join-Path $d "docker-compose.yml")) { return $d }
    $p = Split-Path $d -Parent
    if (-not $p -or $p -eq $d) { break }
    $d = $p
  }
  throw "Repo root not found from: $from"
}

function Resolve-ComposePaths([string]$repoRoot, [string]$composeFile, [string[]]$composeFiles) {
  $paths = New-Object System.Collections.Generic.List[string]
  if ($composeFiles -and $composeFiles.Count -gt 0) {
    foreach ($p in $composeFiles) { if ($p) { $paths.Add($p) | Out-Null } }
  } else {
    if ([string]::IsNullOrWhiteSpace($composeFile)) { $composeFile = Join-Path $repoRoot "docker-compose.yml" }
    $paths.Add($composeFile) | Out-Null
  }

  $resolved = New-Object System.Collections.Generic.List[string]
  foreach ($p in $paths) {
    $pp = $p
    if (-not [System.IO.Path]::IsPathRooted($pp)) { $pp = Join-Path $repoRoot $pp }
    if (-not (Test-Path -LiteralPath $pp)) { throw "Compose file not found: $pp" }
    $resolved.Add((Resolve-Path -LiteralPath $pp).Path) | Out-Null
  }

  # de-dup preserve order
  $seen = @{}
  $uniq = New-Object System.Collections.Generic.List[string]
  foreach ($r in $resolved) {
    $k = $r.ToLowerInvariant()
    if (-not $seen.ContainsKey($k)) { $seen[$k] = $true; $uniq.Add($r) | Out-Null }
  }

  return ,$uniq.ToArray()
}

function Dc([string[]]$composePaths, [string]$projectName, [string[]]$composeArgs) {
  $argv = New-Object System.Collections.Generic.List[string]
  $argv.Add("compose") | Out-Null
  $argv.Add("--ansi") | Out-Null
  $argv.Add("never") | Out-Null
  foreach ($cf in $composePaths) { $argv.Add("-f") | Out-Null; $argv.Add($cf) | Out-Null }
  if ($projectName) { $argv.Add("-p") | Out-Null; $argv.Add($projectName) | Out-Null }
  foreach ($a in $composeArgs) { $argv.Add($a) | Out-Null }

  $out  = & docker @($argv.ToArray()) 2>&1
  $code = $LASTEXITCODE

  return [pscustomobject]@{
    code = [int]$code
    out  = ($out | Out-String)
    argv = ("docker " + ($argv.ToArray() -join " "))
  }
}

function Docker-ExecSh([string]$cid, [string]$cmd) {
  $out  = & docker exec -i $cid sh -lc $cmd 2>&1
  $code = $LASTEXITCODE
  return [pscustomobject]@{
    code = [int]$code
    out  = ($out | Out-String)
    cmd  = $cmd
  }
}

function Extract-ContainerId([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return "" }
  $lines = $text -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
  foreach ($ln in $lines) {
    if ($ln -match '^[0-9a-f]{12,64}$') { return $ln }
  }
  return ""
}

function Is-SensitiveKey([string]$key) {
  if ([string]::IsNullOrWhiteSpace($key)) { return $false }
  $k = $key.ToUpperInvariant()

  # common cloud prefixes
  if ($k -like "AWS_*" -or $k -like "GCP_*" -or $k -like "AZURE_*") { return $true }

  # explicit known
  if ($k -eq "PGADMIN_PASSWORD") { return $true }

  # token-like patterns with boundaries
  if ($k -match '(^|_)(PASS|PASSWORD|SECRET|TOKEN|APIKEY|API_KEY|ACCESS_KEY|CLIENT_SECRET|BEARER|JWT|PRIVATE_KEY)($|_)') { return $true }

  return $false
}

function Redact-Text([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return $text }

  $lines = $text -split "`r?`n"
  for ($i=0; $i -lt $lines.Length; $i++) {
    $line = $lines[$i]

    $trim = $line.Trim()
    if ([string]::IsNullOrWhiteSpace($trim) -or $trim.StartsWith("#")) { continue }

    # env style: [export ]KEY=VALUE
    $m1 = [regex]::Match($line, '^\s*(?:export\s+)?(?<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?<val>.*)\s*$')
    if ($m1.Success) {
      $k = $m1.Groups["key"].Value
      if (Is-SensitiveKey $k) {
        $prefix = $line.Substring(0, $m1.Groups["key"].Index)
        $lines[$i] = ("{0}{1}=***REDACTED***" -f $prefix, $k)
        continue
      }
    }

    # yaml style: KEY: VALUE
    $m2 = [regex]::Match($line, '^\s*(?<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?<val>.*)\s*$')
    if ($m2.Success) {
      $k = $m2.Groups["key"].Value
      if (Is-SensitiveKey $k) {
        $indent = $line.Substring(0, $m2.Groups["key"].Index)
        $lines[$i] = ("{0}{1}: '***REDACTED***'" -f $indent, $k)
        continue
      }
    }

    # yaml env list style: - KEY=VALUE
    $m3 = [regex]::Match($line, '^\s*-\s*(?<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?<val>.*)\s*$')
    if ($m3.Success) {
      $k = $m3.Groups["key"].Value
      if (Is-SensitiveKey $k) {
        $lead = [regex]::Replace($line, '(^\s*-\s*).+$', '$1')
        $lines[$i] = ("{0}{1}=***REDACTED***" -f $lead, $k)
        continue
      }
    }
  }

  return ($lines -join "`r`n")
}

function Snapshot-TextFile([string]$src, [string]$dst, [switch]$noRedact) {
  if (-not (Test-Path -LiteralPath $src)) { return $false }
  $raw = Get-Content -Raw -LiteralPath $src
  if (-not $noRedact) { $raw = Redact-Text $raw }
  Set-Utf8 $dst $raw
  return $true
}

function FileMeta([string]$rootAbs, [string]$pathAbs) {
  if (-not (Test-Path -LiteralPath $pathAbs)) { return $null }
  $fi = Get-Item -LiteralPath $pathAbs
  $rel = $fi.FullName
  if ($rootAbs -and $fi.FullName.StartsWith($rootAbs, [System.StringComparison]::OrdinalIgnoreCase)) {
    $rel = $fi.FullName.Substring($rootAbs.Length).TrimStart("\","/")
  }
  $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $fi.FullName).Hash
  return [pscustomobject]@{
    rel    = $rel
    name   = $fi.Name
    bytes  = [int64]$fi.Length
    ts     = $fi.LastWriteTime.ToString("o")
    sha256 = $h
  }
}

# ---- MAIN ----

# ensure docker exists
$null = Get-Command docker -ErrorAction Stop

$repoRoot = Find-RepoRoot $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($ProjectName)) {
  throw "ProjectName is empty. Provide -ProjectName or set FF_COMPOSE_PROJECT/COMPOSE_PROJECT_NAME."
}

$composePaths = Resolve-ComposePaths -repoRoot $repoRoot -composeFile $ComposeFile -composeFiles $ComposeFiles

if ([string]::IsNullOrWhiteSpace($BackupDir)) {
  $BackupDir = Join-Path $repoRoot "ops\_backups"
}
Ensure-Dir $BackupDir

$stamp = Now-Stamp
$outDir = Join-Path $BackupDir $stamp
Ensure-Dir $outDir
$outDirAbs = (Resolve-Path -LiteralPath $outDir).Path

$backupLog   = Join-Path $outDir "backup.log"
$manifestP   = Join-Path $outDir "manifest.json"
$digestP     = Join-Path $outDir "digest.sha256"

Set-Utf8 $backupLog ("ts={0}`nscript=ff-backup.ps1`nversion={1}`nout_dir={2}`n" -f (Now-Iso), $SCRIPT_VERSION, $outDirAbs)

# snapshots (FlowSec-first: redact .env and env-dynamic by default)
if (-not $NoSnapshots) {
  try {
    $primary = $composePaths[0]
    Copy-Item -Force -LiteralPath $primary -Destination (Join-Path $outDir "snapshot_docker-compose.yml")

    # also snapshot every compose file under its own name (useful when overrides are passed)
    foreach ($cf in $composePaths) {
      $leaf = Split-Path $cf -Leaf
      $dst = Join-Path $outDir ("snapshot_{0}" -f $leaf)
      if (-not (Test-Path -LiteralPath $dst)) {
        Copy-Item -Force -LiteralPath $cf -Destination $dst
      }
    }

    $dyn = Join-Path $repoRoot "docker-compose.env.dynamic.yml"
    if (Test-Path -LiteralPath $dyn) {
      $ok = Snapshot-TextFile -src $dyn -dst (Join-Path $outDir "snapshot_docker-compose.env.dynamic.yml") -noRedact:$NoRedactSnapshots
      if ($ok) { Add-Utf8 $backupLog "snapshot: docker-compose.env.dynamic.yml (redacted=$([bool](-not $NoRedactSnapshots)))`n" }
    }

    $envFile = Join-Path $repoRoot ".env"
    if (Test-Path -LiteralPath $envFile) {
      $ok = Snapshot-TextFile -src $envFile -dst (Join-Path $outDir "snapshot_.env") -noRedact:$NoRedactSnapshots
      if ($ok) { Add-Utf8 $backupLog "snapshot: .env (redacted=$([bool](-not $NoRedactSnapshots)))`n" }
    }
  } catch {
    Add-Utf8 $backupLog ("WARN: snapshots failed: {0}`n" -f $_.Exception.Message)
  }
} else {
  Add-Utf8 $backupLog "snapshots: disabled`n"
}

# resolve container id (robust against warnings)
$ps = Dc -composePaths $composePaths -projectName $ProjectName -composeArgs @("ps","-q",$PgService)
if ($ps.code -ne 0) {
  Set-Utf8 (Join-Path $outDir "compose_ps_q.log") ("ts={0}`nargv={1}`nexit_code={2}`n`n{3}" -f (Now-Iso), $ps.argv, $ps.code, $ps.out)
  throw "docker compose ps -q $PgService failed (exit=$($ps.code)). See compose_ps_q.log in $outDirAbs"
}

Set-Utf8 (Join-Path $outDir "compose_ps_q.log") ("ts={0}`nargv={1}`nexit_code={2}`n`n{3}" -f (Now-Iso), $ps.argv, $ps.code, $ps.out)

$cid = Extract-ContainerId $ps.out
if ([string]::IsNullOrWhiteSpace($cid)) {
  throw "Cannot extract container id for service '$PgService' from output. See compose_ps_q.log in $outDirAbs"
}

Add-Utf8 $backupLog ("pg_container_id={0}`n" -f $cid)

# auto-detect db/user from container env (only if not explicitly passed)
$effectiveUser = $PgUser
$effectiveDb   = $DbName

$wantDetectUser = (-not $PSBoundParameters.ContainsKey("PgUser")) -or [string]::IsNullOrWhiteSpace($PgUser)
$wantDetectDb   = (-not $PSBoundParameters.ContainsKey("DbName")) -or [string]::IsNullOrWhiteSpace($DbName)

try {
  if ($wantDetectUser) {
    $rU = Docker-ExecSh $cid 'echo "${POSTGRES_USER:-}"'
    if ($rU.code -eq 0) {
      $detU = ($rU.out | Out-String).Trim()
      if (-not [string]::IsNullOrWhiteSpace($detU)) { $effectiveUser = $detU }
    }
  }
  if ($wantDetectDb) {
    $rD = Docker-ExecSh $cid 'echo "${POSTGRES_DB:-}"'
    if ($rD.code -eq 0) {
      $detD = ($rD.out | Out-String).Trim()
      if (-not [string]::IsNullOrWhiteSpace($detD)) { $effectiveDb = $detD }
    }
  }
} catch {}

Add-Utf8 $backupLog ("pg_user={0}`n" -f $effectiveUser)
Add-Utf8 $backupLog ("db_name={0}`n" -f $effectiveDb)

$tmpDump    = ("/tmp/ff_backup_{0}_{1}.dump" -f $stamp, $effectiveDb)
$tmpGlobals = ("/tmp/ff_backup_{0}_globals.sql" -f $stamp)

# dump inside container (binary-safe)
$cmd1 = ('pg_dump -U "{0}" -d "{1}" -Fc --no-owner --no-privileges -f "{2}"' -f $effectiveUser, $effectiveDb, $tmpDump)
$out1 = Docker-ExecSh $cid $cmd1
Set-Utf8 (Join-Path $outDir "pg_dump_exec.log") ("ts={0}`ncid={1}`ncmd={2}`nexit_code={3}`n`n{4}" -f (Now-Iso), $cid, $out1.cmd, $out1.code, $out1.out)
if ($out1.code -ne 0) { throw "pg_dump failed (exit=$($out1.code)). See pg_dump_exec.log in $outDirAbs" }

# globals (no role passwords = FlowSec-first)
$cmd2 = ('pg_dumpall -U "{0}" --globals-only --no-role-passwords -f "{1}"' -f $effectiveUser, $tmpGlobals)
$out2 = Docker-ExecSh $cid $cmd2
Set-Utf8 (Join-Path $outDir "pg_globals_exec.log") ("ts={0}`ncid={1}`ncmd={2}`nexit_code={3}`n`n{4}" -f (Now-Iso), $cid, $out2.cmd, $out2.code, $out2.out)
if ($out2.code -ne 0) { throw "pg_dumpall --globals-only failed (exit=$($out2.code)). See pg_globals_exec.log in $outDirAbs" }

# copy to host
$dstDump    = Join-Path $outDir ("pg_{0}.dump" -f $effectiveDb)
$dstGlobals = Join-Path $outDir "pg_globals.sql"

$srcDump    = "{0}:{1}" -f $cid, $tmpDump
$srcGlobals = "{0}:{1}" -f $cid, $tmpGlobals

$out3 = & docker cp $srcDump $dstDump 2>&1
$code3 = $LASTEXITCODE
Set-Utf8 (Join-Path $outDir "docker_cp_dump.log") ("ts={0}`nsrc={1}`ndst={2}`nexit_code={3}`n`n{4}" -f (Now-Iso), $srcDump, $dstDump, $code3, ($out3 | Out-String))
if ($code3 -ne 0) { throw "docker cp dump failed (exit=$code3). See docker_cp_dump.log in $outDirAbs" }

$out4 = & docker cp $srcGlobals $dstGlobals 2>&1
$code4 = $LASTEXITCODE
Set-Utf8 (Join-Path $outDir "docker_cp_globals.log") ("ts={0}`nsrc={1}`ndst={2}`nexit_code={3}`n`n{4}" -f (Now-Iso), $srcGlobals, $dstGlobals, $code4, ($out4 | Out-String))
if ($code4 -ne 0) { throw "docker cp globals failed (exit=$code4). See docker_cp_globals.log in $outDirAbs" }

# sanity: files exist and non-empty
if (-not (Test-Path -LiteralPath $dstDump)) { throw "Dump file missing after docker cp: $dstDump" }
if ((Get-Item -LiteralPath $dstDump).Length -lt 1024) { Add-Utf8 $backupLog "WARN: dump size < 1KB (check if db is empty or dump failed silently)`n" }

if (-not (Test-Path -LiteralPath $dstGlobals)) { throw "Globals file missing after docker cp: $dstGlobals" }
if ((Get-Item -LiteralPath $dstGlobals).Length -lt 64) { Add-Utf8 $backupLog "WARN: globals size < 64B (check pg_dumpall output)`n" }

if (-not $NoCleanupTmp) {
  try {
    $cmdRm = ('rm -f "{0}" "{1}"' -f $tmpDump, $tmpGlobals)
    $null = Docker-ExecSh $cid $cmdRm
  } catch {}
} else {
  Add-Utf8 $backupLog "tmp_cleanup: disabled`n"
}

# gather git info (best-effort)
$gitHead = ""
$gitDirty = $false
$gitIgnoredOutDir = $null
try {
  Push-Location $repoRoot
  $gitHead = ((& git rev-parse HEAD 2>$null) | Out-String).Trim()
  $st = (& git status --porcelain 2>$null)
  if ($st) { $gitDirty = $true }

  # is outDir ignored by git?
  & git check-ignore -q $outDir 2>$null
  if ($LASTEXITCODE -eq 0) { $gitIgnoredOutDir = $true } else { $gitIgnoredOutDir = $false }
} catch {
} finally {
  try { Pop-Location } catch {}
}

# digest + manifest (evidence-first)
$artifactAbs = New-Object System.Collections.Generic.List[string]

# snapshots
if (-not $NoSnapshots) {
  $artifactAbs.Add((Join-Path $outDir "snapshot_docker-compose.yml")) | Out-Null
  foreach ($cf in $composePaths) {
    $leaf = Split-Path $cf -Leaf
    $artifactAbs.Add((Join-Path $outDir ("snapshot_{0}" -f $leaf))) | Out-Null
  }
  $artifactAbs.Add((Join-Path $outDir "snapshot_docker-compose.env.dynamic.yml")) | Out-Null
  $artifactAbs.Add((Join-Path $outDir "snapshot_.env")) | Out-Null
}

# dumps
$artifactAbs.Add($dstDump) | Out-Null
$artifactAbs.Add($dstGlobals) | Out-Null

# logs
$artifactAbs.Add($backupLog) | Out-Null
$artifactAbs.Add((Join-Path $outDir "compose_ps_q.log")) | Out-Null
$artifactAbs.Add((Join-Path $outDir "pg_dump_exec.log")) | Out-Null
$artifactAbs.Add((Join-Path $outDir "pg_globals_exec.log")) | Out-Null
$artifactAbs.Add((Join-Path $outDir "docker_cp_dump.log")) | Out-Null
$artifactAbs.Add((Join-Path $outDir "docker_cp_globals.log")) | Out-Null

# build file meta for existing paths
$metas = @()
foreach ($p in $artifactAbs) {
  if (Test-Path -LiteralPath $p) {
    $m = FileMeta -rootAbs $outDirAbs -pathAbs $p
    if ($m) { $metas += $m }
  }
}

# digest.sha256 (exclude manifest/digest itself; we create digest before manifest)
$dlines = @()
foreach ($m in $metas) {
  $dlines += ("{0}  {1}" -f $m.sha256, $m.rel)
}
Set-Utf8 $digestP (($dlines -join "`r`n") + "`r`n")

# now include digest meta too
$metas += FileMeta -rootAbs $outDirAbs -pathAbs $digestP

$manifest = [pscustomobject]@{
  ts = Now-Iso
  out_dir = $outDirAbs
  script = [pscustomobject]@{ name="ff-backup.ps1"; version=$SCRIPT_VERSION }
  git = [pscustomobject]@{ head=$gitHead; dirty=$gitDirty; out_dir_gitignored=$gitIgnoredOutDir }
  compose = [pscustomobject]@{
    compose_files = $composePaths
    project_name = $ProjectName
    pg_service = $PgService
  }
  postgres = [pscustomobject]@{
    container_id = $cid
    user = $effectiveUser
    db_name = $effectiveDb
  }
  flags = [pscustomobject]@{
    no_cleanup_tmp = [bool]$NoCleanupTmp
    no_snapshots = [bool]$NoSnapshots
    no_redact_snapshots = [bool]$NoRedactSnapshots
  }
  files = $metas
}

Set-Utf8 $manifestP (($manifest | ConvertTo-Json -Depth 64))

Add-Utf8 $backupLog ("manifest={0}`n" -f $manifestP)
Add-Utf8 $backupLog ("digest={0}`n" -f $digestP)

if ($gitIgnoredOutDir -eq $false) {
  Add-Utf8 $backupLog "WARN: backup outDir is NOT git-ignored (risk of accidental commit). Consider .gitignore for ops/_backups.`n"
}

# IMPORTANT for ff-release-m0.ps1 parser:
Write-Output ("outDir: " + $outDirAbs)
exit 0
