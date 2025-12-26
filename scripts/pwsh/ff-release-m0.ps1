#requires -Version 7.0
<#
FoxProFlow RUN • Release Gate M0/M0+
file: scripts/pwsh/ff-release-m0.ps1

Lane: A-RUN (compose/env/scripts/runbooks). No src/** edits, no scripts/sql/** edits.

Goal:
  precheck -> (optional) backup -> (optional) tag rollback image -> (optional) build ->
  (optional) migrate -> (optional) verify (suites) -> (optional) deploy -> (optional) wait_api ->
  (optional) smoke -> evidence -> LKG (+ rollback story)

Evidence:
  ops/_local/evidence/release_m0_<release_id>/...

LKG:
  ops/_local/lkg/last_known_good.json

Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$BaseUrl = $(if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8080" }),

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

  # Fresh DB drill (bootstrap_min + suite) via C-sql worktree
  [switch]$SkipFreshDbDrill,
  [switch]$KeepFreshDbDrillDb,
  [string]$FreshDbSqlWorktree = "",

  [switch]$NoBackup,
  [switch]$NoBuild,
  [switch]$NoDeploy,
  [switch]$NoSmoke,
  [switch]$NoRollback,

  [int]$WaitApiTimeoutSec = 120,
  [int]$WaitApiPollSec = 2
)

# NOTE: DO NOT place any executable statements before [CmdletBinding]/param.
$VERSION = "2025-12-26.det.v9"

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# Silence docker compose warnings about missing pgAdmin env vars (local-only; no compose/env changes)
# (Keep also here for direct invocation of ff-release-m0.ps1 without wrapper.)
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_EMAIL))    { $env:PGADMIN_EMAIL    = "disabled@local" }
if ([string]::IsNullOrWhiteSpace($env:PGADMIN_PASSWORD)) { $env:PGADMIN_PASSWORD = "disabled" }

function Now-Stamp { (Get-Date).ToString("yyyyMMdd_HHmmss") }
function Now-Iso   { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function Repo-Root { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }

function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function Set-Utf8([string]$Path, [string]$Text) { $d=Split-Path $Path -Parent; if($d){Ensure-Dir $d}; $Text | Set-Content -LiteralPath $Path -Encoding utf8NoBOM }
function Add-Utf8([string]$Path, [string]$Text) { $d=Split-Path $Path -Parent; if($d){Ensure-Dir $d}; $Text | Add-Content -LiteralPath $Path -Encoding utf8NoBOM }

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

function Normalize-ReleaseId([string]$rid) {
  if ([string]::IsNullOrWhiteSpace($rid)) { return $rid }
  $rid = $rid.Trim()
  # safe for dir + docker tag: [A-Za-z0-9_.-]
  $rid = ($rid -replace '[^A-Za-z0-9_.-]', '_').Trim('_')
  if ([string]::IsNullOrWhiteSpace($rid)) { throw "ReleaseId sanitized to empty. Provide a valid ReleaseId." }
  return $rid
}

function Resolve-ComposeFile([string]$repoRoot, [string]$composeFile) {
  if ([string]::IsNullOrWhiteSpace($composeFile)) { $composeFile = Join-Path $repoRoot "docker-compose.yml" }
  if (-not (Test-Path -LiteralPath $composeFile)) { throw "ComposeFile not found: $composeFile" }
  return (Resolve-Path -LiteralPath $composeFile).Path
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

function Wait-ApiReady([string]$baseUrl, [int]$timeoutSec, [int]$pollSec, [string]$evidenceDir) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  $u = ($baseUrl.TrimEnd("/") + "/health/extended")
  $logPath = Join-Path $evidenceDir "wait_api_health_extended.log"

  while ((Get-Date) -lt $deadline) {
    try {
      $r = Http-Get -url $u -timeoutSec 10
      Add-Utf8 $logPath ("[{0}] code={1}" -f (Now-Iso), $r.code)
      if ($r.code -ge 200 -and $r.code -lt 300) {
        try {
          $j = $r.body | ConvertFrom-Json -Depth 64
          if ($j.ready -eq $true) {
            Set-Utf8 (Join-Path $evidenceDir "health_extended.json") ($r.body ?? "")
            return $true
          }
        } catch { }
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

  $t += ("4) curl.exe -4 --http1.1 --noproxy 127.0.0.1 `"{0}/health/extended`"" -f $ctx.base_url)
  $t += ""
  Set-Utf8 $path ($t -join "`n")
}

function Update-Lkg([string]$path, [object]$obj) {
  $dir = Split-Path $path -Parent
  Ensure-Dir $dir
  ($obj | ConvertTo-Json -Depth 80) | Set-Content -LiteralPath $path -Encoding utf8NoBOM
}

function Resolve-SiblingWorktree([string]$repoRoot, [string]$siblingName) {
  $parent = Split-Path $repoRoot -Parent
  if ([string]::IsNullOrWhiteSpace($parent)) { return $null }
  $cand = Join-Path $parent $siblingName
  if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }
  return $null
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

function Run-PwshScript([string]$ScriptPath, [string[]]$Args, [string]$LogPath, [switch]$AppendLog) {
  if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Script not found: $ScriptPath" }
  $pwshExe = Get-PwshExe
  $argv = @("-NoProfile","-ExecutionPolicy","Bypass","-File",$ScriptPath) + ($Args ?? @())
  $out = & $pwshExe @argv 2>&1
  $code = $LASTEXITCODE

  if ($LogPath) {
    $text = ("argv={0}`n`n{1}`nexit_code={2}`n" -f ("$pwshExe " + ($argv -join " ")), ($out | Out-String), $code)
    if ($AppendLog) { Add-Utf8 $LogPath $text } else { Set-Utf8 $LogPath $text }
  }

  return [pscustomobject]@{ code=$code; out=($out|Out-String) }
}

function Invoke-PsqlSqlFile([string]$composeFile, [string]$projectName, [string]$sqlFile, [string]$logPath) {
  if (-not (Test-Path -LiteralPath $sqlFile)) { throw "SQL file not found: $sqlFile" }
  $sql = Get-Content -Raw -Encoding UTF8 $sqlFile

  $dcArgv = @(
    "compose","--ansi","never","-f",$composeFile,"-p",$projectName,
    "exec","-T","postgres",
    "psql","-U","admin","-d","foxproflow","-X","-v","ON_ERROR_STOP=1","-f","-"
  )

  $out = $sql | & docker @dcArgv 2>&1
  $code = $LASTEXITCODE

  if ($logPath) {
    Set-Utf8 $logPath ("=== APPLY/VERIFY SQL via STDIN ===`nfile={0}`nts={1}`nargv=docker {2}`n`n{3}`nexit_code={4}`n" -f `
      $sqlFile, (Now-Iso), ($dcArgv -join " "), ($out | Out-String), $code)
  }

  return [pscustomobject]@{ code=$code; out=($out|Out-String) }
}

function BestEffort-TagRollbackImage([string]$composeFile, [string]$projectName, [string]$evidenceDir, [string]$releaseId) {
  $log = Join-Path $evidenceDir "rollback_image_tag.log"
  try {
    $q = Dc -composeFile $composeFile -projectName $projectName -composeArgs @("ps","-q","api")
    Add-Utf8 $log ("argv={0}`n{1}`nexit_code={2}`n" -f $q.argv, $q.out, $q.code)

    $cid = ($q.out.Trim() -split "`r?`n" | Select-Object -First 1).Trim()
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
  } catch {
    return @()
  }
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

  $args = @()

  if ($params -contains "BaseUrl") { $args += @("-BaseUrl", $baseUrl) }
  elseif ($params -contains "ApiBase") { $args += @("-ApiBase", $baseUrl) }
  elseif ($params -contains "ApiUrl") { $args += @("-ApiUrl", $baseUrl) }

  if ($params -contains "KpiMode") { $args += @("-KpiMode", "strict") }
  elseif ($params -contains "Mode") { $args += @("-Mode", "strict") }

  if ($params -contains "ReportPath") { $args += @("-ReportPath", $reportJson) }
  elseif ($params -contains "ReportFile") { $args += @("-ReportFile", $reportJson) }
  elseif ($params -contains "OutFile") { $args += @("-OutFile", $reportJson) }
  elseif ($params -contains "OutputFile") { $args += @("-OutputFile", $reportJson) }
  elseif ($params -contains "EvidenceDir") { $args += @("-EvidenceDir", $evidenceDir) }
  elseif ($params -contains "OutDir") { $args += @("-OutDir", $evidenceDir) }

  if ($ArchitectKey) {
    if ($params -contains "ArchitectKey") { $args += @("-ArchitectKey", $ArchitectKey) }
    elseif ($params -contains "Key") { $args += @("-Key", $ArchitectKey) }
  }

  $r = Run-PwshScript -ScriptPath $smoke -Args ([string[]]$args) -LogPath $log
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

# -----------------------------
# Main
# -----------------------------
$repoRoot = Repo-Root
$BaseUrl = Normalize-BaseUrl $BaseUrl
$ComposeFile = Resolve-ComposeFile -repoRoot $repoRoot -composeFile $ComposeFile

if ([string]::IsNullOrWhiteSpace($ProjectName)) {
  throw "ProjectName is empty. Provide -ProjectName or set FF_COMPOSE_PROJECT/COMPOSE_PROJECT_NAME."
}
if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
  throw "ComposeFile is empty after resolve (unexpected)."
}

if (-not $ReleaseId) { $ReleaseId = ("m0_{0}" -f (Now-Stamp)) }
$ReleaseId = Normalize-ReleaseId $ReleaseId

if ([string]::IsNullOrWhiteSpace($BackupDir)) { $BackupDir = Join-Path $repoRoot "ops\_backups" }
if ($ArchitectKey) { $env:FF_ARCHITECT_KEY = $ArchitectKey }
$env:API_BASE = $BaseUrl

# evidence naming: avoid "release_m0_m0_<stamp>" when ReleaseId already has "m0_" prefix
$evSuffix = $ReleaseId
if ($ReleaseId -like "m0_*") { $evSuffix = ($ReleaseId -replace '^m0_', '') }
$evName = ($ReleaseId -like "release_m0_*") ? $ReleaseId : ("release_m0_" + $evSuffix)

$evidenceDir = Join-Path $repoRoot ("ops\_local\evidence\{0}" -f $evName)
Ensure-Dir $evidenceDir

# single canonical evidence line for callers/loggers
Write-Output ("evidence: " + $evidenceDir)

$started = Now-Iso
$swAll = [System.Diagnostics.Stopwatch]::StartNew()

$gitPre = Try-GetGitInfo $repoRoot
$preSha = $gitPre.sha

$lkgPath = Join-Path $repoRoot "ops\_local\lkg\last_known_good.json"

$exitCode = 0
$steps = New-Object System.Collections.Generic.List[object]

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
    compose_file = $ComposeFile
    project_name = $ProjectName
    migrate_mode_requested = $MigrateMode
    verify_gate_m0 = [bool]($VerifyDbContract -or $VerifyDbContractPlus)
    verify_gate_m0_plus = [bool]$VerifyDbContractPlus
    skip_fresh_db_drill = [bool]$SkipFreshDbDrill
    keep_fresh_db_drill_db = [bool]$KeepFreshDbDrillDb
    fresh_db_sql_worktree = $FreshDbSqlWorktree
    no_backup = [bool]$NoBackup
    no_build  = [bool]$NoBuild
    no_deploy = [bool]$NoDeploy
    no_smoke  = [bool]$NoSmoke
    no_rollback = [bool]$NoRollback
    git_pre = $gitPre
  } | ConvertTo-Json -Depth 60)
)

$rollbackPath = Join-Path $evidenceDir "rollback_story.md"
$backupOutDir = $null
$rollbackImageTag = $null
$failReason = ""
$ok = $true
$composeServices = @()

try {
  Write-Step "PRECHECK"
  Step "precheck" 2 {
    $ps = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("ps","-a")
    Set-Utf8 (Join-Path $evidenceDir "docker_compose_ps.txt") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $ps.argv, $ps.out, $ps.code)
    if ($ps.code -ne 0) { throw "docker compose ps failed (exit=$($ps.code))" }

    $sv = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("config","--services")
    Set-Utf8 (Join-Path $evidenceDir "docker_compose_services.txt") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $sv.argv, $sv.out, $sv.code)
    if ($sv.code -ne 0) { throw "docker compose config --services failed (exit=$($sv.code))" }

    $script:composeServices = @($sv.out -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  }

  Write-Step "WRITE rollback story (initial)"
  if (-not $NoRollback) {
    Write-RollbackStory -path $rollbackPath -ctx @{
      release_id = $ReleaseId
      pre_sha = $preSha
      base_url = $BaseUrl
      repo_root = $repoRoot
      compose_file = $ComposeFile
      project_name = $ProjectName
      backup_dir = $null
      rollback_image_tag = $null
    }
  } else {
    Write-Warn "NoRollback: skipping rollback story"
  }

  Write-Step "FRESH DB DRILL (bootstrap_min)"
  if ($SkipFreshDbDrill) {
    Write-Warn "SkipFreshDbDrill: skipping fresh DB drill"
    $steps.Add([pscustomobject]@{ name="fresh_db_drill"; ok=$true; skipped=$true; ts=Now-Iso }) | Out-Null
  } else {
    Step "fresh_db_drill" 10 {
      $drill = Join-Path $PSScriptRoot "ff-fresh-db-drill.ps1"
      if (-not (Test-Path -LiteralPath $drill)) { throw "ff-fresh-db-drill.ps1 not found: $drill" }

      $sqlWt = $FreshDbSqlWorktree
      if ([string]::IsNullOrWhiteSpace($sqlWt)) {
        $sqlWt = Resolve-SiblingWorktree -repoRoot $repoRoot -siblingName "C-sql"
      }
      if (-not $sqlWt) {
        throw "C-sql worktree not found near '$repoRoot'. Provide -FreshDbSqlWorktree explicitly."
      }

      $bootstrapAbs = Join-Path $sqlWt "scripts\sql\bootstrap_min_apply.sql"
      $suiteAbs     = Join-Path $sqlWt "scripts\sql\verify\suites\bootstrap_min.txt"
      if (-not (Test-Path -LiteralPath $bootstrapAbs)) { throw "bootstrap_min_apply.sql not found: $bootstrapAbs" }
      if (-not (Test-Path -LiteralPath $suiteAbs))     { throw "bootstrap_min suite not found: $suiteAbs" }

      # Detect optional params; BUT always pass the mandatory ones that currently prompt in your environment.
      $paramKeys = @()
      try { $paramKeys = @((Get-Command $drill -ErrorAction Stop).Parameters.Keys) } catch { $paramKeys = @() }
      Set-Utf8 (Join-Path $evidenceDir "fresh_db_drill_params_detected.json") (($paramKeys | ConvertTo-Json -Depth 10))

      $args = New-Object System.Collections.Generic.List[string]

      # Optional: SqlWorktree (if supported)
      if ($paramKeys -contains "SqlWorktree") {
        $args.Add("-SqlWorktree") | Out-Null; $args.Add($sqlWt) | Out-Null
      }

      # Mandatory for your current drill script (prevents interactive prompt)
      $args.Add("-BootstrapSqlPath") | Out-Null; $args.Add($bootstrapAbs) | Out-Null
      $args.Add("-SuiteFile")        | Out-Null; $args.Add($suiteAbs)     | Out-Null

      # Optional knobs (only if supported)
      if ($paramKeys -contains "PreferProject") {
        $args.Add("-PreferProject") | Out-Null; $args.Add($ProjectName) | Out-Null
      }
      if ($paramKeys -contains "PgUser") {
        $args.Add("-PgUser") | Out-Null; $args.Add("admin") | Out-Null
      }
      if ($KeepFreshDbDrillDb -and ($paramKeys -contains "KeepDb")) {
        $args.Add("-KeepDb") | Out-Null
      }

      Set-Utf8 (Join-Path $evidenceDir "fresh_db_drill_meta.json") (
        ([pscustomobject]@{
          ts = Now-Iso
          drill = $drill
          sql_worktree = $sqlWt
          bootstrap_abs = $bootstrapAbs
          suite_abs = $suiteAbs
          keep_db = [bool]$KeepFreshDbDrillDb
          args = $args.ToArray()
        } | ConvertTo-Json -Depth 40)
      )

      $log = Join-Path $evidenceDir "fresh_db_drill.log"
      $r = Run-PwshScript -ScriptPath $drill -Args ([string[]]$args.ToArray()) -LogPath $log
      if ($r.code -ne 0) { throw "Fresh DB drill failed (exit=$($r.code)). See: $log" }

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
      $b = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("build","api","worker","beat")
      Set-Utf8 (Join-Path $evidenceDir "build.log") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $b.argv, $b.out, $b.code)
      if ($b.code -ne 0) { throw "build failed (exit=$($b.code))" }
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
      Set-Utf8 $log ("== MIGRATE bootstrap_all_min ==`nrunner={0}`nts={1}`n" -f $migRunner, (Now-Iso))

      $tries = @(
        @("-Apply","-ComposeFile",$ComposeFile,"-ProjectName",$ProjectName),
        @("-Apply","-ComposeFile",$ComposeFile,"-Project",$ProjectName),
        @("-Apply","-ComposeFile",$ComposeFile)
      )

      $last = $null
      foreach ($a in $tries) {
        Add-Utf8 $log ("--- TRY args: {0}`n" -f ($a -join " "))
        $r = Run-PwshScript -ScriptPath $migRunner -Args ([string[]]$a) -LogPath $log -AppendLog
        $last = $r
        if ($r.code -eq 0) { break }

        $txt = $r.out
        $bindProjName = ($txt -match "parameter name 'ProjectName'") -or ($txt -match "cannot be found that matches parameter name 'ProjectName'")
        $bindProj     = ($txt -match "parameter name 'Project'")     -or ($txt -match "cannot be found that matches parameter name 'Project'")
        if ($bindProjName -or $bindProj) {
          Add-Utf8 $log "INFO: parameter binding mismatch -> trying next argset`n"
          continue
        }
        break
      }

      if (-not $last) { throw "bootstrap_all_min: internal error (no attempts executed)" }
      if ($last.code -ne 0) { throw "migrate bootstrap_all_min failed (exit=$($last.code))" }
    }
  }
  elseif ($MigrateMode -eq "sql_dirs") {
    Step "migrate_sql_dirs" 3 {
      $auto = Resolve-SqlDirs-Auto -repoRoot $repoRoot
      $migDir = if ($SqlMigrationsDir) { $SqlMigrationsDir } else { $auto.mig_dir }
      $fxAuto = if ($SqlFixpacksAutoDir) { $SqlFixpacksAutoDir } else { $auto.fix_auto_dir }
      $fxRoot = $auto.fix_root_dir

      Set-Utf8 (Join-Path $evidenceDir "migrate_sql_dirs_sources.json") (
        ([pscustomobject]@{
          mig_dir = $migDir
          fix_auto_dir = $fxAuto
          fix_root_dir = $fxRoot
          c_sql_root = $auto.c_sql_root
          apply_gate_fixpacks = [bool]$ApplyGateFixpacks
        } | ConvertTo-Json -Depth 40)
      )

      $plan = @()
      if ($migDir -and (Test-Path -LiteralPath $migDir)) {
        $plan += Get-ChildItem -LiteralPath $migDir -File -Filter "*.sql" | Sort-Object Name | Select-Object -ExpandProperty FullName
      }
      if ($ApplyGateFixpacks -and $fxRoot -and (Test-Path -LiteralPath $fxRoot)) {
        $plan += Get-ChildItem -LiteralPath $fxRoot -File -Filter "*_apply.sql" -ErrorAction SilentlyContinue |
                 Sort-Object Name | Select-Object -ExpandProperty FullName
      }
      if ($fxAuto -and (Test-Path -LiteralPath $fxAuto)) {
        $plan += Get-ChildItem -LiteralPath $fxAuto -File -Filter "*.sql" | Sort-Object Name | Select-Object -ExpandProperty FullName
      }

      $planPath = Join-Path $evidenceDir "migrate_sql_dirs_plan.txt"
      Set-Utf8 $planPath (($plan | ForEach-Object { $_ }) -join "`n")

      if (-not $plan -or $plan.Count -eq 0) {
        Write-Warn "sql_dirs: no sql files found (plan empty) — nothing to apply"
        return
      }

      foreach ($f in $plan) {
        $name = [System.IO.Path]::GetFileName($f)
        $log = Join-Path $evidenceDir ("migrate_sql_{0}.log" -f $name)
        $r = Invoke-PsqlSqlFile -composeFile $ComposeFile -projectName $ProjectName -sqlFile $f -logPath $log
        if ($r.code -ne 0) { throw "migrate sql_dirs failed on $name (exit=$($r.code))" }
      }
    }
  }
  elseif ($MigrateMode -eq "custom") {
    Step "migrate_custom" 3 {
      if (-not $MigrateScript) { throw "MigrateMode=custom requires -MigrateScript" }
      if (-not (Test-Path -LiteralPath $MigrateScript)) { throw "MigrateScript not found: $MigrateScript" }

      $log = Join-Path $evidenceDir "migrate_custom.log"
      $r = Run-PwshScript -ScriptPath $MigrateScript -Args ([string[]]@("-Apply","-ComposeFile",$ComposeFile,"-ProjectName",$ProjectName)) -LogPath $log
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

        $args = [string[]]@(
          "-SuiteFile",$suiteFile,
          "-EvidenceDir",$evidenceDir,
          "-ComposeFile",$ComposeFile,
          "-ProjectName",$ProjectName
        )

        $r = Run-PwshScript -ScriptPath $runner -Args $args -LogPath $log
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

      $d = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs (@("up","-d","--remove-orphans") + $servicesToUp)
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
      Wait-ApiReady -baseUrl $BaseUrl -timeoutSec $WaitApiTimeoutSec -pollSec $WaitApiPollSec -evidenceDir $evidenceDir | Out-Null
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
    compose_file = $ComposeFile
    project_name = $ProjectName
    migrate_mode = $MigrateMode
    backup_dir = $backupOutDir
    rollback_image_tag = $rollbackImageTag
    fresh_db_drill = [pscustomobject]@{
      skipped = [bool]$SkipFreshDbDrill
      keep_db = [bool]$KeepFreshDbDrillDb
      sql_worktree = $FreshDbSqlWorktree
    }
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
    $summaryJson = ($summary | ConvertTo-Json -Depth 95)
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
