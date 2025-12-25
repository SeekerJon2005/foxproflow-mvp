#requires -Version 7.0
<#
FoxProFlow RUN • Gate C0 (Commercial One-Button)
file: scripts/pwsh/ff-gate-c0.ps1

Flow:
  precheck ->
  run M0 (deploy+wait; smoke off by default) ->
  verify suites (gate_m0 + optional gate_m0_plus) ->
  commercial checks (ping corr / 422 / 404 / 403 / recent / create+poll) ->
  optional dependency drill ->
  summary -> exit code

Evidence:
  ops/_local/evidence/<release_id>/...

Created by: Архитектор Яцков Евгений Анатольевич
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$BaseUrl = $(if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8080" }),

  [string]$ComposeFile = "",
  [string]$ProjectName = "",

  # C0 evidence folder name
  [string]$ReleaseId = "",

  # M0 ReleaseId (M0 evidence folder name: release_m0_<M0ReleaseId>)
  # Default: same as C0 ReleaseId (so evidence dir becomes release_m0_c0_YYYYMMDD_HHMMSS)
  [string]$M0ReleaseId = "",

  [string]$ArchitectKey = $(if ($env:FF_ARCHITECT_KEY) { "$env:FF_ARCHITECT_KEY".Trim() } else { "" }),

  # DB verify
  [switch]$VerifyPlus,

  # Optional: run M0 smoke too (usually not needed; C0 has own commercial checks)
  [switch]$AlsoRunM0Smoke,

  # Optional: dependency drill (stop worker -> POST -> 503 dependency -> start worker)
  [switch]$DependencyDrill,

  # Optional: speed knobs for M0
  [switch]$NoBackup,
  [switch]$NoBuild,

  [int]$HttpTimeoutSec = 20,
  [int]$OrderTimeoutSec = 120,
  [int]$PollSec = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$SCRIPT_VERSION = "2025-12-25.c0.v9"

# Stable exit codes:
# 0 OK
# 2 PRECHECK fail
# 3 M0 fail
# 4 VERIFY suites fail
# 5 COMMERCIAL fail
# 6 DEPENDENCY DRILL fail
$script:exitCode = 0

function Now-Iso   { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function Now-Stamp { (Get-Date).ToString("yyyyMMdd_HHmmss") }
function Repo-Root { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }

function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }
function Set-Utf8([string]$Path, [string]$Text) { $d = Split-Path $Path -Parent; if($d){Ensure-Dir $d}; $Text | Set-Content -LiteralPath $Path -Encoding utf8NoBOM }
function Add-Utf8([string]$Path, [string]$Text) { $d = Split-Path $Path -Parent; if($d){Ensure-Dir $d}; $Text | Add-Content -LiteralPath $Path -Encoding utf8NoBOM }

function Write-Step([string]$msg) { Write-Host ("`n==> " + $msg) -ForegroundColor Cyan }
function Write-Warn([string]$msg) { Write-Host ("WARN: " + $msg) -ForegroundColor Yellow }
function Write-Ok([string]$msg)   { Write-Host ("OK: " + $msg) -ForegroundColor Green }
function Write-Fail([string]$msg) { Write-Host ("FAIL: " + $msg) -ForegroundColor Red }

function Normalize-BaseUrl([string]$u) {
  if ([string]::IsNullOrWhiteSpace($u)) { $u = "http://127.0.0.1:8080" }
  if ($u -match "localhost") { $u = $u -replace "localhost","127.0.0.1" }
  return $u.TrimEnd("/")
}

function Resolve-ProjectName([string]$pn) {
  if (-not [string]::IsNullOrWhiteSpace($pn)) { return $pn }
  if ($env:FF_PROJECT) { return $env:FF_PROJECT }
  if ($env:FF_COMPOSE_PROJECT) { return $env:FF_COMPOSE_PROJECT }
  if ($env:COMPOSE_PROJECT_NAME) { return $env:COMPOSE_PROJECT_NAME }
  return "foxproflow-mvp20"
}

function Resolve-ComposeFile([string]$repoRoot, [string]$composeFile) {
  if ([string]::IsNullOrWhiteSpace($composeFile)) { $composeFile = Join-Path $repoRoot "docker-compose.yml" }
  if (-not (Test-Path -LiteralPath $composeFile)) { throw "ComposeFile not found: $composeFile" }
  return (Resolve-Path -LiteralPath $composeFile).Path
}

function Dc([string]$composeFile, [string]$projectName, [string[]]$composeArgs) {
  $argv = @("compose","--ansi","never","-f",$composeFile,"-p",$projectName) + $composeArgs
  $out = & docker @argv 2>&1
  return [pscustomobject]@{ code=$LASTEXITCODE; out=($out|Out-String); argv=("docker " + ($argv -join " ")) }
}

function Read-Header([string]$headersPath, [string]$name) {
  if (-not (Test-Path -LiteralPath $headersPath)) { return $null }
  $lines = Get-Content -LiteralPath $headersPath -ErrorAction SilentlyContinue
  $rx = "^{0}:\s*(.+)\s*$" -f [regex]::Escape($name)
  $val = $null
  foreach ($ln in $lines) {
    $m = [regex]::Match($ln, $rx, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if ($m.Success) { $val = $m.Groups[1].Value.Trim() }
  }
  return $val
}

function Http-Call(
  [string]$evidenceDir,
  [string]$name,
  [string]$method,
  [string]$path,
  [string]$correlationId,
  [string]$jsonBody,
  [hashtable]$extraHeaders
) {
  $url = $script:BaseUrl + $path

  $hdrPath  = Join-Path $evidenceDir ("http_{0}.headers.txt" -f $name)
  $bodyPath = Join-Path $evidenceDir ("http_{0}.body.txt" -f $name)
  $errPath  = Join-Path $evidenceDir ("http_{0}.stderr.txt" -f $name)
  $metaPath = Join-Path $evidenceDir ("http_{0}.meta.json" -f $name)

  $argv = @(
    "-4","--http1.1","--noproxy","127.0.0.1","--globoff",
    "-sS","-m",$HttpTimeoutSec,
    "-D",$hdrPath,
    "-o",$bodyPath,
    "-w","%{http_code}",
    "-X",$method
  )

  $argv += @("-H","Accept: application/json")
  $argv += @("-H",("X-Correlation-Id: {0}" -f $correlationId))

  if ($extraHeaders) {
    foreach ($k in $extraHeaders.Keys) {
      $argv += @("-H",("{0}: {1}" -f $k, $extraHeaders[$k]))
    }
  }

  if ($jsonBody) {
    $argv += @("-H","Content-Type: application/json","--data",$jsonBody)
  }

  $codeStr = & curl.exe @argv $url 2> $errPath
  $curlExit = $LASTEXITCODE

  $httpCode = 0
  $s = ($codeStr | Out-String).Trim()
  $m = [regex]::Match($s, '(\d{3})$')
  if ($m.Success) { $httpCode = [int]$m.Groups[1].Value }

  $body = ""
  if (Test-Path -LiteralPath $bodyPath) { $body = Get-Content -Raw -LiteralPath $bodyPath -ErrorAction SilentlyContinue }

  $json = $null
  try { if ($body) { $json = $body | ConvertFrom-Json -Depth 80 } } catch { $json = $null }

  Set-Utf8 $metaPath (([pscustomobject]@{
    name = $name
    method = $method
    path = $path
    url = $url
    correlation_id = $correlationId
    curl_exit = $curlExit
    http_code = $httpCode
    headers_file = $hdrPath
    body_file = $bodyPath
    stderr_file = $errPath
  }) | ConvertTo-Json -Depth 20)

  return [pscustomobject]@{
    http_code = $httpCode
    curl_exit = $curlExit
    body = $body
    json = $json
    headers_path = $hdrPath
  }
}

# ---------- REQUIRE (FIXED) ----------
function Resolve-RequireBool([object]$v) {
  if ($null -eq $v) { return $false }

  if ($v -is [bool]) { return $v }

  if ($v -is [sbyte] -or $v -is [byte] -or $v -is [int16] -or $v -is [uint16] -or
      $v -is [int] -or $v -is [uint32] -or $v -is [long] -or $v -is [uint64] -or
      $v -is [single] -or $v -is [double] -or $v -is [decimal]) {
    return ([double]$v -ne 0.0)
  }

  if ($v -is [string]) {
    return (-not [string]::IsNullOrWhiteSpace($v))
  }

  if ($v -is [type]) {
    throw "Require: cond must be boolean/truthy expression. Got Type '$($v.FullName)' (prints as '$v'). Likely bug: passed `.GetType()` or `[string]` instead of boolean (use `-is [string]`, `$null -ne `$x`, or `-not [string]::IsNullOrWhiteSpace(...)`)."
  }

  if ($v -is [System.Collections.IDictionary] -or $v -is [System.Collections.ICollection]) {
    try { return ($v.Count -gt 0) } catch { }
  }

  return $true
}

function Require([object]$cond, [string]$msg, [int]$failExitCode) {
  try {
    $b = Resolve-RequireBool $cond
    if (-not $b) {
      $script:exitCode = $failExitCode
      $caller = $null
      try { $caller = (Get-PSCallStack | Select-Object -Skip 1 -First 1) } catch { $caller = $null }
      if ($caller -and $caller.ScriptName) {
        throw ("{0} (at {1}:{2})" -f $msg, $caller.ScriptName, $caller.ScriptLineNumber)
      }
      throw $msg
    }
  } catch {
    $script:exitCode = $failExitCode
    $caller = $null
    try { $caller = (Get-PSCallStack | Select-Object -Skip 1 -First 1) } catch { $caller = $null }
    if ($caller -and $caller.ScriptName) {
      throw ("{0} (at {1}:{2})" -f $_.Exception.Message, $caller.ScriptName, $caller.ScriptLineNumber)
    }
    throw
  }
}

# ---------- StrictMode-safe JSON access ----------
function Try-GetPropValue([object]$obj, [string[]]$names) {
  if ($null -eq $obj) { return $null }
  foreach ($n in $names) {
    try {
      $p = $obj.PSObject.Properties[$n]
      if ($p) { return $p.Value }
    } catch {}
  }
  return $null
}

function Get-CommercialStatusInfo([object]$order) {
  if ($null -eq $order) { return $null }

  $lt = Try-GetPropValue $order @("last_task","lastTask","last_dev_task","lastDevTask","last_task_result","lastTaskResult")
  if ($lt) {
    $cs = Try-GetPropValue $lt @("commercial_status","commercialStatus","commercial","commercialState")
    if ($cs) { return [pscustomobject]@{ value=[string]$cs; source="last_task.*.commercial_status" } }

    $st = Try-GetPropValue $lt @("status","state")
    if ($st) { return [pscustomobject]@{ value=[string]$st; source="last_task.*.(status/state)" } }
  }

  $tasks = Try-GetPropValue $order @("tasks","dev_tasks","devTasks","task_list","taskList")
  if ($tasks) {
    try {
      $arr = @($tasks)
      if ($arr.Count -gt 0) {
        $t = $arr[-1]
        $cs2 = Try-GetPropValue $t @("commercial_status","commercialStatus","commercial","commercialState")
        if ($cs2) { return [pscustomobject]@{ value=[string]$cs2; source="tasks[-1].commercial_status" } }

        $st2 = Try-GetPropValue $t @("status","state")
        if ($st2) { return [pscustomobject]@{ value=[string]$st2; source="tasks[-1].(status/state)" } }
      }
    } catch {}
  }

  $res = Try-GetPropValue $order @("result","order_result","orderResult")
  if ($res) {
    $lt2 = Try-GetPropValue $res @("last_task","lastTask","last_dev_task","lastDevTask")
    if ($lt2) {
      $cs3 = Try-GetPropValue $lt2 @("commercial_status","commercialStatus","commercial","commercialState")
      if ($cs3) { return [pscustomobject]@{ value=[string]$cs3; source="result.last_task.commercial_status" } }
    }

    $cs4 = Try-GetPropValue $res @("commercial_status","commercialStatus")
    if ($cs4) { return [pscustomobject]@{ value=[string]$cs4; source="result.commercial_status" } }
  }

  $cs0 = Try-GetPropValue $order @("commercial_status","commercialStatus")
  if ($cs0) { return [pscustomobject]@{ value=[string]$cs0; source="root.commercial_status" } }

  return $null
}

# ---------- M0 parse guard ----------
function Get-ScriptParseErrors([string]$scriptPath) {
  $tok = $null; $err = $null
  [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tok, [ref]$err) | Out-Null
  return @($err)
}

function Write-ParseErrors([string]$scriptPath, [object[]]$errs, [string]$outBase) {
  try {
    $lst = @()
    foreach ($e in @($errs)) {
      if ($null -eq $e) { continue }
      $ext = $e.Extent
      $lst += [pscustomobject]@{
        message = $e.Message
        errorId = $e.ErrorId
        script  = $scriptPath
        line    = $ext.StartLineNumber
        col     = $ext.StartColumnNumber
        text    = [string]$ext.Text
      }
    }
    Set-Utf8 ($outBase + ".json") ($lst | ConvertTo-Json -Depth 10)
    $txt = ($lst | ForEach-Object {
      "line=$($_.line) col=$($_.col) id=$($_.errorId)`n$($_.message)`n>> $($_.text)`n"
    }) -join "`n"
    Set-Utf8 ($outBase + ".txt") $txt
  } catch {}
}

function Get-OrderIdFromCreate([object]$j) {
  foreach ($k in @("dev_order_id","order_id","id","id_uuid")) {
    try {
      $v = $j.$k
      if ($null -ne $v -and -not [string]::IsNullOrWhiteSpace([string]$v)) { return [string]$v }
    } catch {}
  }
  return ""
}

function Get-PwshExe() {
  try {
    if ($IsWindows) {
      $cand = Join-Path $PSHOME "pwsh.exe"
      if (Test-Path -LiteralPath $cand) { return $cand }
    }
  } catch {}
  return "pwsh"
}

function Invoke-PwshScript(
  [Parameter(Mandatory=$true)][string]$ScriptPath,
  [Parameter(Mandatory=$true)][string[]]$Args,
  [Parameter(Mandatory=$true)][string]$OutStdPath,
  [Parameter(Mandatory=$true)][string]$OutErrPath
) {
  if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Script not found: $ScriptPath" }

  $pwshExe = Get-PwshExe
  $argList = @("-NoProfile","-ExecutionPolicy","Bypass","-File",$ScriptPath) + ($Args ?? @())

  $p = Start-Process -FilePath $pwshExe `
    -ArgumentList $argList `
    -Wait -PassThru `
    -NoNewWindow `
    -RedirectStandardOutput $OutStdPath `
    -RedirectStandardError $OutErrPath

  return [pscustomobject]@{
    pwsh = $pwshExe
    argv = ($argList -join " ")
    exit_code = [int]$p.ExitCode
    stdout_path = $OutStdPath
    stderr_path = $OutErrPath
  }
}

function Resolve-M0EvidenceDir([string]$repoRoot, [string]$m0ReleaseId) {
  $base = Join-Path $repoRoot "ops\_local\evidence"
  $name = if ($m0ReleaseId -like "release_m0_*") { $m0ReleaseId } else { "release_m0_" + $m0ReleaseId }
  $cand = Join-Path $base $name
  if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }

  $hit = @(Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "release_m0_*" -and $_.Name -like "*$m0ReleaseId*" } |
    Sort-Object LastWriteTime -Desc |
    Select-Object -First 1)

  if ((@($hit)).Count -gt 0) { return $hit[0].FullName }
  return ""
}

function Copy-M0Evidence([string]$m0EvidenceDir, [string]$dstEvidenceDir) {
  if (-not $m0EvidenceDir) { return }
  $dst = Join-Path $dstEvidenceDir "m0"
  Ensure-Dir $dst

  $sum = Join-Path $m0EvidenceDir "release_m0_summary.json"
  if (Test-Path -LiteralPath $sum) {
    Copy-Item -Force -LiteralPath $sum -Destination (Join-Path $dstEvidenceDir "m0_release_m0_summary.json")
  }

  $files = @(Get-ChildItem -LiteralPath $m0EvidenceDir -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @(".json",".log",".txt",".md") } |
    Select-Object -ExpandProperty FullName)

  foreach ($f in $files) {
    try { Copy-Item -Force -LiteralPath $f -Destination (Join-Path $dst (Split-Path $f -Leaf)) } catch {}
  }

  $verify = Join-Path $m0EvidenceDir "verify"
  if (Test-Path -LiteralPath $verify) {
    try { Copy-Item -Recurse -Force -LiteralPath $verify -Destination (Join-Path $dst "verify") } catch {}
  }

  Set-Utf8 (Join-Path $dstEvidenceDir "m0_evidence_dir.txt") $m0EvidenceDir
}

# ---------------- MAIN ----------------
$script:BaseUrl = Normalize-BaseUrl $BaseUrl
$repoRoot = Repo-Root
$ComposeFile = Resolve-ComposeFile -repoRoot $repoRoot -composeFile $ComposeFile
$ProjectName = Resolve-ProjectName $ProjectName

if ([string]::IsNullOrWhiteSpace($ReleaseId)) { $ReleaseId = "c0_" + (Now-Stamp) }
if ([string]::IsNullOrWhiteSpace($M0ReleaseId)) { $M0ReleaseId = $ReleaseId }

# auto-load key from .env if placeholder/too short
if ($ArchitectKey -match '^\s*<.*>\s*$' -or $ArchitectKey.Length -lt 16) {
  try {
    $line = (Select-String -LiteralPath (Join-Path $repoRoot ".env") -Pattern '^\s*FF_ARCHITECT_KEY\s*=' -ErrorAction SilentlyContinue).Line
    if ($line) { $ArchitectKey = ($line -split '=',2)[1].Trim() }
  } catch {}
}

$evidenceDir = Join-Path $repoRoot ("ops\_local\evidence\{0}" -f $ReleaseId)
Ensure-Dir $evidenceDir

$started = Now-Iso
$steps = New-Object System.Collections.Generic.List[object]
$ok = $true
$failReason = ""

$transcriptPath = Join-Path $evidenceDir "transcript.txt"
try { Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null } catch {}

Set-Utf8 (Join-Path $evidenceDir "gate_c0_meta.json") (([pscustomobject]@{
  gate = "C0"
  script_version = $SCRIPT_VERSION
  release_id = $ReleaseId
  m0_release_id = $M0ReleaseId
  started = $started
  base_url = $script:BaseUrl
  compose_file = $ComposeFile
  project_name = $ProjectName
  verify_plus = [bool]$VerifyPlus
  also_run_m0_smoke = [bool]$AlsoRunM0Smoke
  dependency_drill = [bool]$DependencyDrill
  no_backup = [bool]$NoBackup
  no_build = [bool]$NoBuild
  http_timeout_sec = [int]$HttpTimeoutSec
  order_timeout_sec = [int]$OrderTimeoutSec
  poll_sec = [int]$PollSec
}) | ConvertTo-Json -Depth 30)

try {
  # PRECHECK
  Write-Step "PRECHECK"
  $ps = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("ps","-a")
  Set-Utf8 (Join-Path $evidenceDir "compose_ps.txt") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $ps.argv, $ps.out, $ps.code)
  Require ($ps.code -eq 0) "compose ps failed" 2

  $sv = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("config","--services")
  Set-Utf8 (Join-Path $evidenceDir "compose_services.txt") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $sv.argv, $sv.out, $sv.code)
  Require ($sv.code -eq 0) "compose config --services failed" 2
  $steps.Add([pscustomobject]@{ name="precheck"; ok=$true; ts=Now-Iso }) | Out-Null

  # RUN M0
  Write-Step "RUN M0 (deploy+wait)"
  $m0 = Join-Path $PSScriptRoot "ff-release-m0.ps1"
  Require (Test-Path -LiteralPath $m0) "Missing ff-release-m0.ps1" 3

  # Parse-guard (фиксит твой флап 15->0 ошибок: если M0 сломан, останавливаемся и пишем артефакты)
  $m0Parse = @(Get-ScriptParseErrors $m0)
  if ($m0Parse.Count -gt 0) {
    Write-ParseErrors -scriptPath $m0 -errs $m0Parse -outBase (Join-Path $evidenceDir "m0_parse_errors")
    Require $false "ff-release-m0.ps1 has parse errors (see m0_parse_errors.txt)" 3
  }

  $m0Args = @(
    "-BaseUrl",$script:BaseUrl,
    "-ComposeFile",$ComposeFile,
    "-ProjectName",$ProjectName,
    "-ReleaseId",$M0ReleaseId,
    "-MigrateMode","sql_dirs",
    "-ApplyGateFixpacks"
  )
  if ($NoBackup) { $m0Args += "-NoBackup" }
  if ($NoBuild)  { $m0Args += "-NoBuild" }
  if (-not $AlsoRunM0Smoke) { $m0Args += "-NoSmoke" }

  Set-Utf8 (Join-Path $evidenceDir "m0_cmdline.txt") ("pwsh -NoProfile -ExecutionPolicy Bypass -File `"{0}`" {1}" -f $m0, ($m0Args -join " "))

  $m0Std = Join-Path $evidenceDir "m0_stdout.log"
  $m0Err = Join-Path $evidenceDir "m0_stderr.log"
  $m0Run = Join-Path $evidenceDir "m0_run.log"

  $r = Invoke-PwshScript -ScriptPath $m0 -Args $m0Args -OutStdPath $m0Std -OutErrPath $m0Err

  Set-Utf8 $m0Run ("argv={0}`nexit_code={1}`n--- stdout ---`n" -f $r.argv, $r.exit_code)
  if (Test-Path -LiteralPath $m0Std) { Add-Utf8 $m0Run (Get-Content -Raw -LiteralPath $m0Std -ErrorAction SilentlyContinue) }
  Add-Utf8 $m0Run "`n--- stderr ---`n"
  if (Test-Path -LiteralPath $m0Err) { Add-Utf8 $m0Run (Get-Content -Raw -LiteralPath $m0Err -ErrorAction SilentlyContinue) }

  $m0EvDir = Resolve-M0EvidenceDir -repoRoot $repoRoot -m0ReleaseId $M0ReleaseId
  if ($m0EvDir) {
    Copy-M0Evidence -m0EvidenceDir $m0EvDir -dstEvidenceDir $evidenceDir
    Add-Utf8 $m0Run ("`nM0 evidence dir: {0}`n" -f $m0EvDir)
  } else {
    Add-Utf8 $m0Run "`nM0 evidence dir not found (M0 may have failed before creating evidence).`n"
  }

  if ($r.exit_code -ne 0) {
    Require $false ("M0 failed (exit={0}). See m0_run.log and m0/* artifacts if present." -f $r.exit_code) 3
  }

  $steps.Add([pscustomobject]@{ name="m0"; ok=$true; ts=Now-Iso; exit_code=$r.exit_code; m0_release_id=$M0ReleaseId }) | Out-Null

  # VERIFY suites
  Write-Step "VERIFY suites (gate_m0)"
  $suiteRunner = Join-Path $PSScriptRoot "ff-db-verify-suite.ps1"
  Require (Test-Path -LiteralPath $suiteRunner) "Missing suite runner" 4

  $verifyDir = Join-Path $evidenceDir "verify"
  Ensure-Dir $verifyDir

  $parent = Split-Path $repoRoot -Parent
  $cSqlRoot = Join-Path $parent "C-sql"
  Require (Test-Path -LiteralPath $cSqlRoot) ("C-sql worktree not found: {0}" -f $cSqlRoot) 4

  $suiteM0   = Join-Path $cSqlRoot "scripts\sql\verify\suites\gate_m0.txt"
  $suitePlus = Join-Path $cSqlRoot "scripts\sql\verify\suites\gate_m0_plus.txt"
  Require (Test-Path -LiteralPath $suiteM0) ("Verify suite file not found: {0}" -f $suiteM0) 4

  $r1 = Invoke-PwshScript -ScriptPath $suiteRunner `
    -Args @("-SuiteFile",$suiteM0,"-EvidenceDir",$verifyDir,"-ComposeFile",$ComposeFile,"-ProjectName",$ProjectName) `
    -OutStdPath (Join-Path $verifyDir "suite_stdout.log") `
    -OutErrPath (Join-Path $verifyDir "suite_stderr.log")

  Set-Utf8 (Join-Path $verifyDir "verify_gate_m0.runner.log") ("argv={0}`nexit_code={1}`n" -f $r1.argv, $r1.exit_code)
  Require ($r1.exit_code -eq 0) "verify suite gate_m0 failed (see verify/ folder)" 4
  $steps.Add([pscustomobject]@{ name="verify_gate_m0"; ok=$true; ts=Now-Iso }) | Out-Null

  if ($VerifyPlus) {
    Write-Step "VERIFY suites (gate_m0_plus)"
    Require (Test-Path -LiteralPath $suitePlus) ("Verify suite file not found: {0}" -f $suitePlus) 4

    $r2 = Invoke-PwshScript -ScriptPath $suiteRunner `
      -Args @("-SuiteFile",$suitePlus,"-EvidenceDir",$verifyDir,"-ComposeFile",$ComposeFile,"-ProjectName",$ProjectName) `
      -OutStdPath (Join-Path $verifyDir "suite_plus_stdout.log") `
      -OutErrPath (Join-Path $verifyDir "suite_plus_stderr.log")

    Set-Utf8 (Join-Path $verifyDir "verify_gate_m0_plus.runner.log") ("argv={0}`nexit_code={1}`n" -f $r2.argv, $r2.exit_code)
    Require ($r2.exit_code -eq 0) "verify suite gate_m0_plus failed (see verify/ folder)" 4
    $steps.Add([pscustomobject]@{ name="verify_gate_m0_plus"; ok=$true; ts=Now-Iso }) | Out-Null
  }

  # COMMERCIAL CHECKS
  Write-Step "COMMERCIAL checks"
  $body = '{"order_type":"stand_diagnostics_v1","payload":{}}'

  # 1) crm ping
  $cid = "c0-{0}-ping" -f $ReleaseId
  $rA = Http-Call -evidenceDir $evidenceDir -name "01_crm_ping" -method "GET" -path "/api/crm/smoke/ping" -correlationId $cid -jsonBody $null -extraHeaders @{}
  Require ($rA.curl_exit -eq 0) "curl failed on crm ping" 5
  Require ($rA.http_code -ge 200 -and $rA.http_code -lt 300) ("crm ping bad http: {0}" -f $rA.http_code) 5
  $xh = Read-Header $rA.headers_path "x-correlation-id"
  Require ($xh -eq $cid) ("x-correlation-id mismatch (crm ping): expected={0} actual={1}" -f $cid, $xh) 5

  # 2) 422
  $cid = "c0-{0}-422" -f $ReleaseId
  $rB = Http-Call -evidenceDir $evidenceDir -name "02_recent_422" -method "GET" -path "/api/devfactory/orders/recent?limit=oops&include_result=0" -correlationId $cid -jsonBody $null -extraHeaders @{}
  Require ($rB.http_code -eq 422) ("expected 422, got {0}" -f $rB.http_code) 5
  $errB = Try-GetPropValue $rB.json @("error","err")
  $kindB = Try-GetPropValue $errB @("kind","type")
  Require ($kindB -eq "validation") ("422 expected error.kind=validation, got '{0}'" -f $kindB) 5

  # 3) 404
  $cid = "c0-{0}-404" -f $ReleaseId
  $rC = Http-Call -evidenceDir $evidenceDir -name "03_task_404" -method "GET" -path "/api/devfactory/tasks/999999999" -correlationId $cid -jsonBody $null -extraHeaders @{}
  Require ($rC.http_code -eq 404) ("expected 404, got {0}" -f $rC.http_code) 5
  $errC = Try-GetPropValue $rC.json @("error","err")
  $kindC = Try-GetPropValue $errC @("kind","type")
  Require ($kindC -eq "validation") ("404 expected error.kind=validation, got '{0}'" -f $kindC) 5

  # 4) 403 without key
  $cid = "c0-{0}-403" -f $ReleaseId
  $rD = Http-Call -evidenceDir $evidenceDir -name "04_create_403" -method "POST" -path "/api/devfactory/orders" -correlationId $cid -jsonBody $body -extraHeaders @{}
  Require ($rD.http_code -eq 403) ("expected 403, got {0}" -f $rD.http_code) 5
  $errD = Try-GetPropValue $rD.json @("error","err")
  $kindD = Try-GetPropValue $errD @("kind","type")
  Require ($kindD -eq "policy") ("403 expected error.kind=policy, got '{0}'" -f $kindD) 5

  # 5) recent ok
  $cid = "c0-{0}-recent" -f $ReleaseId
  $rE = Http-Call -evidenceDir $evidenceDir -name "05_recent_ok" -method "GET" -path "/api/devfactory/orders/recent?limit=10&include_result=0" -correlationId $cid -jsonBody $null -extraHeaders @{}
  Require ($rE.http_code -ge 200 -and $rE.http_code -lt 300) ("recent bad http: {0}" -f $rE.http_code) 5
  $okE = Try-GetPropValue $rE.json @("ok","success")
  Require ($okE -eq $true) ("recent expected ok=true, got '{0}'" -f $okE) 5

  # 6) create + poll
  Require (-not [string]::IsNullOrWhiteSpace($ArchitectKey)) "FF_ARCHITECT_KEY is empty — required for create+poll" 5
  $hdrKey = @{
    "X-FF-Architect-Key" = $ArchitectKey
    "X-Architect-Key"    = $ArchitectKey
    "Authorization"      = ("Bearer " + $ArchitectKey)
  }

  $cid = "c0-{0}-create" -f $ReleaseId
  $rF = Http-Call -evidenceDir $evidenceDir -name "06_create_ok" -method "POST" -path "/api/devfactory/orders" -correlationId $cid -jsonBody $body -extraHeaders $hdrKey
  Require ($rF.http_code -ge 200 -and $rF.http_code -lt 300) ("create bad http: {0}" -f $rF.http_code) 5
  $okF = Try-GetPropValue $rF.json @("ok","success")
  Require ($okF -eq $true) ("create expected ok=true, got '{0}'" -f $okF) 5

  $oid = Get-OrderIdFromCreate $rF.json
  Require (-not [string]::IsNullOrWhiteSpace($oid)) "cannot extract order id from create response" 5
  Set-Utf8 (Join-Path $evidenceDir "created_order_id.txt") $oid

  $deadline = (Get-Date).AddSeconds($OrderTimeoutSec)
  $final = $null
  $n = 0
  while ((Get-Date) -lt $deadline) {
    $n++
    $cidp = "c0-{0}-poll-{1}" -f $ReleaseId, $n
    $rp = Http-Call -evidenceDir $evidenceDir -name ("07_poll_{0:00}" -f $n) -method "GET" -path ("/api/devfactory/orders/{0}?include_result=1" -f $oid) -correlationId $cidp -jsonBody $null -extraHeaders $hdrKey

    if ($rp.http_code -ge 200 -and $rp.http_code -lt 300 -and $rp.json) {
      $okP = Try-GetPropValue $rp.json @("ok","success")
      if ($okP -eq $true) {
        $st = Try-GetPropValue $rp.json @("status","state")
        if ($st -in @("done","failed","error")) { $final = $rp.json; break }
      }
    }
    Start-Sleep -Seconds $PollSec
  }

  Require ($null -ne $final) "poll timeout: order did not reach terminal status" 5
  try { Set-Utf8 (Join-Path $evidenceDir "final_order.json") ($final | ConvertTo-Json -Depth 90) } catch {}

  $finalStatus = Try-GetPropValue $final @("status","state")
  Require ($finalStatus -eq "done") ("order terminal status not done: {0}" -f $finalStatus) 5

  $csInfo = Get-CommercialStatusInfo $final
  if (-not $csInfo) {
    Require $false "Cannot determine commercial status: no last_task/tasks/commercial_status in order payload (see final_order.json)" 5
  }

  Set-Utf8 (Join-Path $evidenceDir "commercial_status_detected.txt") ("source={0}`nvalue={1}`n" -f $csInfo.source, $csInfo.value)

  $csNorm = ([string]$csInfo.value).Trim().ToLowerInvariant()
  Require ($csNorm -in @("succeeded","success")) ("commercial_status not succeeded: {0} (source={1})" -f $csInfo.value, $csInfo.source) 5

  $steps.Add([pscustomobject]@{ name="commercial"; ok=$true; ts=Now-Iso; order_id=$oid; commercial_source=$csInfo.source; commercial_value=$csInfo.value }) | Out-Null

  # 7) dependency drill
  if ($DependencyDrill) {
    Write-Step "DEPENDENCY DRILL (stop worker -> 503 dependency -> up worker)"
    try {
      $stop = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("stop","worker")
      Set-Utf8 (Join-Path $evidenceDir "depdrill_stop_worker.log") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $stop.argv, $stop.out, $stop.code)

      $cid = "c0-{0}-dep503" -f $ReleaseId
      $rd = Http-Call -evidenceDir $evidenceDir -name "08_depdrill_503" -method "POST" -path "/api/devfactory/orders" -correlationId $cid -jsonBody $body -extraHeaders $hdrKey
      Require ($rd.http_code -eq 503) ("expected 503, got {0}" -f $rd.http_code) 6
      $errX = Try-GetPropValue $rd.json @("error","err")
      $kindX = Try-GetPropValue $errX @("kind","type")
      Require ($kindX -eq "dependency") ("503 expected error.kind=dependency, got '{0}'" -f $kindX) 6

      $steps.Add([pscustomobject]@{ name="dependency_drill"; ok=$true; ts=Now-Iso }) | Out-Null
    } finally {
      $up = Dc -composeFile $ComposeFile -projectName $ProjectName -composeArgs @("up","-d","worker")
      Set-Utf8 (Join-Path $evidenceDir "depdrill_up_worker.log") ("argv={0}`n`n{1}`nexit_code={2}`n" -f $up.argv, $up.out, $up.code)
    }
  }

  Write-Ok "C0 PASS"
  $script:exitCode = 0

} catch {
  $ok = $false
  $failReason = $_.Exception.Message
  if ($script:exitCode -eq 0) { $script:exitCode = 1 }
  Write-Fail $failReason

  try {
    Set-Utf8 (Join-Path $evidenceDir "gate_c0_error.txt") (
      "ts={0}`nexit_code={1}`nerror={2}`n`n{3}" -f (Now-Iso), $script:exitCode, $failReason, ($_.Exception.ToString())
    )
  } catch {}
} finally {
  try { Stop-Transcript | Out-Null } catch {}
}

$ended = Now-Iso
$summary = [pscustomobject]@{
  gate = "C0"
  script_version = $SCRIPT_VERSION
  release_id = $ReleaseId
  m0_release_id = $M0ReleaseId
  started = $started
  ended = $ended
  ok = $ok
  exit_code = $script:exitCode
  fail_reason = $failReason
  base_url = $script:BaseUrl
  compose_file = $ComposeFile
  project_name = $ProjectName
  evidence_dir = $evidenceDir
  steps = @($steps.ToArray())
}
Set-Utf8 (Join-Path $evidenceDir "gate_c0_summary.json") ($summary | ConvertTo-Json -Depth 90)

exit $script:exitCode
