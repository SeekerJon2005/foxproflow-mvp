#requires -Version 7.0
<#
FoxProFlow RUN • Release Gate M0/M0+
file: scripts/pwsh/ff-release-m0.ps1

Lane: A-RUN (compose/env/scripts/runbooks). No src/** edits, no scripts/sql/** edits.

Goal:
  precheck ->
  (optional) flowsec_secrets_scan ->
  (optional) fresh_db_drill (bootstrap_min) ->
  (optional) backup ->
  (optional) tag rollback image ->
  (optional) build ->
  (optional) migrate ->
  (optional) verify (suites) ->
  (optional) deploy ->
  (optional) wait_api ->
  (optional) worker_tasks_smoke ->
  (optional) smoke ->
  evidence -> LKG (+ rollback story)

Evidence:
  ops/_local/evidence/release_m0_<release_id>/...

LKG:
  ops/_local/lkg/last_known_good.json

Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$BaseUrl = $(if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8080" }),
  [string]$HealthPath = $(if ($env:FF_HEALTH_PATH) { $env:FF_HEALTH_PATH } else { "/health" }),

  [string]$ComposeFile = "",
  [string]$ProjectName = $(if ($env:FF_COMPOSE_PROJECT) { $env:FF_COMPOSE_PROJECT } elseif ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "" }),

  [string]$ReleaseId = "",

  [string]$BackupDir = "",

  [string]$ApiContainer = "",
  [string]$WorkerContainer = "",

  [string]$ArchitectKey = $(if ($env:FF_ARCHITECT_KEY) { $env:FF_ARCHITECT_KEY } else { "" }),

  [ValidateSet("", "skip", "sql_dirs", "bootstrap_all_min", "custom")]
  [string]$MigrateMode = "",

  [string]$MigrateScript = "",

  # legacy/compat flags used in older invocations
  [string]$SqlMigrationsDir = "",
  [string]$SqlFixpacksAutoDir = "",
  [switch]$ApplyGateFixpacks,

  # DB verify suites
  [switch]$VerifyDbContract,
  [switch]$VerifyDbContractPlus,

  # Fresh DB drill (bootstrap_min + suite) via C-sql worktree + local ff-fresh-db-drill.ps1
  [switch]$SkipFreshDbDrill,
  [switch]$KeepFreshDbDrillDb,
  [string]$FreshDbSqlWorktree = "",

  # Worker critical tasks smoke (celery inspect ping + registered tasks + optional log scan)
  [switch]$SkipWorkerTasksSmoke,
  [string]$WorkerRequiredTasksCsv = "",
  [int]$WorkerLogsSinceMin = 30,
  [switch]$SkipWorkerUnregisteredLogCheck,
  [int]$WorkerSmokeRetries = 10,
  [int]$WorkerSmokeSleepSec = 2,
  [int]$WorkerPingTimeoutSec = 10,
  [int]$WorkerInspectTimeoutSec = 20,

  # FlowSec secrets scan (optional if script exists)
  [switch]$SkipFlowSecSecretsScan,
  [string]$FlowSecMode = "all",
  [switch]$FlowSecAdvisory,
  [switch]$FlowSecAllowSoftFindings,
  [string]$FlowSecAllowlistPath = "scripts/pwsh/sec/ff-sec-allowlist.txt",
  [int]$FlowSecMaxFileBytes = 2000000,

  [switch]$NoBackup,
  [switch]$NoBuild,
  [switch]$NoDeploy,
  [switch]$NoSmoke,
  [switch]$NoRollback,

  [int]$WaitApiTimeoutSec = 120,
  [int]$WaitApiPollSec = 2
)

# NOTE: DO NOT place any executable statements before [CmdletBinding]/param.
$VERSION = "2025-12-26.det.v18"

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# Silence docker compose warnings about missing pgAdmin env vars (local-only; no compose/env changes)
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_EMAIL))    { $env:PGADMIN_EMAIL    = "disabled@local" }
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_PASSWORD)) { $env:PGADMIN_PASSWORD = "disabled" }

function Now-Stamp { (Get-Date).ToString("yyyyMMdd_HHmmss") }
function Now-Iso   { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function Repo-Root { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }

function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function Set-Utf8([string]$Path, [string]$Text) { $d=Split-Path $Path -Parent; if($d){Ensure-Dir $d}; ($Text ?? "") | Set-Content -LiteralPath $Path -Encoding utf8NoBOM }
function Add-Utf8([string]$Path, [string]$Text) { $d=Split-Path $Path -Parent; if($d){Ensure-Dir $d}; ($Text ?? "") | Add-Content -LiteralPath $Path -Encoding utf8NoBOM }

function Write-Step([string]$msg) { Write-Host ("`n==> " + $msg) -ForegroundColor Cyan }
function Write-Warn([string]$msg) { Write-Host ("WARN: " + $msg) -ForegroundColor Yellow }
function Write-Ok([string]$msg)   { Write-Host ("OK: " + $msg) -ForegroundColor Green }
function Write-Fail([string]$msg) { Write-Host ("FAIL: " + $msg) -ForegroundColor Red }

function Normalize-BaseUrl([string]$u) {
  if ([string]::IsNullOrWhiteSpace($u)) { return "http://127.0.0.1:8080" }
  if ($u -match "localhost") { $u = ($u -replace "localhost","127.0.0.1") }
  $u = $u.Trim()
  while ($u.EndsWith("/")) { $u = $u.Substring(0, $u.Length - 1) }
  return $u
}

function Normalize-HealthPath([string]$hp) {
  if ([string]::IsNullOrWhiteSpace($hp)) { $hp = "/health" }
  $hp = $hp.Trim()
  if (-not $hp.StartsWith("/")) { $hp = "/" + $hp }
  return $hp
}

function Normalize-ReleaseId([string]$rid) {
  if ([string]::IsNullOrWhiteSpace($rid)) { return $rid }
  $rid = $rid.Trim()
  $rid = ($rid -replace '[^A-Za-z0-9_.-]', '_').Trim('_')
  if ([string]::IsNullOrWhiteSpace($rid)) { throw "ReleaseId sanitized to empty. Provide a valid ReleaseId." }
  return $rid
}

function Resolve-ComposeFile([string]$repoRoot, [string]$composeFile) {
  if ([string]::IsNullOrWhiteSpace($composeFile)) { $composeFile = Join-Path $repoRoot "docker-compose.yml" }
  if (-not (Test-Path -LiteralPath $composeFile)) { throw "ComposeFile not found: $composeFile" }
  return (Resolve-Path -LiteralPath $composeFile).Path
}

function Resolve-SiblingWorktree([string]$repoRoot, [string]$siblingName) {
  $parent = Split-Path $repoRoot -Parent
  if ([string]::IsNullOrWhiteSpace($parent)) { return $null }
  $cand = Join-Path $parent $siblingName
  if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }
  return $null
}

function Sanitize-DbName([string]$name) {
  if ([string]::IsNullOrWhiteSpace($name)) { return $name }
  $n = ($name.Trim().ToLowerInvariant() -replace '[^a-z0-9_]', '_')
  if ($n.Length -gt 60) { $n = $n.Substring(0,60) }
  return $n
}

function Dc([string]$composeFile, [string]$projectName, [string[]]$composeArgs) {
  $argv = New-Object System.Collections.Generic.List[string]
  $argv.Add("compose") | Out-Null
  $argv.Add("--ansi")  | Out-Null
  $argv.Add("never")   | Out-Null
  $argv.Add("-f")      | Out-Null
  $argv.Add($composeFile) | Out-Null
  if ($projectName) { $argv.Add("-p") | Out-Null; $argv.Add($projectName) | Out-Null }
  foreach ($a in $composeArgs) { $argv.Add($a) | Out-Null }

  $out = & docker @($argv.ToArray()) 2>&1
  $code = $LASTEXITCODE
  return [pscustomobject]@{
    code = $code
    out  = ($out | Out-String)
    argv = ("docker " + ($argv.ToArray() -join " "))
  }
}

function Extract-ServiceNames([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return @() }
  $names = New-Object System.Collections.Generic.List[string]
  foreach ($line in ($text -split '\r?\n')) {
    $t = ($line ?? "").Trim()
    if (-not $t) { continue }
    if ($t -match '^[A-Za-z0-9][A-Za-z0-9_-]*$') { $names.Add($t) | Out-Null }
  }
  return @($names.ToArray() | Sort-Object -Unique)
}

function Extract-EnvFilesFromCompose([string]$composeFile) {
  $dir = Split-Path $composeFile -Parent
  $lines = Get-Content -LiteralPath $composeFile -Encoding UTF8
  $out = New-Object System.Collections.Generic.List[string]

  for ($i=0; $i -lt $lines.Count; $i++) {
    $ln = $lines[$i]

    # inline: env_file: .env.docker   OR env_file: [.env.docker, .env.other]
    $mInline = [regex]::Match($ln, '^\s*env_file\s*:\s*(.+?)\s*$')
    if ($mInline.Success -and ($ln -notmatch '^\s*env_file\s*:\s*$')) {
      $val = $mInline.Groups[1].Value.Trim()
      $val = ($val -replace '\s+#.*$','').Trim()
      if ($val.StartsWith('[') -and $val.EndsWith(']')) {
        $inside = $val.Substring(1, $val.Length-2)
        foreach ($part in ($inside -split ',')) {
          $p = ($part ?? "").Trim()
          if (-not $p) { continue }
          if (($p.StartsWith('"') -and $p.EndsWith('"')) -or ($p.StartsWith("'") -and $p.EndsWith("'"))) {
            $p = $p.Substring(1, $p.Length-2)
          }
          if (-not $p) { continue }
          $out.Add($p) | Out-Null
        }
      } else {
        if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
          $val = $val.Substring(1, $val.Length-2)
        }
        if ($val) { $out.Add($val) | Out-Null }
      }
      continue
    }

    # multiline:
    # env_file:
    #   - .env.docker
    $mStart = [regex]::Match($ln, '^(\s*)env_file\s*:\s*$')
    if ($mStart.Success) {
      $baseIndent = $mStart.Groups[1].Value.Length
      for ($j=$i+1; $j -lt $lines.Count; $j++) {
        $ln2 = $lines[$j]
        if ([string]::IsNullOrWhiteSpace($ln2)) { continue }
        if ($ln2 -match '^\s*#') { continue }

        $indent2 = ([regex]::Match($ln2, '^\s*').Value.Length)
        if ($indent2 -le $baseIndent) { break }

        $mItem = [regex]::Match($ln2, '^\s*-\s*(.+?)\s*$')
        if ($mItem.Success) {
          $p = $mItem.Groups[1].Value.Trim()
          $p = ($p -replace '\s+#.*$','').Trim()
          if (($p.StartsWith('"') -and $p.EndsWith('"')) -or ($p.StartsWith("'") -and $p.EndsWith("'"))) {
            $p = $p.Substring(1, $p.Length-2)
          }
          if ($p) { $out.Add($p) | Out-Null }
        }
      }
    }
  }

  $uniq = @($out.ToArray() | Where-Object { $_ } | Sort-Object -Unique)
  $abs = @()
  foreach ($p in $uniq) {
    $pp = $p
    if (-not [System.IO.Path]::IsPathRooted($pp)) { $pp = Join-Path $dir $pp }
    $abs += (Resolve-Path -LiteralPath $pp -ErrorAction SilentlyContinue)?.Path ?? $pp
  }
  return @($abs | Sort-Object -Unique)
}

function Http-Get([string]$url, [int]$timeoutSec = 12) {
  try {
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
      $httpCodeStr = & curl.exe -4 --http1.1 --noproxy 127.0.0.1 -sS -m $timeoutSec -w "%{http_code}" -o $tmp $url 2>&1
      $body = Get-Content -Raw -ErrorAction SilentlyContinue $tmp
      $m = [regex]::Match($httpCodeStr, "(\d{3})\s*$")
      $code = if ($m.Success) { [int]$m.Groups[1].Value } else { 0 }
      return [pscustomobject]@{ code=$code; body=$body; raw=($httpCodeStr|Out-String) }
    } finally {
      Remove-Item -Force -ErrorAction SilentlyContinue $tmp
    }
  } catch {
    $resp = Invoke-WebRequest -Uri $url -TimeoutSec $timeoutSec -SkipHttpErrorCheck
    return [pscustomobject]@{ code=[int]$resp.StatusCode; body=[string]$resp.Content; raw="" }
  }
}

function Wait-ApiReady([string]$baseUrl, [string]$healthPath, [int]$timeoutSec, [int]$pollSec, [string]$evidenceDir) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  $hp = Normalize-HealthPath $healthPath
  $u = ($baseUrl.TrimEnd("/") + $hp)

  $logPath = Join-Path $evidenceDir "wait_api_health_extended.log"
  $metaPath = Join-Path $evidenceDir "wait_api_target.txt"
  Set-Utf8 $metaPath ("ts={0}`nurl={1}`nhealth_path={2}`n" -f (Now-Iso), $u, $hp)

  $nfStreak = 0
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Http-Get -url $u -timeoutSec 10
      Add-Utf8 $logPath ("[{0}] code={1}" -f (Now-Iso), $r.code)

      if ($r.code -eq 404) {
        $nfStreak++
        if ($nfStreak -ge 3) {
          try { Set-Utf8 (Join-Path $evidenceDir "wait_api_last_body.txt") ($r.body ?? "") } catch {}
          throw "Health endpoint not found (404): $u"
        }
      } else {
        $nfStreak = 0
      }

      if ($r.code -ge 200 -and $r.code -lt 300) {
        try {
          $j = $r.body | ConvertFrom-Json -Depth 64
          $props = @($j.PSObject.Properties.Name)

          if ($props -contains "ready") {
            if ($j.ready -eq $true) { Set-Utf8 (Join-Path $evidenceDir "health_extended.json") ($r.body ?? ""); return $true }
          }
          elseif ($props -contains "ok") {
            if ($j.ok -eq $true) { Set-Utf8 (Join-Path $evidenceDir "health_extended.json") ($r.body ?? ""); return $true }
          }
          elseif ($props -contains "status") {
            $s = ($j.status ?? "").ToString().ToLowerInvariant()
            if ($s -in @("ok","healthy","up")) { Set-Utf8 (Join-Path $evidenceDir "health_extended.json") ($r.body ?? ""); return $true }
          }

          # Unknown schema but 2xx => ready enough for RUN gate
          Set-Utf8 (Join-Path $evidenceDir "health_extended.json") ($r.body ?? "")
          return $true
        } catch {
          Set-Utf8 (Join-Path $evidenceDir "health_extended.json") ($r.body ?? "")
          return $true
        }
      }
    } catch {
      Add-Utf8 $logPath ("[{0}] error={1}" -f (Now-Iso), $_.Exception.Message)
    }

    Start-Sleep -Seconds $pollSec
  }

  throw "API not ready within ${timeoutSec}s: $u"
}

function Try-GetGitInfo([string]$root) {
  $info = [ordered]@{ sha=$null; branch=$null; dirty=$null }
  try {
    Push-Location $root
    $info.sha = (git rev-parse HEAD 2>$null).Trim()
    $info.branch = (git rev-parse --abbrev-ref HEAD 2>$null).Trim()
    $st = (git status --porcelain 2>$null)
    $info.dirty = ([string]::IsNullOrWhiteSpace($st) -eq $false)
  } catch { } finally { try { Pop-Location } catch {} }
  return $info
}

function Write-RollbackStory([string]$path, [hashtable]$ctx) {
  $t = @()
  $t += "# FoxProFlow • Rollback Story (M0)"
  $t += ""
  $t += ("ts: {0}" -f (Now-Iso))
  $t += ("release_id: {0}" -f $ctx.release_id)
  $t += ("pre_git_sha: {0}" -f $ctx.pre_sha)
  $t += ("base_url: {0}" -f $ctx.base_url)
  $t += ("health_path: {0}" -f ($ctx.health_path ?? "/health"))
  if ($ctx.compose_file) { $t += ("compose_file: {0}" -f $ctx.compose_file) }
  if ($ctx.project_name) { $t += ("project_name: {0}" -f $ctx.project_name) }
  if ($ctx.backup_dir) { $t += ("backup_dir: {0}" -f $ctx.backup_dir) }
  if ($ctx.rollback_image_tag) { $t += ("rollback_image_tag: {0}" -f $ctx.rollback_image_tag) }
  $t += ""

  $t += "## Быстрый откат"
  $t += ("1) cd `"{0}`"" -f $ctx.repo_root)
  $t += ("2) git reset --hard {0}" -f $ctx.pre_sha)

  $dc = "docker compose"
  if ($ctx.compose_file) { $dc += " -f `"$($ctx.compose_file)`"" }
  if ($ctx.project_name) { $dc += " -p $($ctx.project_name)" }
  $t += ("3) {0} up -d --build api worker beat" -f $dc)

  $hp = ($ctx.health_path ?? "/health")
  if (-not $hp.StartsWith("/")) { $hp = "/" + $hp }
  $t += ("4) curl.exe -4 --http1.1 --noproxy 127.0.0.1 `"{0}{1}`"" -f $ctx.base_url, $hp)
  $t += ""
  Set-Utf8 $path ($t -join "`n")
}

function Update-Lkg([string]$path, [object]$obj) {
  $dir = Split-Path $path -Parent
  Ensure-Dir $dir
  ($obj | ConvertTo-Json -Depth 80) | Set-Content -LiteralPath $path -Encoding utf8NoBOM
}

function Resolve-SqlDirs-Auto([string]$repoRoot) {
  $cSqlRoot = Resolve-SiblingWorktree -repoRoot $repoRoot -siblingName "C-sql"

  $aMig = Join-Path $repoRoot "scripts\sql\migrations"
  $cMig = if ($cSqlRoot) { Join-Path $cSqlRoot "scripts\sql\migrations" } else { "" }

  $aFixAuto = Join-Path $repoRoot "scripts\sql\fixpacks\auto"
  $cFixAuto = if ($cSqlRoot) { Join-Path $cSqlRoot "scripts\sql\fixpacks\auto" } else { "" }

  $aFixRoot = Join-Path $repoRoot "scripts\sql\fixpacks"
  $cFixRoot = if ($cSqlRoot) { Join-Path $cSqlRoot "scripts\sql\fixpacks" } else { "" }

  $migDir = (Test-Path -LiteralPath $aMig) ? $aMig : $cMig
  $fxAuto = (Test-Path -LiteralPath $aFixAuto) ? $aFixAuto : $cFixAuto
  $fxRoot = (Test-Path -LiteralPath $aFixRoot) ? $aFixRoot : $cFixRoot

  return [pscustomobject]@{ c_sql_root=$cSqlRoot; mig_dir=$migDir; fix_auto_dir=$fxAuto; fix_root_dir=$fxRoot }
}

function Resolve-VerifySuiteFile([string]$repoRoot, [string]$suiteName) {
  $cSqlRoot = Resolve-SiblingWorktree -repoRoot $repoRoot -siblingName "C-sql"
  if ($cSqlRoot) {
    $p = Join-Path $cSqlRoot ("scripts\sql\verify\suites\{0}.txt" -f $suiteName)
    if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
  }
  $p2 = Join-Path $repoRoot ("scripts\sql\verify\suites\{0}.txt" -f $suiteName)
  if (Test-Path -LiteralPath $p2) { return (Resolve-Path -LiteralPath $p2).Path }
  throw "Verify suite not found: $suiteName"
}

function Resolve-BackupScript([string]$scriptsDir) {
  $primary = Join-Path $scriptsDir "ff-backup.ps1"
  if (Test-Path -LiteralPath $primary) { return (Resolve-Path -LiteralPath $primary).Path }

  $alts = @()
  try {
    $alts = Get-ChildItem -LiteralPath $scriptsDir -File -Filter "ff-backup*.ps1" -ErrorAction SilentlyContinue | Sort-Object Name
  } catch { $alts = @() }

  if ($alts -and $alts.Count -gt 0) { return $alts[0].FullName }
  return $primary
}

function Get-PwshExe() {
  try {
    if ($IsWindows) {
      $cand = Join-Path $PSHOME "pwsh.exe"
      if (Test-Path -LiteralPath $cand) { return $cand }
    }
  } catch { }
  return "pwsh"
}

# Important: never collide with automatic variable $args (case-insensitive)
function Run-PwshScript(
  [string]$ScriptPath,
  [Alias("Args")]
  [string[]]$ScriptArgs = @(),
  [string]$LogPath = "",
  [switch]$AppendLog
) {
  if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Script not found: $ScriptPath" }
  $pwshExe = Get-PwshExe

  $safe = @()
  if ($null -ne $ScriptArgs) { $safe = [string[]]$ScriptArgs }

  $argv = @("-NoProfile","-ExecutionPolicy","Bypass","-File",$ScriptPath) + $safe
  $out = & $pwshExe @argv 2>&1
  $code = $LASTEXITCODE

  if ($LogPath) {
    $text = ("argv={0}`n`n{1}`nexit_code={2}`n" -f ("$pwshExe " + ($argv -join " ")), ($out | Out-String), $code)
    if ($AppendLog) { Add-Utf8 $LogPath $text } else { Set-Utf8 $LogPath $text }
  }

  return [pscustomobject]@{ code=$code; out=($out|Out-String) }
}

# --- psql include expansion (\i/\ir) for SQL apply ---
function Try-ParsePsqlInclude([string]$line) {
  $m = [regex]::Match($line, '^\s*\\i(r)?\s+(.+?)\s*$')
  if (-not $m.Success) { return $null }

  $p = $m.Groups[2].Value.Trim()
  $p = ($p -replace '\s+--.*$', '').Trim()
  if (($p.StartsWith('"') -and $p.EndsWith('"')) -or ($p.StartsWith("'") -and $p.EndsWith("'"))) {
    if ($p.Length -ge 2) { $p = $p.Substring(1, $p.Length - 2) }
  }
  if ([string]::IsNullOrWhiteSpace($p)) { return $null }
  return $p
}

function Expand-PsqlIncludes([string]$sqlFile, [hashtable]$seen = $null) {
  if (-not $seen) { $seen = @{} }
  if (-not (Test-Path -LiteralPath $sqlFile)) { throw "SQL file not found: $sqlFile" }

  $full = (Resolve-Path -LiteralPath $sqlFile).Path
  if ($seen.ContainsKey($full)) { return ("-- SKIP RECURSIVE INCLUDE: {0}`n" -f $full) }
  $seen[$full] = $true

  $baseDir = Split-Path $full -Parent
  $sb = New-Object System.Text.StringBuilder
  $lines = Get-Content -LiteralPath $full -Encoding UTF8

  foreach ($line in $lines) {
    $incRel = Try-ParsePsqlInclude $line
    if ($incRel) {
      $incPath = $incRel
      if (-not [System.IO.Path]::IsPathRooted($incPath)) { $incPath = Join-Path $baseDir $incPath }
      if (-not (Test-Path -LiteralPath $incPath)) {
        throw ("psql include not found: {0} (resolved: {1}) referenced from {2}" -f $incRel, $incPath, $full)
      }

      $incFull = (Resolve-Path -LiteralPath $incPath).Path
      [void]$sb.AppendLine(("-- BEGIN INCLUDE: {0} => {1}" -f $incRel, $incFull))
      [void]$sb.Append((Expand-PsqlIncludes -sqlFile $incFull -seen $seen))
      [void]$sb.AppendLine(("-- END INCLUDE: {0}" -f $incRel))
      continue
    }
    [void]$sb.AppendLine($line)
  }

  return $sb.ToString()
}

function Invoke-PsqlSqlFile(
  [string]$composeFile,
  [string]$projectName,
  [string]$sqlFile,
  [string]$logPath,
  [string]$dbName = "foxproflow"
) {
  if (-not (Test-Path -LiteralPath $sqlFile)) { throw "SQL file not found: $sqlFile" }

  $raw = Get-Content -Raw -Encoding UTF8 $sqlFile
  $needsExpand = ($raw -match '(?m)^\s*\\i(r)?\s+')
  $sql = if ($needsExpand) { Expand-PsqlIncludes -sqlFile $sqlFile -seen @{} } else { $raw }

  $dcArgv = @(
    "compose","--ansi","never","-f",$composeFile,"-p",$projectName,
    "exec","-T","postgres",
    "psql","-U","admin","-d",$dbName,"-X","-v","ON_ERROR_STOP=1","-f","-"
  )

  $out = $sql | & docker @dcArgv 2>&1
  $code = $LASTEXITCODE

  if ($logPath) {
    $logDir = Split-Path $logPath -Parent
    if ($needsExpand -and $logDir) {
      $expandedName = "expanded_" + [System.IO.Path]::GetFileName($sqlFile)
      Set-Utf8 (Join-Path $logDir $expandedName) $sql
    }
    Set-Utf8 $logPath ("=== APPLY/VERIFY SQL via STDIN ===`nfile={0}`nts={1}`ndb={2}`nargv=docker {3}`n`n{4}`nexit_code={5}`n" -f `
      $sqlFile, (Now-Iso), $dbName, ($dcArgv -join " "), ($out | Out-String), $code)
  }

  return [pscustomobject]@{ code=$code; out=($out|Out-String) }
}

function BestEffort-TagRollbackImage([string]$composeFile, [string]$projectName, [string]$evidenceDir, [string]$releaseId) {
  $log = Join-Path $evidenceDir "rollback_image_tag.log"
  try {
    $q = Dc -composeFile $composeFile -projectName $projectName -composeArgs @("ps","-q","api")
    Add-Utf8 $log ("argv={0}`n{1}`nexit_code={2}`n" -f $q.argv, $q.out, $q.code)

    $cid = ($q.out.Trim() -split '\r?\n' | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($cid)) {
      $src = "foxproflow/app:latest"
      $dst = ("foxproflow/app:rollback_{0}" -f $releaseId)
      $out = & docker image tag $src $dst 2>&1
      $code = $LASTEXITCODE
      Add-Utf8 $log ("fallback tag: {0} -> {1}`n{2}`nexit_code={3}`n" -f $src, $dst, ($out | Out-String), $code)
      if ($code -ne 0) { return $null }
      return $dst
    }

    $imgId = (& docker inspect -f "{{.Image}}" $cid 2>&1 | Out-String).Trim()
    Add-Utf8 $log ("container={0}`nimage_id={1}`n" -f $cid, $imgId)
    if ([string]::IsNullOrWhiteSpace($imgId)) { return $null }

    $dstTag = ("foxproflow/app:rollback_{0}" -f $releaseId)
    $out2 = & docker image tag $imgId $dstTag 2>&1
    $code2 = $LASTEXITCODE
    Add-Utf8 $log ("tag image_id -> {0}`n{1}`nexit_code={2}`n" -f $dstTag, ($out2 | Out-String), $code2)
    if ($code2 -ne 0) { return $null }

    return $dstTag
  } catch {
    Add-Utf8 $log ("ERROR: {0}`n" -f $_.Exception.Message)
    return $null
  }
}

function Get-ScriptParamNames([string]$scriptPath) {
  try {
    $tok = $null; $err = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tok, [ref]$err)
    if ($err -and $err.Count -gt 0) { return @() }
    $pb = $ast.ParamBlock
    if (-not $pb) { return @() }
    $names = @()
    foreach ($p in $pb.Parameters) { $names += $p.Name.VariablePath.UserPath }
    return $names
  } catch { return @() }
}

function Try-ExtractJsonText([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return $null }
  $t = $text.Trim()
  $m = [regex]::Match($t, '(?s)(\{.*\}|\[.*\])')
  if ($m.Success) { return $m.Groups[1].Value }
  return $null
}

function Invoke-SmokeM0([string]$baseUrl, [string]$evidenceDir) {
  $smoke = Join-Path $PSScriptRoot "ff-smoke-m0.ps1"
  if (-not (Test-Path -LiteralPath $smoke)) { throw "ff-smoke-m0.ps1 not found: $smoke" }

  $env:API_BASE = $baseUrl
  if ($ArchitectKey) { $env:FF_ARCHITECT_KEY = $ArchitectKey }

  $params = Get-ScriptParamNames $smoke
  Set-Utf8 (Join-Path $evidenceDir "smoke_m0_params_detected.json") (($params | ConvertTo-Json -Depth 10))

  $reportJson = Join-Path $evidenceDir "smoke_m0.json"
  $log = Join-Path $evidenceDir "smoke_m0.log"

  $argsLocal = @()

  if ($params -contains "BaseUrl") { $argsLocal += @("-BaseUrl", $baseUrl) }
  elseif ($params -contains "ApiBase") { $argsLocal += @("-ApiBase", $baseUrl) }
  elseif ($params -contains "ApiUrl") { $argsLocal += @("-ApiUrl", $baseUrl) }

  if ($params -contains "KpiMode") { $argsLocal += @("-KpiMode", "strict") }
  elseif ($params -contains "Mode") { $argsLocal += @("-Mode", "strict") }

  if ($params -contains "ReportPath") { $argsLocal += @("-ReportPath", $reportJson) }
  elseif ($params -contains "ReportFile") { $argsLocal += @("-ReportFile", $reportJson) }
  elseif ($params -contains "OutFile") { $argsLocal += @("-OutFile", $reportJson) }
  elseif ($params -contains "OutputFile") { $argsLocal += @("-OutputFile", $reportJson) }
  elseif ($params -contains "EvidenceDir") { $argsLocal += @("-EvidenceDir", $evidenceDir) }
  elseif ($params -contains "OutDir") { $argsLocal += @("-OutDir", $evidenceDir) }

  if ($ArchitectKey) {
    if ($params -contains "ArchitectKey") { $argsLocal += @("-ArchitectKey", $ArchitectKey) }
    elseif ($params -contains "Key") { $argsLocal += @("-Key", $ArchitectKey) }
  }

  $r = Run-PwshScript -ScriptPath $smoke -Args ([string[]]$argsLocal) -LogPath $log
  if ($r.code -ne 0) { throw "smoke failed (exit=$($r.code))" }

  if (-not (Test-Path -LiteralPath $reportJson)) {
    try {
      $jt = Try-ExtractJsonText $r.out
      if ($jt) {
        $obj = $jt | ConvertFrom-Json -Depth 64
        ($obj | ConvertTo-Json -Depth 64) | Set-Content -LiteralPath $reportJson -Encoding utf8NoBOM
      }
    } catch { }
  }

  return $true
}

function Select-ExistingServices([string[]]$allServices, [string[]]$preferred) {
  if (-not $allServices -or $allServices.Count -eq 0) { return $preferred }
  $set = @{}
  foreach ($s in $allServices) { if ($s) { $set[$s.Trim()] = $true } }
  $out = New-Object System.Collections.Generic.List[string]
  foreach ($p in $preferred) {
    if ($set.ContainsKey($p)) { $out.Add($p) | Out-Null }
  }
  if ($out.Count -gt 0) { return $out.ToArray() }
  return $allServices
}

function Invoke-FlowSecSecretsScan(
  [string]$repoRoot,
  [string]$evidenceDir
) {
  $scan = Join-Path $PSScriptRoot "sec\ff-sec-scan-secrets.ps1"
  if (-not (Test-Path -LiteralPath $scan)) { return [pscustomobject]@{ skipped=$true; ok=$null; script=$scan; log=$null } }
  if ($SkipFlowSecSecretsScan) { return [pscustomobject]@{ skipped=$true; ok=$null; script=$scan; log=$null } }

  $log = Join-Path $evidenceDir "flowsec_secrets_scan.log"
  $p = Get-ScriptParamNames $scan
  Set-Utf8 (Join-Path $evidenceDir "flowsec_secrets_params_detected.json") (($p | ConvertTo-Json -Depth 10))

  $argsList = New-Object System.Collections.Generic.List[string]

  if ($p -contains "Mode") { $argsList.AddRange([string[]]@("-Mode",$FlowSecMode)) | Out-Null }
  if ($FlowSecAdvisory -and ($p -contains "Advisory")) { $argsList.Add("-Advisory") | Out-Null }
  if ($FlowSecAllowSoftFindings -and ($p -contains "AllowSoftFindings")) { $argsList.Add("-AllowSoftFindings") | Out-Null }

  if ($p -contains "AllowlistPath") { $argsList.AddRange([string[]]@("-AllowlistPath",$FlowSecAllowlistPath)) | Out-Null }
  elseif ($p -contains "Allowlist") { $argsList.AddRange([string[]]@("-Allowlist",$FlowSecAllowlistPath)) | Out-Null }

  if ($p -contains "MaxFileBytes") { $argsList.AddRange([string[]]@("-MaxFileBytes","$FlowSecMaxFileBytes")) | Out-Null }

  if ($p -contains "RepoRoot") { $argsList.AddRange([string[]]@("-RepoRoot",$repoRoot)) | Out-Null }
  elseif ($p -contains "Root") { $argsList.AddRange([string[]]@("-Root",$repoRoot)) | Out-Null }

  $r = Run-PwshScript -ScriptPath $scan -Args ([string[]]$argsList.ToArray()) -LogPath $log
  if ($r.code -ne 0) { throw "FlowSec secrets scan failed (exit=$($r.code)). See: $log" }

  return [pscustomobject]@{
    skipped=$false; ok=$true; script=$scan; log=$log;
    mode=$FlowSecMode; advisory=[bool]$FlowSecAdvisory; allow_soft_findings=[bool]$FlowSecAllowSoftFindings;
    allowlist_path=$FlowSecAllowlistPath; max_file_bytes=[int]$FlowSecMaxFileBytes
  }
}

function Invoke-FreshDbDrill(
  [string]$repoRoot,
  [string]$composeFile,
  [string]$projectName,
  [string]$evidenceDir,
  [string]$evSuffix,
  [string]$freshDbSqlWorktree
) {
  $drill = Join-Path $PSScriptRoot "ff-fresh-db-drill.ps1"
  if (-not (Test-Path -LiteralPath $drill)) { throw "Missing fresh-db drill script: $drill" }

  $sqlWt = $freshDbSqlWorktree
  if ([string]::IsNullOrWhiteSpace($sqlWt)) { $sqlWt = Resolve-SiblingWorktree -repoRoot $repoRoot -siblingName "C-sql" }
  if (-not $sqlWt) { throw "C-sql worktree not found near '$repoRoot'. Provide -FreshDbSqlWorktree explicitly." }

  $suiteAbs = Join-Path $sqlWt "scripts\sql\verify\suites\bootstrap_min.txt"
  if (-not (Test-Path -LiteralPath $suiteAbs)) { throw "bootstrap_min suite not found: $suiteAbs" }

  $fdDir = Join-Path $evidenceDir "fresh_db_drill_bootstrap_min"
  Ensure-Dir $fdDir

  $p = Get-ScriptParamNames $drill
  Set-Utf8 (Join-Path $fdDir "params_detected.json") (($p | ConvertTo-Json -Depth 10))

  $rid = ("m0_freshdb_" + $evSuffix)
  $argsList = New-Object System.Collections.Generic.List[string]

  if ($p -contains "ReleaseId") { $argsList.AddRange([string[]]@("-ReleaseId",$rid)) | Out-Null }
  if ($p -contains "ComposeFile") { $argsList.AddRange([string[]]@("-ComposeFile",$composeFile)) | Out-Null }
  if ($p -contains "ProjectName") { $argsList.AddRange([string[]]@("-ProjectName",$projectName)) | Out-Null }
  if ($p -contains "SuiteFile") { $argsList.AddRange([string[]]@("-SuiteFile",$suiteAbs)) | Out-Null }

  if ($KeepFreshDbDrillDb) {
    if ($p -contains "KeepTempDb") { $argsList.Add("-KeepTempDb") | Out-Null }
    elseif ($p -contains "KeepDb") { $argsList.Add("-KeepDb") | Out-Null }
  }

  if ($p -contains "EvidenceRoot") { $argsList.AddRange([string[]]@("-EvidenceRoot",$evidenceDir)) | Out-Null }
  elseif ($p -contains "EvidenceDir") { $argsList.AddRange([string[]]@("-EvidenceDir",$fdDir)) | Out-Null }
  elseif ($p -contains "OutDir") { $argsList.AddRange([string[]]@("-OutDir",$fdDir)) | Out-Null }

  Set-Utf8 (Join-Path $fdDir "drill_meta.json") (
    ([pscustomobject]@{
      ts = Now-Iso
      script = $drill
      sql_worktree = $sqlWt
      suite_abs = $suiteAbs
      keep_db = [bool]$KeepFreshDbDrillDb
      args = $argsList.ToArray()
    } | ConvertTo-Json -Depth 40)
  )

  $log = Join-Path $evidenceDir "fresh_db_drill.log"
  $r = Run-PwshScript -ScriptPath $drill -Args ([string[]]$argsList.ToArray()) -LogPath $log
  if ($r.code -ne 0) { throw "Fresh DB drill failed (exit=$($r.code)). See: $log" }

  return [pscustomobject]@{ ok=$true; script=$drill; evidence_dir=$fdDir; sql_worktree=$sqlWt }
}

function Invoke-WorkerTasksSmoke(
  [string]$composeFile,
  [string]$projectName,
  [string]$evidenceDir,
  [string]$evSuffix
) {
  $ws = Join-Path $PSScriptRoot "ff-worker-critical-tasks-smoke.ps1"
  if (-not (Test-Path -LiteralPath $ws)) { throw "Missing worker tasks smoke script: $ws" }

  $wsDir = Join-Path $evidenceDir "worker_tasks_smoke"
  Ensure-Dir $wsDir

  $p = Get-ScriptParamNames $ws
  Set-Utf8 (Join-Path $wsDir "params_detected.json") (($p | ConvertTo-Json -Depth 10))

  $argsList = New-Object System.Collections.Generic.List[string]
  if ($p -contains "ReleaseId") { $argsList.AddRange([string[]]@("-ReleaseId", ("worker_tasks_" + $evSuffix))) | Out-Null }
  if ($p -contains "ComposeFile") { $argsList.AddRange([string[]]@("-ComposeFile", $composeFile)) | Out-Null }
  if ($p -contains "ProjectName") { $argsList.AddRange([string[]]@("-ProjectName", $projectName)) | Out-Null }
  if ($p -contains "EvidenceDir") { $argsList.AddRange([string[]]@("-EvidenceDir", $wsDir)) | Out-Null }

  if (-not [string]::IsNullOrWhiteSpace($WorkerRequiredTasksCsv) -and ($p -contains "RequiredTasksCsv")) {
    $argsList.AddRange([string[]]@("-RequiredTasksCsv",$WorkerRequiredTasksCsv)) | Out-Null
  }

  if ($p -contains "Retries") { $argsList.AddRange([string[]]@("-Retries","$WorkerSmokeRetries")) | Out-Null }
  if ($p -contains "SleepSec") { $argsList.AddRange([string[]]@("-SleepSec","$WorkerSmokeSleepSec")) | Out-Null }
  if ($p -contains "PingTimeoutSec") { $argsList.AddRange([string[]]@("-PingTimeoutSec","$WorkerPingTimeoutSec")) | Out-Null }
  if ($p -contains "InspectTimeoutSec") { $argsList.AddRange([string[]]@("-InspectTimeoutSec","$WorkerInspectTimeoutSec")) | Out-Null }

  if (-not $SkipWorkerUnregisteredLogCheck -and ($p -contains "CheckUnregisteredInLogs")) {
    $argsList.Add("-CheckUnregisteredInLogs") | Out-Null
    if ($p -contains "LogsSinceMin") { $argsList.AddRange([string[]]@("-LogsSinceMin","$WorkerLogsSinceMin")) | Out-Null }
  } else {
    if ($p -contains "LogsSinceMin") { $argsList.AddRange([string[]]@("-LogsSinceMin","$WorkerLogsSinceMin")) | Out-Null }
  }

  Set-Utf8 (Join-Path $wsDir "worker_smoke_meta.json") (
    ([pscustomobject]@{
      ts = Now-Iso
      script = $ws
      evidence_dir = $wsDir
      args = $argsList.ToArray()
    } | ConvertTo-Json -Depth 40)
  )

  $log = Join-Path $wsDir "worker_smoke_runner.log"
  $r = Run-PwshScript -ScriptPath $ws -Args ([string[]]$argsList.ToArray()) -LogPath $log
  if ($r.code -ne 0) { throw "worker tasks smoke failed (exit=$($r.code)). See: $log" }

  return [pscustomobject]@{ ok=$true; script=$ws; evidence_dir=$wsDir }
}

# -----------------------------
# Main
# -----------------------------
$repoRoot = Repo-Root
$BaseUrl = Normalize-BaseUrl $BaseUrl
$HealthPath = Normalize-HealthPath $HealthPath
$ComposeFile = Resolve-ComposeFile -repoRoot $repoRoot -composeFile $ComposeFile

if ([string]::IsNullOrWhiteSpace($ProjectName)) {
  throw "ProjectName is empty. Provide -ProjectName or set FF_COMPOSE_PROJECT/COMPOSE_PROJECT_NAME."
}

if (-not $ReleaseId) { $ReleaseId = ("m0_{0}" -f (Now-Stamp)) }
$ReleaseId = Normalize-ReleaseId $ReleaseId

if ([string]::IsNullOrWhiteSpace($BackupDir)) { $BackupDir = Join-Path $repoRoot "ops\_backups" }
if ($ArchitectKey) { $env:FF_ARCHITECT_KEY = $ArchitectKey }
$env:API_BASE = $BaseUrl

# evidence naming
$evSuffix = $ReleaseId
if ($ReleaseId -like "m0_*") { $evSuffix = ($ReleaseId -replace '^m0_', '') }

$evName = $ReleaseId
if ($ReleaseId -notlike "release_m0_*") {
  $evName = ("release_m0_" + $evSuffix)
}

$evidenceDir = Join-Path $repoRoot ("ops\_local\evidence\{0}" -f $evName)
Ensure-Dir $evidenceDir
Write-Output ("evidence: " + $evidenceDir)

$started = Now-Iso
$swAll = [System.Diagnostics.Stopwatch]::StartNew()

$gitPre = Try-GetGitInfo $repoRoot
$preSha = $gitPre.sha

$lkgPath = Join-Path $repoRoot "ops\_local\lkg\last_known_good.json"

$exitCode = 0
$steps = New-Object System.Collections.Generic.List[object]

$rollbackPath = Join-Path $evidenceDir "rollback_story.md"
$backupOutDir = $null
$rollbackImageTag = $null
$failReason = ""
$ok = $true
$composeServices = @()

$flowsec = [ordered]@{ skipped=$true; ok=$null; script=$null; log=$null }
$freshDrill = [ordered]@{ skipped=$true; keep_db=[bool]$KeepFreshDbDrillDb; sql_worktree=$null; script=$null; evidence_dir=$null; ok=$null }
$workerSmoke = [ordered]@{
  skipped=$true; ok=$null; script=$null; evidence_dir=$null;
  required_tasks_csv=$WorkerRequiredTasksCsv; logs_since_min=[int]$WorkerLogsSinceMin; skip_unregistered_log_check=[bool]$SkipWorkerUnregisteredLogCheck
}

function Step([string]$name, [int]$failExitCode, [scriptblock]$fn) {
  $t0 = Now-Iso
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  try {
    & $fn
    $sw.Stop()
    $steps.Add([pscustomobject]@{ name=$name; ok=$true; started=$t0; ms=[int]$sw.ElapsedMilliseconds }) | Out-Null
  } catch {
    $sw.Stop()
    $steps.Add([pscustomobject]@{ name=$name; ok=$false; started=$t0; ms=[int]$sw.ElapsedMilliseconds; error=$_.Exception.Message }) | Out-Null
    $script:exitCode = $failExitCode
    throw
  }
}

Set-Utf8 (Join-Path $evidenceDir "release_meta.json") (
  ([pscustomobject]@{
    version = $VERSION
    gate = "M0"
    release_id = $ReleaseId
    evidence_name = $evName
    started = $started
    base_url = $BaseUrl
    health_path = $HealthPath
    compose_file = $ComposeFile
    project_name = $ProjectName
    migrate_mode_requested = $MigrateMode
    verify_gate_m0 = [bool]($VerifyDbContract -or $VerifyDbContractPlus)
    verify_gate_m0_plus = [bool]$VerifyDbContractPlus
    skip_fresh_db_drill = [bool]$SkipFreshDbDrill
    keep_fresh_db_drill_db = [bool]$KeepFreshDbDrillDb
    fresh_db_sql_worktree = $FreshDbSqlWorktree
    skip_worker_tasks_smoke = [bool]$SkipWorkerTasksSmoke
    worker_required_tasks_csv = $WorkerRequiredTasksCsv
    worker_logs_since_min = [int]$WorkerLogsSinceMin
    skip_worker_unregistered_log_check = [bool]$SkipWorkerUnregisteredLogCheck
    no_backup = [bool]$NoBackup
    no_build  = [bool]$NoBuild
    no_deploy = [bool]$NoDeploy
    no_smoke  = [bool]$NoSmoke
    no_rollback = [bool]$NoRollback
    skip_flowsec_secrets_scan = [bool]$SkipFlowSecSecretsScan
    git_pre = $gitPre
  } | ConvertTo-Json -Depth 80)
)

try {
  Write-Step "PRECHECK"
  Step "precheck" 2 {
    $ps = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("ps","-a")
    Set-Utf8 (Join-Path $evidenceDir "docker_compose_ps.txt") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $ps.argv, $ps.out, $ps.code)
    if ($ps.code -ne 0) { throw "docker compose ps failed (exit=$($ps.code))" }

    $sv = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("config","--services")
    Set-Utf8 (Join-Path $evidenceDir "docker_compose_services.txt") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $sv.argv, $sv.out, $sv.code)
    if ($sv.code -ne 0) { throw "docker compose config --services failed (exit=$($sv.code))" }

    $raw = @($sv.out -split '\r?\n' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    Set-Utf8 (Join-Path $evidenceDir "docker_compose_services_raw.txt") (($raw -join "`n") + "`n")

    $script:composeServices = Extract-ServiceNames $sv.out
    Set-Utf8 (Join-Path $evidenceDir "compose_services_extracted.txt") ((@($script:composeServices) -join "`n") + "`n")

    # env_file existence check (fail early, instead of deploy crash)
    $envFilesAbs = Extract-EnvFilesFromCompose -composeFile $ComposeFile
    Set-Utf8 (Join-Path $evidenceDir "compose_env_files.txt") ((@($envFilesAbs) -join "`n") + "`n")

    $missing = @()
    foreach ($f in @($envFilesAbs)) {
      if (-not (Test-Path -LiteralPath $f)) { $missing += $f }
    }
    if (@($missing).Count -gt 0) {
      throw ("Missing env_file(s) referenced by compose: `n" + (@($missing) -join "`n"))
    }
  }

  Write-Step "FLOWSEC: SECRETS SCAN"
  if ($SkipFlowSecSecretsScan) {
    Write-Warn "SkipFlowSecSecretsScan: skipping secrets scan"
    $flowsec.skipped = $true
    $steps.Add([pscustomobject]@{ name="flowsec_secrets_scan"; ok=$true; skipped=$true; ts=Now-Iso }) | Out-Null
  } else {
    Step "flowsec_secrets_scan" 12 {
      $res = Invoke-FlowSecSecretsScan -repoRoot $repoRoot -evidenceDir $evidenceDir
      $flowsec = [ordered]@{}
      foreach ($k in $res.PSObject.Properties.Name) { $flowsec[$k] = $res.$k }
      if ($res.skipped -eq $true) {
        Write-Warn "FlowSec secrets scan script not found or skipped"
      } else {
        Write-Ok "FlowSec secrets scan PASS"
      }
    }
  }

  Write-Step "WRITE rollback story (initial)"
  if (-not $NoRollback) {
    Write-RollbackStory -path $rollbackPath -ctx @{
      release_id = $ReleaseId
      pre_sha = $preSha
      base_url = $BaseUrl
      health_path = $HealthPath
      repo_root = $repoRoot
      compose_file = $ComposeFile
      project_name = $ProjectName
      backup_dir = $null
      rollback_image_tag = $null
    }
  } else {
    Write-Warn "NoRollback: skipping rollback story"
  }

  # FRESH DB DRILL (bootstrap_min)
  Write-Step "FRESH DB DRILL (bootstrap_min)"
  if ($SkipFreshDbDrill) {
    $freshDrill.skipped = $true
    $steps.Add([pscustomobject]@{ name="fresh_db_drill_bootstrap_min"; ok=$true; skipped=$true; ts=Now-Iso }) | Out-Null
    Write-Warn "SkipFreshDbDrill: skipping fresh DB drill"
  } else {
    Step "fresh_db_drill_bootstrap_min" 10 {
      $freshDrill.skipped = $false
      $res = Invoke-FreshDbDrill -repoRoot $repoRoot -composeFile $ComposeFile -projectName $ProjectName -evidenceDir $evidenceDir -evSuffix $evSuffix -freshDbSqlWorktree $FreshDbSqlWorktree
      $freshDrill.ok = $true
      $freshDrill.script = $res.script
      $freshDrill.evidence_dir = $res.evidence_dir
      $freshDrill.sql_worktree = $res.sql_worktree
      Write-Ok "Fresh DB drill PASS"
    }
  }

  Write-Step "BACKUP"
  if ($NoBackup) {
    Write-Warn "NoBackup: skipping backup"
    $steps.Add([pscustomobject]@{ name="backup"; ok=$true; skipped=$true; ts=Now-Iso }) | Out-Null
  } else {
    Step "backup" 9 {
      $backupScript = Resolve-BackupScript -scriptsDir $PSScriptRoot
      if (-not (Test-Path -LiteralPath $backupScript)) {
        throw "ff-backup script not found in: $PSScriptRoot (expected ff-backup.ps1 or ff-backup*.ps1). Pass -NoBackup to skip."
      }

      $log = Join-Path $evidenceDir "backup.log"
      $r = Run-PwshScript -ScriptPath $backupScript -Args ([string[]]@("-BackupDir",$BackupDir,"-ComposeFile",$ComposeFile,"-ProjectName",$ProjectName)) -LogPath $log
      if ($r.code -ne 0) { throw "backup failed (exit=$($r.code))" }

      try {
        $m = [regex]::Match($r.out, 'outDir:\s+([A-Za-z]:\\[^\r\n]+)')
        if ($m.Success) { $backupOutDir = $m.Groups[1].Value.Trim() }
      } catch { }
    }
  }

  Write-Step "TAG rollback image (best-effort)"
  if ($NoRollback) {
    Write-Warn "NoRollback: skipping rollback image tag"
  } else {
    $rollbackImageTag = BestEffort-TagRollbackImage -composeFile $ComposeFile -projectName $ProjectName -evidenceDir $evidenceDir -releaseId $ReleaseId
    if ($rollbackImageTag) {
      Write-Ok ("rollback_image_tag=" + $rollbackImageTag)
      Set-Utf8 (Join-Path $evidenceDir "rollback_image_tag.txt") $rollbackImageTag
    } else {
      Write-Warn "rollback image tag failed (non-fatal). See rollback_image_tag.log"
    }
  }

  Write-Step "BUILD"
  if ($NoBuild) {
    Write-Warn "NoBuild: skipping build"
    $steps.Add([pscustomobject]@{ name="build"; ok=$true; skipped=$true; ts=Now-Iso }) | Out-Null
  } else {
    Step "build" 8 {
      $buildLog = Join-Path $evidenceDir "build.log"

      $dockerArgv = New-Object System.Collections.Generic.List[string]
      $dockerArgv.AddRange([string[]]@("compose","--ansi","never","-f",$ComposeFile)) | Out-Null
      if ($ProjectName) { $dockerArgv.AddRange([string[]]@("-p",$ProjectName)) | Out-Null }
      $dockerArgv.AddRange([string[]]@("build","--progress","plain","api","worker","beat")) | Out-Null

      Set-Utf8 $buildLog ("ts={0}`nargv=docker {1}`n`n" -f (Now-Iso), ($dockerArgv.ToArray() -join " "))
      & docker @($dockerArgv.ToArray()) 2>&1 | Tee-Object -FilePath $buildLog -Append
      $code = $LASTEXITCODE
      Add-Utf8 $buildLog ("`nexit_code={0}`n" -f $code)
      if ($code -ne 0) { throw "build failed (exit=$code)" }
    }
  }

  if ($MigrateMode -eq "") {
    $defaultMig = Join-Path $PSScriptRoot "ff-db-bootstrap-all-min.ps1"
    $auto = Resolve-SqlDirs-Auto -repoRoot $repoRoot
    if (Test-Path -LiteralPath $defaultMig) { $MigrateMode = "bootstrap_all_min" }
    elseif ($auto.mig_dir -and (Test-Path -LiteralPath $auto.mig_dir)) { $MigrateMode = "sql_dirs" }
    else { $MigrateMode = "skip" }
  }

  Write-Step "MIGRATE"
  if ($MigrateMode -eq "skip") {
    Write-Warn "MigrateMode=skip: skipping migrate"
    $steps.Add([pscustomobject]@{ name="migrate"; ok=$true; skipped=$true; ts=Now-Iso }) | Out-Null
  }
  elseif ($MigrateMode -eq "bootstrap_all_min") {
    Step "migrate_bootstrap_all_min" 3 {
      $migRunner = if ($MigrateScript) { $MigrateScript } else { (Join-Path $PSScriptRoot "ff-db-bootstrap-all-min.ps1") }
      if (-not (Test-Path -LiteralPath $migRunner)) { throw "migrate runner not found: $migRunner" }

      $log = Join-Path $evidenceDir "migrate_bootstrap_all_min.log"
      $p = Get-ScriptParamNames $migRunner

      $argsList = New-Object System.Collections.Generic.List[string]
      if ($p -contains "ComposeFile") { $argsList.AddRange([string[]]@("-ComposeFile",$ComposeFile)) | Out-Null }
      if ($p -contains "ProjectName") { $argsList.AddRange([string[]]@("-ProjectName",$ProjectName)) | Out-Null }
      if ($p -contains "Apply") { $argsList.Add("-Apply") | Out-Null }

      Set-Utf8 $log ("== MIGRATE bootstrap_all_min ==`nrunner={0}`nts={1}`nargv={2}`n" -f $migRunner, (Now-Iso), ($argsList.ToArray() -join " "))
      $r = Run-PwshScript -ScriptPath $migRunner -Args ([string[]]$argsList.ToArray()) -LogPath $log -AppendLog
      if ($r.code -ne 0) { throw "migrate bootstrap_all_min failed (exit=$($r.code))" }
    }
  }
  elseif ($MigrateMode -eq "sql_dirs") {
    Step "migrate_sql_dirs" 3 {
      $auto = Resolve-SqlDirs-Auto -repoRoot $repoRoot

      $migDir = $SqlMigrationsDir
      if ([string]::IsNullOrWhiteSpace($migDir)) { $migDir = $auto.mig_dir }

      $fixAutoDir = $SqlFixpacksAutoDir
      if ([string]::IsNullOrWhiteSpace($fixAutoDir)) { $fixAutoDir = $auto.fix_auto_dir }

      $sources = [ordered]@{
        ts = Now-Iso
        migrate_mode = "sql_dirs"
        repo_root = $repoRoot
        compose_file = $ComposeFile
        project_name = $ProjectName
        migrations_dir = $migDir
        fixpacks_auto_dir = $fixAutoDir
        apply_gate_fixpacks = [bool]$ApplyGateFixpacks
      }

      $plan = New-Object System.Collections.Generic.List[string]

      if ($migDir -and (Test-Path -LiteralPath $migDir)) {
        $migs = Get-ChildItem -LiteralPath $migDir -File -Filter "*.sql" -ErrorAction SilentlyContinue | Sort-Object Name
        foreach ($f in $migs) { $plan.Add($f.FullName) | Out-Null }
      }

      if ($ApplyGateFixpacks -and $fixAutoDir -and (Test-Path -LiteralPath $fixAutoDir)) {
        $fx = Get-ChildItem -LiteralPath $fixAutoDir -File -Filter "*.sql" -ErrorAction SilentlyContinue | Sort-Object Name
        foreach ($f in $fx) { $plan.Add($f.FullName) | Out-Null }
      }

      $sources.migrations_files = @()
      if ($migDir -and (Test-Path -LiteralPath $migDir)) { $sources.migrations_files = @((Get-ChildItem -LiteralPath $migDir -File -Filter "*.sql" | Sort-Object Name).FullName) }

      $sources.fixpacks_files = @()
      if ($ApplyGateFixpacks -and $fixAutoDir -and (Test-Path -LiteralPath $fixAutoDir)) { $sources.fixpacks_files = @((Get-ChildItem -LiteralPath $fixAutoDir -File -Filter "*.sql" | Sort-Object Name).FullName) }

      Set-Utf8 (Join-Path $evidenceDir "migrate_sql_dirs_sources.json") (($sources | ConvertTo-Json -Depth 60))

      $planPath = Join-Path $evidenceDir "migrate_sql_dirs_plan.txt"
      Set-Utf8 $planPath ((@($plan.ToArray()) -join "`n") + "`n")

      if (-not $plan -or $plan.Count -eq 0) {
        Write-Warn "sql_dirs: no sql files found (plan empty) — nothing to apply"
        return
      }

      foreach ($f in $plan.ToArray()) {
        $name = [System.IO.Path]::GetFileName($f)
        $log = Join-Path $evidenceDir ("migrate_sql_{0}.log" -f $name)
        $r = Invoke-PsqlSqlFile -composeFile $ComposeFile -projectName $ProjectName -sqlFile $f -logPath $log -dbName "foxproflow"
        if ($r.code -ne 0) { throw "migrate sql_dirs failed on $name (exit=$($r.code))" }
      }
    }
  }
  elseif ($MigrateMode -eq "custom") {
    Step "migrate_custom" 3 {
      if (-not $MigrateScript) { throw "MigrateMode=custom requires -MigrateScript" }
      if (-not (Test-Path -LiteralPath $MigrateScript)) { throw "MigrateScript not found: $MigrateScript" }

      $log = Join-Path $evidenceDir "migrate_custom.log"
      $p = Get-ScriptParamNames $MigrateScript

      $argsList = New-Object System.Collections.Generic.List[string]
      if ($p -contains "ComposeFile") { $argsList.AddRange([string[]]@("-ComposeFile",$ComposeFile)) | Out-Null }
      if ($p -contains "ProjectName") { $argsList.AddRange([string[]]@("-ProjectName",$ProjectName)) | Out-Null }
      if ($p -contains "Apply") { $argsList.Add("-Apply") | Out-Null }

      $r = Run-PwshScript -ScriptPath $MigrateScript -Args ([string[]]$argsList.ToArray()) -LogPath $log
      if ($r.code -ne 0) { throw "migrate custom failed (exit=$($r.code))" }
    }
  }
  else {
    throw "Invalid MigrateMode: $MigrateMode"
  }

  if ($VerifyDbContract -or $VerifyDbContractPlus) {
    Write-Step "VERIFY DB CONTRACT (suites)"
    Step "verify_db_contract_suites" 4 {
      $runner = Join-Path $PSScriptRoot "ff-db-verify-suite.ps1"
      if (-not (Test-Path -LiteralPath $runner)) { throw "Missing suite runner: $runner" }

      $suiteList = New-Object System.Collections.Generic.List[string]
      if ($VerifyDbContract)     { $suiteList.Add("gate_m0")      | Out-Null }
      if ($VerifyDbContractPlus) { $suiteList.Add("gate_m0_plus") | Out-Null }

      Set-Utf8 (Join-Path $evidenceDir "verify_suites_plan.txt") (($suiteList.ToArray()) -join "`n")

      foreach ($suiteName in $suiteList.ToArray()) {
        $suiteFile = Resolve-VerifySuiteFile -repoRoot $repoRoot -suiteName $suiteName
        $log = Join-Path $evidenceDir ("verify_suite_{0}.log" -f $suiteName)

        $suiteArgs = [string[]]@(
          "-SuiteFile",$suiteFile,
          "-EvidenceDir",$evidenceDir,
          "-ComposeFile",$ComposeFile,
          "-ProjectName",$ProjectName
        )

        $r = Run-PwshScript -ScriptPath $runner -Args $suiteArgs -LogPath $log
        if ($r.code -ne 0) { throw "verify suite '$suiteName' failed (exit=$($r.code)). See: $log" }
      }
    }
  } else {
    Write-Warn "VerifyDbContract flags are not set: skipping verify suites"
    $steps.Add([pscustomobject]@{ name="verify_db_contract_suites"; ok=$true; skipped=$true; ts=Now-Iso }) | Out-Null
  }

  Write-Step "DEPLOY"
  if ($NoDeploy) {
    Write-Warn "NoDeploy: skipping deploy"
    $steps.Add([pscustomobject]@{ name="deploy"; ok=$true; skipped=$true; ts=Now-Iso }) | Out-Null
  } else {
    Step "deploy" 5 {
      $preferred = @("postgres","redis","osrm","api","worker","beat")
      $servicesToUp = Select-ExistingServices -allServices $composeServices -preferred $preferred

      $upArgs = @("up","-d","--remove-orphans")
      if ($NoBuild) { $upArgs += @("--no-build") }

      $d = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs ($upArgs + $servicesToUp)
      Set-Utf8 (Join-Path $evidenceDir "deploy.log") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $d.argv, $d.out, $d.code)
      if ($d.code -ne 0) { throw "deploy failed (exit=$($d.code))" }

      $ps2 = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("ps")
      Set-Utf8 (Join-Path $evidenceDir "docker_compose_ps_after_deploy.txt") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $ps2.argv, $ps2.out, $ps2.code)
    }
  }

  Write-Step "WAIT API READY"
  if ($WaitApiTimeoutSec -le 0) {
    Write-Warn "WaitApiTimeoutSec<=0: skipping wait_api"
    $steps.Add([pscustomobject]@{ name="wait_api"; ok=$true; skipped=$true; ts=Now-Iso }) | Out-Null
  } else {
    Step "wait_api" 6 {
      Wait-ApiReady -baseUrl $BaseUrl -healthPath $HealthPath -timeoutSec $WaitApiTimeoutSec -pollSec $WaitApiPollSec -evidenceDir $evidenceDir | Out-Null
    }
  }

  Write-Step "WORKER CRITICAL TASKS SMOKE"
  if ($NoSmoke -or $SkipWorkerTasksSmoke) {
    $workerSmoke.skipped = $true
    $steps.Add([pscustomobject]@{ name="worker_tasks_smoke"; ok=$true; skipped=$true; ts=Now-Iso }) | Out-Null
    if ($NoSmoke) { Write-Warn "NoSmoke: skipping worker tasks smoke" } else { Write-Warn "SkipWorkerTasksSmoke: skipping worker tasks smoke" }
  } else {
    Step "worker_tasks_smoke" 11 {
      $workerSmoke.skipped = $false
      $res = Invoke-WorkerTasksSmoke -composeFile $ComposeFile -projectName $ProjectName -evidenceDir $evidenceDir -evSuffix $evSuffix
      $workerSmoke.ok = $true
      $workerSmoke.script = $res.script
      $workerSmoke.evidence_dir = $res.evidence_dir
      Write-Ok "Worker tasks smoke PASS"
    }
  }

  Write-Step "SMOKE"
  if ($NoSmoke) {
    Write-Warn "NoSmoke: skipping smoke"
    $steps.Add([pscustomobject]@{ name="smoke"; ok=$true; skipped=$true; ts=Now-Iso }) | Out-Null
  } else {
    Step "smoke" 7 {
      Invoke-SmokeM0 -baseUrl $BaseUrl -evidenceDir $evidenceDir | Out-Null
    }
  }

  $ok = $true
  $failReason = ""

} catch {
  $ok = $false
  $failReason = $_.Exception.Message
  if (-not $exitCode -or $exitCode -eq 0) { $exitCode = 1 }

  try {
    Set-Utf8 (Join-Path $evidenceDir "release_error.txt") (
      "ts={0}`nexit_code={1}`nerror={2}`n`n{3}" -f (Now-Iso), $exitCode, $failReason, ($_.Exception.ToString())
    )
  } catch { }

} finally {
  $swAll.Stop()
  $ended = Now-Iso
  $gitPost = Try-GetGitInfo $repoRoot

  if (-not $NoRollback) {
    try {
      Write-RollbackStory -path $rollbackPath -ctx @{
        release_id = $ReleaseId
        pre_sha = $preSha
        base_url = $BaseUrl
        health_path = $HealthPath
        repo_root = $repoRoot
        compose_file = $ComposeFile
        project_name = $ProjectName
        backup_dir = $backupOutDir
        rollback_image_tag = $rollbackImageTag
      }
    } catch { }
  }

  $stepsArray = @()
  try { $stepsArray = @($steps.ToArray()) } catch { $stepsArray = @($steps) }

  try {
    $stepsJson = ($stepsArray | ConvertTo-Json -Depth 90)
    Set-Utf8 (Join-Path $evidenceDir "release_steps.json") $stepsJson
    Set-Utf8 (Join-Path $evidenceDir "steps.json") $stepsJson
  } catch { }

  $summary = [pscustomobject]@{
    version = $VERSION
    gate = "M0"
    release_id = $ReleaseId
    evidence_name = $evName
    evidence_dir = $evidenceDir
    started = $started
    ended = $ended
    ok = [bool]$ok
    exit_code = [int]$exitCode
    fail_reason = [string]$failReason

    base_url = $BaseUrl
    health_path = $HealthPath
    compose_file = $ComposeFile
    project_name = $ProjectName

    migrate_mode = $MigrateMode
    backup_dir = $backupOutDir
    rollback_image_tag = $rollbackImageTag

    flowsec_secrets_scan = [pscustomobject]$flowsec
    fresh_db_drill = [pscustomobject]$freshDrill
    worker_tasks_smoke = [pscustomobject]$workerSmoke

    verify = [pscustomobject]@{
      db_contract = [bool]($VerifyDbContract -or $VerifyDbContractPlus)
      db_contract_plus = [bool]$VerifyDbContractPlus
    }

    git_pre  = $gitPre
    git_post = $gitPost
    steps = $stepsArray
    compose_services = @($composeServices)
  }

  try {
    $summaryJson = ($summary | ConvertTo-Json -Depth 120)
    Set-Utf8 (Join-Path $evidenceDir "release_m0_summary.json") $summaryJson
    Set-Utf8 (Join-Path $evidenceDir "summary.json") $summaryJson
  } catch { }

  if ($ok -and $exitCode -eq 0) {
    try {
      $lkg = [pscustomobject]@{
        version = $VERSION
        ts = $ended
        gate = "M0"
        release_id = $ReleaseId
        evidence_dir = $evidenceDir
        base_url = $BaseUrl
        health_path = $HealthPath
        compose_file = $ComposeFile
        project_name = $ProjectName
        rollback_image_tag = $rollbackImageTag
        git = $gitPost
      }
      Update-Lkg -path $lkgPath -obj $lkg
      Set-Utf8 (Join-Path $evidenceDir "lkg_updated.txt") ("ok=true`npath={0}`n" -f $lkgPath)
    } catch {
      try { Set-Utf8 (Join-Path $evidenceDir "lkg_update_error.txt") $_.Exception.ToString() } catch {}
    }
  }
}

if ($ok -and $exitCode -eq 0) {
  Write-Ok "M0 OK"
  exit 0
} else {
  Write-Fail ("M0 FAILED (exit={0}): {1}" -f $exitCode, $failReason)
  exit $exitCode
}
