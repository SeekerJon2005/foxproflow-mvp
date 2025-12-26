#requires -Version 7.0
<#
FoxProFlow • Security Lane • Immune Watchlist builder (advisory-first)
file: scripts/pwsh/sec/ff-sec-immune-watchlist.ps1
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  [string]$PolicyMapJson = "",
  [string]$OutDir = "",
  [string]$OutBaseName = "security_immune_watchlist_v0",
  [switch]$PrintSummaryOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Ensure-Dir([string]$p) {
  if ([string]::IsNullOrWhiteSpace($p)) { return }
  New-Item -ItemType Directory -Force -Path $p | Out-Null
}

function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }

function Repo-Root {
  (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Load-Json([string]$path) {
  $p = (Resolve-Path -LiteralPath $path).Path
  (Get-Content -Raw -LiteralPath $p) | ConvertFrom-Json -Depth 100
}

function As-Array($x) {
  if ($null -eq $x) { return @() }
  if ($x -is [System.Array]) { return @($x) }
  return @($x)
}

try {
  $root = Repo-Root
  if ([string]::IsNullOrWhiteSpace($OutDir)) { $OutDir = Join-Path $root "docs\ops\security" }
  Ensure-Dir $OutDir

  if ([string]::IsNullOrWhiteSpace($PolicyMapJson)) { $PolicyMapJson = Join-Path $OutDir "security_policy_map_v0.json" }
  if (-not (Test-Path -LiteralPath $PolicyMapJson)) { throw "PolicyMapJson not found: $PolicyMapJson" }

  $pm = Load-Json $PolicyMapJson
  $items = As-Array $pm.items

  $hot = @($items | Where-Object { $_.priority -in @("P0","P1") })

  $actionCounts = @(
    $hot | Group-Object action | Sort-Object Count -Descending | ForEach-Object {
      [pscustomobject]@{ count = [int]$_.Count; action = [string]$_.Name }
    }
  )

  $domainCounts = @(
    $hot | Group-Object domain | Sort-Object Count -Descending | ForEach-Object {
      [pscustomobject]@{ count = [int]$_.Count; domain = [string]$_.Name }
    }
  )

  $topActions = @($actionCounts | Select-Object -First 12 | ForEach-Object { $_.action })

  # Build watchlist directly (no nested function calls / no parentheses hell)
  $watchlist = @(
    [pscustomobject]@{
      id="IMM-001"; prio="P0";
      signal="Policy deny spike on P0/P1 actions";
      why="Рост deny по опасным действиям = дрейф ролей/ключей/политик или попытка обхода. Ранний индикатор инцидента.";
      threshold="WARN: >=20 denies/10m (P0/P1); CRIT: >=100 denies/10m или рост x5";
      evidence=@(
        "api logs: 403 Forbidden на protected endpoints",
        "ops/event_log (если есть): policy_deny/action/subject/ts",
        "devfactory events: deny на autofix/admin"
      );
      scope_actions=@($topActions)
    },

    [pscustomobject]@{
      id="IMM-002"; prio="P0";
      signal="Autofix enable/run attempts (denied or repeated)";
      why="Autofix = опасная кнопка. Повторные попытки без разрешения — misconfig или злоупотребление.";
      threshold="WARN: >=3 attempts/10m; CRIT: >=10 attempts/10m";
      evidence=@(
        "api: /api/devfactory/tasks/*/autofix/* (403/200)",
        "devfactory autofix events (если включены)",
        "audit trail: correlation_id + subject"
      );
      scope_actions=@($topActions | Where-Object { $_ -eq "devfactory.autofix_admin" })
    },

    [pscustomobject]@{
      id="IMM-003"; prio="P0";
      signal="5xx spike on execution domains (autoplan/devfactory/devorders)";
      why="Рост 5xx на контурах исполнения/коммерции = деградация и риск потери денег/доверия.";
      threshold="WARN: 5xx_rate >=2%/10m; CRIT: >=5%/10m или 10+ подряд";
      evidence=@(
        "api logs: ERROR/Traceback frequency",
        "health/extended latency + ready flags",
        "celery task failures correlated"
      );
      scope_actions=@($topActions | Where-Object { $_ -match '^autoplan\.|^devfactory\.|^devorders\.' })
    },

    [pscustomobject]@{
      id="IMM-004"; prio="P1";
      signal="Queue backlog / unregistered Celery tasks";
      why="Unregistered tasks и рост очередей = скрытый отказ контуров.";
      threshold="WARN: LLEN queue >100; CRIT: >1000 или Received unregistered task";
      evidence=@(
        "worker logs: Received unregistered task",
        "redis-cli LLEN <queue>",
        "celery inspect ping/registered"
      );
      scope_actions=@("ops.queue_read","ops.health_read")
    },

    [pscustomobject]@{
      id="IMM-005"; prio="P1";
      signal="Health degradation (ready=false, latency spikes)";
      why="Перед инцидентом часто растёт latency Postgres/Redis и ready=false.";
      threshold="WARN: pg latency >50ms; CRIT: >200ms или ready=false";
      evidence=@(
        "GET /health/extended snapshots",
        "docker compose ps + restarts",
        "postgres logs: connection/lock issues"
      );
      scope_actions=@("ops.health_read")
    }
  )

  if ($PrintSummaryOnly) {
    $domainCounts | Select-Object -First 20 | Format-Table -AutoSize
    $actionCounts | Select-Object -First 20 | Format-Table -AutoSize
    exit 0
  }

  $nl = [Environment]::NewLine
  $md = New-Object System.Collections.Generic.List[string]

  $md.Add("# FoxProFlow • Security Lane • Immune Watchlist v0 (advisory-first)") | Out-Null
  $md.Add(("Дата: {0}" -f (Get-Date -Format "yyyy-MM-dd"))) | Out-Null
  $md.Add("Создал: Архитектор Яцков Евгений Анатольевич") | Out-Null
  $md.Add("") | Out-Null
  $md.Add("Source policy map:") | Out-Null
  $md.Add($PolicyMapJson) | Out-Null
  $md.Add("") | Out-Null

  $md.Add("## 1) Hot domains/actions (P0/P1 coverage)") | Out-Null
  $md.Add("") | Out-Null

  $md.Add("### Domains (P0/P1)") | Out-Null
  $md.Add("| Count | Domain |") | Out-Null
  $md.Add("|---:|---|") | Out-Null
  foreach ($d in ($domainCounts | Select-Object -First 30)) { $md.Add(("| {0} | {1} |" -f $d.count, $d.domain)) | Out-Null }
  $md.Add("") | Out-Null

  $md.Add("### Actions (P0/P1)") | Out-Null
  $md.Add("| Count | Action |") | Out-Null
  $md.Add("|---:|---|") | Out-Null
  foreach ($a in ($actionCounts | Select-Object -First 40)) { $md.Add(("| {0} | {1} |" -f $a.count, $a.action)) | Out-Null }
  $md.Add("") | Out-Null

  $md.Add("## 2) Watchlist") | Out-Null
  $md.Add("") | Out-Null

  foreach ($w in $watchlist) {
    $md.Add(("### {0} ({1}) — {2}" -f $w.id, $w.prio, $w.signal)) | Out-Null
    $md.Add(("Why: {0}" -f $w.why)) | Out-Null
    $md.Add(("Threshold: {0}" -f $w.threshold)) | Out-Null
    $md.Add("Evidence:") | Out-Null
    foreach ($e in (As-Array $w.evidence)) { $md.Add(("- {0}" -f $e)) | Out-Null }
    $md.Add("Scope actions:") | Out-Null
    foreach ($sa in (As-Array $w.scope_actions | Select-Object -First 12)) { $md.Add(("- {0}" -f $sa)) | Out-Null }
    $md.Add("") | Out-Null
  }

  $outMd = Join-Path $OutDir ($OutBaseName + ".md")
  $outJson = Join-Path $OutDir ($OutBaseName + ".json")

  ($md.ToArray() -join $nl) | Set-Content -LiteralPath $outMd -Encoding utf8NoBOM

  $payload = [pscustomobject]@{
    ts = Now-Iso
    source_policy_map = $PolicyMapJson
    hot_domains = $domainCounts
    hot_actions = $actionCounts
    watchlist = $watchlist
  }
  ($payload | ConvertTo-Json -Depth 64) | Set-Content -LiteralPath $outJson -Encoding utf8NoBOM

  Write-Host ("[SEC IMMUNE WATCHLIST] written: {0}" -f $outMd) -ForegroundColor Green
  Write-Host ("[SEC IMMUNE WATCHLIST] json:    {0}" -f $outJson) -ForegroundColor Green
  exit 0
}
catch {
  Write-Host "[SEC IMMUNE WATCHLIST] FAIL" -ForegroundColor Red
  Write-Host ($_.Exception.Message) -ForegroundColor Red
  if ($_.InvocationInfo -and $_.InvocationInfo.PositionMessage) { Write-Host $_.InvocationInfo.PositionMessage -ForegroundColor Yellow }
  exit 1
}
