#requires -Version 7.0
<#
FoxProFlow • DevFactory Gateway • commit-msg
file: scripts/pwsh/ff-dev-gateway-enforce-commit.ps1

Deny-by-default:
- Commit message MUST contain [DEVTASK:N]
- FlowSec P0: STAGED changes MUST pass secrets/PII scan (ff-sec-logscan-repo.ps1)
- DevTask must exist (API or DB fallback)

Exit codes:
  0 allow
  2 missing [DEVTASK:N]
  3 DevTask not found (API+DB)
  4 FlowSec secscan failed/findings
  1 other error
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [Parameter(Position=0)]
  [string]$CommitMsgFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function GW([string]$msg)  { Write-Host "[gateway] $msg" }
function GWW([string]$msg) { Write-Host "[gateway][warn] $msg" }

function Is-True([string]$v) {
  if (-not $v) { return $false }
  $t = $v.Trim().ToLowerInvariant()
  return ($t -in @("1","true","yes","y","on"))
}

function Trunc([string]$s, [int]$maxLen = 240) {
  if (-not $s) { return "" }
  $t = $s.Trim()
  if ($t.Length -le $maxLen) { return $t }
  return ($t.Substring(0, $maxLen) + "...<truncated>")
}

function Get-RepoRoot() {
  $root = (& git rev-parse --show-toplevel 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $root) { throw "git rev-parse --show-toplevel failed" }
  return $root.Trim()
}

function Get-CommitMsgFile([string]$p) {
  if ($p -and (Test-Path -LiteralPath $p)) { return (Resolve-Path -LiteralPath $p).Path }
  $cand = (& git rev-parse --git-path COMMIT_EDITMSG 2>$null)
  if ($LASTEXITCODE -eq 0 -and $cand -and (Test-Path -LiteralPath $cand)) { return (Resolve-Path -LiteralPath $cand).Path }
  throw "Commit message file not found."
}

function Read-TextBestEffort([string]$path) {
  try { return (Get-Content -LiteralPath $path -Raw -Encoding UTF8 -ErrorAction Stop) } catch {}
  try { return (Get-Content -LiteralPath $path -Raw -ErrorAction Stop) } catch {}
  throw "Cannot read commit message file: $path"
}

function Get-ApiBase() {
  if ($env:API_BASE) { return $env:API_BASE.TrimEnd("/") }
  if ($env:FF_API_BASE) { return $env:FF_API_BASE.TrimEnd("/") }
  return "http://127.0.0.1:8080"
}

