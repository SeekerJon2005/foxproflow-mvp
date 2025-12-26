#requires -Version 7.0
<#
FoxProFlow • Security Lane • Outreach Composer (evidence-first) v1.2
file: scripts/pwsh/sec/ff-sec-outreach-compose.ps1

v1.1:
  - Remove internal ops/_local paths from EMAIL output (keep in JSON/meta only)
  - Add CTA with 2 suggested time slots
  - Add -BatchCsv for mass generation

v1.2:
  - Replace pilot -> пилот (subjects + email)
  - Replace evidence pack -> пакет доказательств (subjects + email)
  - Add 1-line "Итог пилота" after deliverables (short + full)
  - Make call opener phrasing more Russian (no "evidence pack:")

Goal:
  Generate ready-to-send outreach materials (email subjects + bodies + call script + checklist)
  tailored by segment/company/persona, and write to evidence folder.

Outputs:
  ops/_local/evidence/outreach_<stamp>/
    - outreach_<company_slug>.md
    - outreach_<company_slug>.json
    - meta.json

Usage (single):
  pwsh -NoProfile -File .\scripts\pwsh\sec\ff-sec-outreach-compose.ps1 `
    -Company "Wildberries" -Segment marketplace -ContactName "Иван" -ContactRole "CTO" -Depth full -OpenFolder

Usage (batch):
  pwsh -NoProfile -File .\scripts\pwsh\sec\ff-sec-outreach-compose.ps1 `
    -BatchCsv ".\ops\_local\in\outreach_targets.csv"

CSV columns (header required):
  company,segment,contact_name,contact_role,depth
  segment: marketplace|bank|ecosystem|saas|logistics|custom
  depth: short|full

Notes:
  - READ-ONLY wrt repo. Writes only to ops/_local/evidence
  - No external deps.
#>

[CmdletBinding(PositionalBinding=$false)]
param(
  # Single mode
  [string]$Company = "",
  [ValidateSet("marketplace","bank","ecosystem","saas","logistics","custom")]
  [string]$Segment = "custom",
  [string]$ContactName = "",
  [string]$ContactRole = "",
  [ValidateSet("short","full")]
  [string]$Depth = "short",

  # Batch mode
  [string]$BatchCsv = "",

  # Evidence
  [string]$EvidenceRoot = "",

  # References kept in JSON/meta (not printed in emails)
  [string]$GateEvidenceDir = "ops/_local/evidence/sec_gate_v0_20251226_062509",
  [string]$PilotPdfEvidence = "ops/_local/evidence/pilot_proposal_pdf_20251226_071403/proposal.pdf",

  # CTA
  [string]$CtaTz = "MSK",
  [string]$CtaSlot1 = "завтра 11:00–13:00",
  [string]$CtaSlot2 = "послезавтра 15:00–17:00",

  [switch]$OpenFolder
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Now-Stamp { Get-Date -Format "yyyyMMdd_HHmmss" }
function Now-Iso { (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffK") }
function Ensure-Dir([string]$p) { if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }

function Repo-Root {
  (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Slugify([string]$s) {
  if ([string]::IsNullOrWhiteSpace($s)) { return "company" }
  $t = $s.Trim().ToLowerInvariant()
  $t = $t -replace '[^a-z0-9а-яё]+','_'
  $t = $t -replace '_+','_'
  $t = $t.Trim('_')
  if ($t.Length -gt 48) { $t = $t.Substring(0,48) }
  if ([string]::IsNullOrWhiteSpace($t)) { return "company" }
  return $t
}

function GreetingLine([string]$name) {
  if ([string]::IsNullOrWhiteSpace($name)) { return "Здравствуйте!" }
  return ("Здравствуйте, {0}!" -f $name.Trim())
}

function Segment-Profile([string]$seg) {
  switch ($seg) {
    "marketplace" { return [pscustomobject]@{ label="Маркетплейс / e-commerce"; why_now="высокая цена простоя, быстрые релизы, много интеграций и дрейф правил"; focus="безопасность изменений + раннее предупреждение дрейфа/аномалий"; proof="surface/policy/watchlist/drill/coverage" } }
    "bank"        { return [pscustomobject]@{ label="Банк / финтех";            why_now="регуляторка и аудит, высокая токсичность ошибок, контроль изменений и доказуемость решений"; focus="доказуемый контроль опасных действий (policy gates) + иммунитет деградаций"; proof="повторяемые артефакты для внутреннего аудита" } }
    "ecosystem"   { return [pscustomobject]@{ label="Экосистема / платформа";   why_now="много команд и продуктов => дрейф практик, рост инцидентов на стыках"; focus="унификация policy plane и иммунитет сигналов для SRE/Platform/Sec"; proof="one-click gate + baseline метрики до/после" } }
    "saas"        { return [pscustomobject]@{ label="B2B SaaS";                 why_now="SLA и удержание: цена деградации и инцидентов растёт вместе с клиентами"; focus="контроль изменений и раннее предупреждение без торможения релизов"; proof="drill + coverage как регулярный отчёт" } }
    "logistics"   { return [pscustomobject]@{ label="Логистика / TMS / 3PL";    why_now="сложные цепочки, много сторонних систем, критичность ошибок в исполнении"; focus="policy на опасные операции (confirm/apply/autofix) + иммунитет на дрейф"; proof="срез поверхности + план enable-enforce по whitelist" } }
    default       { return [pscustomobject]@{ label="Custom";                  why_now="рост сложности и цены ошибок"; focus="advisory-first безопасность изменений + доказуемость"; proof="one-click gate" } }
  }
}

function Build-Subjects([string]$company, [pscustomobject]$prof) {
  $c = $company.Trim()
  return @(
    ("{0}: пилот по безопасности изменений (advisory-first) + пакет доказательств" -f $c),
    ("{0}: раннее предупреждение инцидентов и контроль опасных действий (без блокировок)" -f $c),
    ("{0}: 2-недельный read-only пилот безопасности изменений (surface/policy/immune)" -f $c)
  )
}

function Build-Cta([string]$slot1, [string]$slot2, [string]$tz) {
  $s1 = $slot1.Trim()
  $s2 = $slot2.Trim()
  $t  = $tz.Trim()
  return ("Если откликается — удобно созвониться 20 минут: {0} или {1} ({2})?" -f $s1, $s2, $t)
}

function PilotOutcomeLine() {
  return "Итог пилота: карта P0/P1 + baseline по дрейфу/инцидентам + план whitelist-enforce (опционально)."
}

function Build-EmailShort([string]$company, [pscustomobject]$prof, [string]$contactName, [string]$contactRole, [string]$ctaLine) {
  $greet = GreetingLine $contactName
  $roleLine = ""
  if ($contactRole) { $roleLine = ("({0})" -f $contactRole.Trim()) }

  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add($greet) | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add(("Я — Евгений Яцков, FoxProFlow. Предлагаю 2-недельный пилот по безопасности изменений в режиме advisory-first (read-only): без блокировок по умолчанию и без доступа к вашему ядру. {0}" -f $roleLine).Trim()) | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("Что вы получаете на выходе:") | Out-Null
  $lines.Add("- инвентарь поверхности и P0/P1 опасных действий (surface map);") | Out-Null
  $lines.Add("- action/policy карта гейтов (whitelist-подход);") | Out-Null
  $lines.Add("- immune-watchlist сигналов (deny/5xx/backlog/health) + пороги;") | Out-Null
  $lines.Add("- one-click пакет доказательств (повторяемые артефакты для руководства/аудита).") | Out-Null
  $lines.Add((PilotOutcomeLine)) | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add(("Почему актуально для {0}: {1}." -f $company.Trim(), $prof.why_now)) | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("Пилот безопасный: ничего не блокируем, не меняем бизнес-логику, фиксируем baseline и выдаём план перехода к enforce через whitelist и окна обслуживания (опционально).") | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add($ctaLine) | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("С уважением,") | Out-Null
  $lines.Add("Евгений Яцков") | Out-Null
  $lines.Add("FoxProFlow") | Out-Null

  return ($lines.ToArray() -join [Environment]::NewLine)
}

function Build-EmailFull([string]$company, [pscustomobject]$prof, [string]$contactName, [string]$contactRole, [string]$ctaLine) {
  $greet = GreetingLine $contactName
  $roleLine = ""
  if ($contactRole) { $roleLine = ("Роль: {0}" -f $contactRole.Trim()) }

  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add($greet) | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("Я — Евгений Яцков, FoxProFlow. Мы делаем функцию безопасности изменений и «иммунитет» раннего предупреждения: policy-gates на опасные действия + мониторинг сигналов деградации (advisory-first).") | Out-Null
  if ($roleLine) { $lines.Add($roleLine) | Out-Null }
  $lines.Add("") | Out-Null
  $lines.Add(("Контекст для {0}: {1}." -f $company.Trim(), $prof.why_now)) | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("Формат пилота (2 недели, read-only):") | Out-Null
  $lines.Add("- enforce выключен: ничего не блокируем по умолчанию;") | Out-Null
  $lines.Add("- не нужен доступ к коду/ядру; работаем поверх наблюдаемости/выгрузок;") | Out-Null
  $lines.Add("- на выходе — пакет доказательств и план whitelist-enforce (опционально).") | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("Deliverables:") | Out-Null
  $lines.Add("1) Surface map: поверхность + приоритет P0/P1.") | Out-Null
  $lines.Add("2) Policy map: action/policy имена и гейт-контуры.") | Out-Null
  $lines.Add("3) Immune watchlist: deny/5xx/backlog/health + пороги WARN/CRIT.") | Out-Null
  $lines.Add("4) One-click gate: прогон с доказательствами и coverage score.") | Out-Null
  $lines.Add((PilotOutcomeLine)) | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("Что нужно от вас (минимально):") | Out-Null
  $lines.Add("- 2–5 критичных контуров/сервисов;") | Out-Null
  $lines.Add("- read-only логи/метрики или выгрузки (по вашим правилам);") | Out-Null
  $lines.Add("- контакт SRE/Platform/Sec инженера на 2 недели.") | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add($ctaLine) | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("С уважением,") | Out-Null
  $lines.Add("Евгений Яцков") | Out-Null
  $lines.Add("FoxProFlow") | Out-Null

  return ($lines.ToArray() -join [Environment]::NewLine)
}

function Build-CallOpener([string]$company, [pscustomobject]$prof) {
  return ("20 секунд: Мы предлагаем {0} для {1}. На выходе: {2}. Формат безопасный: advisory-first, без блокировок, с пакетом доказательств." -f $prof.focus, $company.Trim(), $prof.proof)
}

function Build-CallScript([string]$company) {
  $lines = @(
    "0:00–0:20 — Контекст: «мы про безопасность изменений и раннее предупреждение».",
    "0:20–1:20 — Почему сейчас: цена простоя/ошибок растёт, интеграций больше, дрейф правил ускоряется.",
    "1:20–2:20 — Формат пилота: advisory-first, read-only, без доступа к ядру, без enforce по умолчанию.",
    "2:20–3:20 — Deliverables: surface/policy/watchlist + one-click gate + доказательства + coverage.",
    "3:20–4:20 — Что нужно от {0}: 2–5 критичных контуров + read-only наблюдаемость/выгрузки + контакт SRE/Platform.",
    "4:20–5:00 — Next step: whitelist-enforce в окна обслуживания (опционально)."
  )
  $lines[4] = ($lines[4] -f $company.Trim())
  return ($lines -join [Environment]::NewLine)
}

function Build-Checklist() {
  return @(
    "- Какие контуры самые критичные (деньги/простои/регуляторка)?",
    "- Где чаще всего ломается: релизы, миграции, фоновые задачи, интеграции?",
    "- Какие метрики уже есть: change failure rate, MTTR, incident rate?",
    "- Где лежат логи/метрики (observability стек)?",
    "- Кто владелец релиз-процесса (SRE/Platform/Sec)?"
  ) -join [Environment]::NewLine
}

function Compose-One {
  param(
    [Parameter(Mandatory=$true)][string]$Company,
    [Parameter(Mandatory=$true)][string]$Segment,
    [string]$ContactName,
    [string]$ContactRole,
    [string]$Depth,
    [string]$EvidenceRoot,
    [string]$GateEvidenceDir,
    [string]$PilotPdfEvidence,
    [string]$CtaSlot1,
    [string]$CtaSlot2,
    [string]$CtaTz
  )

  $stamp = Now-Stamp
  $evDir = Join-Path $EvidenceRoot ("outreach_" + $stamp)
  Ensure-Dir $evDir

  $companySlug = Slugify $Company
  $mdOut = Join-Path $evDir ("outreach_" + $companySlug + ".md")
  $jsonOut = Join-Path $evDir ("outreach_" + $companySlug + ".json")
  $metaOut = Join-Path $evDir "meta.json"

  $prof = Segment-Profile $Segment
  $subjects = Build-Subjects $Company $prof
  $ctaLine = Build-Cta $CtaSlot1 $CtaSlot2 $CtaTz

  $emailShort = Build-EmailShort $Company $prof $ContactName $ContactRole $ctaLine
  $emailFull  = Build-EmailFull  $Company $prof $ContactName $ContactRole $ctaLine

  $callOpener = Build-CallOpener $Company $prof
  $callScript = Build-CallScript $Company
  $checklist  = Build-Checklist

  $doc = New-Object System.Collections.Generic.List[string]
  $doc.Add("# FoxProFlow • Security Lane • Outreach Draft") | Out-Null
  $doc.Add(("ts: {0}" -f (Now-Iso))) | Out-Null
  $doc.Add(("company: {0}" -f $Company.Trim())) | Out-Null
  $doc.Add(("segment: {0} ({1})" -f $Segment, $prof.label)) | Out-Null
  if ($ContactName) { $doc.Add(("contact_name: {0}" -f $ContactName.Trim())) | Out-Null }
  if ($ContactRole) { $doc.Add(("contact_role: {0}" -f $ContactRole.Trim())) | Out-Null }
  $doc.Add("") | Out-Null

  $doc.Add("## Subjects") | Out-Null
  foreach ($s in $subjects) { $doc.Add(("* " + $s)) | Out-Null }
  $doc.Add("") | Out-Null

  $doc.Add("## Email (short)") | Out-Null
  $doc.Add("") | Out-Null
  $doc.Add($emailShort) | Out-Null
  $doc.Add("") | Out-Null

  if ($Depth -eq "full") {
    $doc.Add("## Email (enterprise/full)") | Out-Null
    $doc.Add("") | Out-Null
    $doc.Add($emailFull) | Out-Null
    $doc.Add("") | Out-Null
  }

  $doc.Add("## Call opener (20 sec)") | Out-Null
  $doc.Add($callOpener) | Out-Null
  $doc.Add("") | Out-Null

  $doc.Add("## Call script (5 min)") | Out-Null
  $doc.Add($callScript) | Out-Null
  $doc.Add("") | Out-Null

  $doc.Add("## First-call checklist") | Out-Null
  $doc.Add($checklist) | Out-Null
  $doc.Add("") | Out-Null

  ($doc.ToArray() -join [Environment]::NewLine) | Set-Content -LiteralPath $mdOut -Encoding utf8NoBOM

  # JSON keeps internal references
  $payload = [pscustomobject]@{
    ts = Now-Iso
    company = $Company
    company_slug = $companySlug
    segment = $Segment
    segment_label = $prof.label
    contact_name = $ContactName
    contact_role = $ContactRole
    depth = $Depth
    evidence_dir = $evDir
    outputs = [pscustomobject]@{ markdown = $mdOut; json = $jsonOut; meta = $metaOut }
    subjects = $subjects
    email_short = $emailShort
    email_full = $emailFull
    call_opener = $callOpener
    call_script = $callScript
    checklist = $checklist
    references = [pscustomobject]@{
      gate_evidence_dir = $GateEvidenceDir
      pilot_pdf = $PilotPdfEvidence
    }
    cta = [pscustomobject]@{
      tz = $CtaTz
      slot1 = $CtaSlot1
      slot2 = $CtaSlot2
    }
  }

  ($payload | ConvertTo-Json -Depth 64) | Set-Content -LiteralPath $jsonOut -Encoding utf8NoBOM
  ($payload | ConvertTo-Json -Depth 16) | Set-Content -LiteralPath $metaOut -Encoding utf8NoBOM

  return [pscustomobject]@{ evidence_dir = $evDir; md = $mdOut; json = $jsonOut }
}

# --- main ---
$root = Repo-Root
if ([string]::IsNullOrWhiteSpace($EvidenceRoot)) {
  $EvidenceRoot = Join-Path $root "ops\_local\evidence"
}
Ensure-Dir $EvidenceRoot

$results = @()

if (-not [string]::IsNullOrWhiteSpace($BatchCsv)) {
  $csvPath = $BatchCsv
  if (-not (Test-Path -LiteralPath $csvPath)) { throw "BatchCsv not found: $csvPath" }

  $rows = Import-Csv -LiteralPath $csvPath
  foreach ($r in $rows) {
    $c = [string]$r.company
    if ([string]::IsNullOrWhiteSpace($c)) { continue }

    $seg = [string]$r.segment
    if ([string]::IsNullOrWhiteSpace($seg)) { $seg = "custom" }

    $dn = [string]$r.depth
    if ([string]::IsNullOrWhiteSpace($dn)) { $dn = "short" }

    $res = Compose-One -Company $c -Segment $seg -ContactName ([string]$r.contact_name) -ContactRole ([string]$r.contact_role) `
      -Depth $dn -EvidenceRoot $EvidenceRoot -GateEvidenceDir $GateEvidenceDir -PilotPdfEvidence $PilotPdfEvidence `
      -CtaSlot1 $CtaSlot1 -CtaSlot2 $CtaSlot2 -CtaTz $CtaTz
    $results += $res
  }
} else {
  if ([string]::IsNullOrWhiteSpace($Company)) { throw "Provide -Company (single mode) or -BatchCsv (batch mode)." }
  $results += (Compose-One -Company $Company -Segment $Segment -ContactName $ContactName -ContactRole $ContactRole `
    -Depth $Depth -EvidenceRoot $EvidenceRoot -GateEvidenceDir $GateEvidenceDir -PilotPdfEvidence $PilotPdfEvidence `
    -CtaSlot1 $CtaSlot1 -CtaSlot2 $CtaSlot2 -CtaTz $CtaTz)
}

$last = $results | Select-Object -Last 1
Write-Host "[OUTREACH COMPOSE] OK" -ForegroundColor Green
Write-Host ("evidence: {0}" -f $last.evidence_dir)
Write-Host ("md: {0}" -f $last.md)

if ($OpenFolder -and $last.evidence_dir) {
  explorer.exe $last.evidence_dir | Out-Null
}