function Try-ApiCheck([string]$baseUrl, [int]$taskId) {
  $url = "$baseUrl/api/devfactory/tasks/$taskId"
  $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
  if ($curl) {
    $tmpBody = [System.IO.Path]::GetTempFileName()
    $tmpErr  = [System.IO.Path]::GetTempFileName()
    try {
      $httpCode = & $curl.Source -4 --http1.1 --noproxy 127.0.0.1 `
        -sS --connect-timeout 2 -m 5 `
        -H "Accept: application/json" `
        -o $tmpBody -w "%{http_code}" $url 2> $tmpErr
      $codeInt = 0
      if ($httpCode -match '^\d{3}$') { $codeInt = [int]$httpCode }
      return [pscustomobject]@{ ok = ($LASTEXITCODE -eq 0 -and $codeInt -ge 200 -and $codeInt -lt 300); code = $codeInt; url = $url }
    } finally {
      Remove-Item -Force -ErrorAction SilentlyContinue $tmpBody
      Remove-Item -Force -ErrorAction SilentlyContinue $tmpErr
    }
  }
  try {
    $r = Invoke-WebRequest -Uri $url -Method GET -TimeoutSec 5 -Headers @{ Accept = "application/json" } -SkipHttpErrorCheck
    $code = [int]$r.StatusCode
    return [pscustomobject]@{ ok = ($code -ge 200 -and $code -lt 300); code = $code; url = $url }
  } catch {
    return [pscustomobject]@{ ok = $false; code = 0; url = $url }
  }
}

function Resolve-ComposeFile([string]$repoRoot) {
  if ($env:FF_COMPOSE_FILE -and (Test-Path -LiteralPath $env:FF_COMPOSE_FILE)) {
    return (Resolve-Path -LiteralPath $env:FF_COMPOSE_FILE).Path
  }
  $cand = Join-Path $repoRoot "docker-compose.yml"
  if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }
  throw "docker-compose.yml not found (set FF_COMPOSE_FILE)."
}

function Get-ComposeProjectArgs() {
  $pn = $null
  if ($env:FF_COMPOSE_PROJECT) { $pn = $env:FF_COMPOSE_PROJECT }
  elseif ($env:COMPOSE_PROJECT_NAME) { $pn = $env:COMPOSE_PROJECT_NAME }
  if ($pn) { return @("-p", $pn) }
  return @()
}

function Db-HasTask([string]$composeFile, [int]$taskId) {
  $svc = $(if ($env:FF_DB_SERVICE) { $env:FF_DB_SERVICE } else { "postgres" })
  $projArgs = Get-ComposeProjectArgs
  $dockerCmd = (Get-Command docker -ErrorAction Stop).Source
  $psqlCmd =
    'psql -U "${POSTGRES_USER:-admin}" -d "${POSTGRES_DB:-foxproflow}" ' +
    '-tA -P pager=off -v ON_ERROR_STOP=1 ' +
    '-c "SELECT 1 FROM dev.dev_task WHERE id = ' + $taskId + ' LIMIT 1;"'
  $argv = @("compose","--ansi","never","-f",$composeFile) + $projArgs + @("exec","-T",$svc,"sh","-lc",$psqlCmd)
  $out = & $dockerCmd @argv 2>&1
  if ($LASTEXITCODE -ne 0) { return $false }
  return (($out | Out-String).Trim() -eq "1")
}

function Resolve-SecScanPath([string]$repoRoot) {
  # Самый надёжный путь: рядом с gateway (в scripts/pwsh)
  $local = Join-Path $PSScriptRoot "ff-sec-logscan-repo.ps1"
  if (Test-Path -LiteralPath $local) { return $local }

  $cand = Join-Path $repoRoot "scripts\pwsh\ff-sec-logscan-repo.ps1"
  if (Test-Path -LiteralPath $cand) { return $cand }

  throw "SEC scan script missing (expected $local or $cand)."
}

function Run-SecScan([string]$repoRoot) {
  if (($env:FF_GATEWAY_SECSCAN ?? "").Trim() -eq "0") {
    if (-not (Is-True $env:FF_GATEWAY_BREAKGLASS)) { throw "SECSCAN disabled but BREAKGLASS not provided." }
    $reason = ($env:FF_GATEWAY_BREAKGLASS_REASON ?? "").Trim()
    if (-not $reason) { throw "BREAKGLASS=1 requires FF_GATEWAY_BREAKGLASS_REASON." }
    GWW ("BREAKGLASS: SECSCAN disabled. reason={0}" -f (Trunc $reason 200))
    return
  }

  $secscan = Resolve-SecScanPath $repoRoot
  $scanMode = "Secrets"
  if (Is-True $env:FF_GATEWAY_PII_SCAN) { $scanMode = "SecretsAndPII" }

  $evidenceDir = ($env:FF_GATEWAY_SECSCAN_EVIDENCE_DIR ?? "").Trim()
  if (-not $evidenceDir) { $evidenceDir = "ops\_local\evidence\secscan" }

  GW ("SEC gate: scanning STAGED for {0}..." -f $scanMode)
  & pwsh -NoProfile -ExecutionPolicy Bypass -File $secscan -Mode Staged -Scan $scanMode -EvidenceDir $evidenceDir
  $ec = $LASTEXITCODE
  if ($ec -ne 0) { throw "SEC gate FAIL (exit=$ec)." }
  GW "SEC gate OK."
}

# ---------------- main ----------------
Write-Host "=== DevFactory Gateway • commit check ==="

$CommitMsgFile = Get-CommitMsgFile $CommitMsgFile
GW ("Файл коммита: {0}" -f $CommitMsgFile)

$msg = Read-TextBestEffort $CommitMsgFile
$subject = ($msg -split "(\r?\n)", 2)[0]
GW ("Commit subject: {0}" -f (Trunc $subject 240))

$m = [regex]::Match($msg, '\[DEVTASK:(\d+)\]')
if (-not $m.Success) {
  GW "В сообщении коммита НЕТ маркера вида [DEVTASK:123]."
  exit 2
}

$taskId = [int]$m.Groups[1].Value
GW ("Найден DevFactory task id: {0}" -f $taskId)

# 0) FlowSec gate
try {
  $repoRoot = Get-RepoRoot
  Run-SecScan $repoRoot
} catch {
  GW ("FLOWSEC error: {0}" -f $_.Exception.Message)
  exit 4
}

# 1) DevTask check (API -> DB)
$apiBase = Get-ApiBase
$api = Try-ApiCheck -baseUrl $apiBase -taskId $taskId
GW ("Проверяю задачу через API: {0}" -f $api.url)
GW ("API статус: {0}" -f $api.code)

if ($api.ok) {
  GW "DevFactory задача найдена, commit разрешён."
  exit 0
}

GW "API не подтвердил задачу. Fallback: проверяю в DB (dev.dev_task)..."
try {
  $repoRoot2 = Get-RepoRoot
  $composeFile = Resolve-ComposeFile $repoRoot2
  if (Db-HasTask -composeFile $composeFile -taskId $taskId) {
    GW "DevFactory задача найдена в DB, commit разрешён."
    exit 0
  }
} catch { }

GW "FAIL: задача НЕ найдена ни через API, ни в DB."
exit 3
