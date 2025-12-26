#requires -Version 7.0
<#
FoxProFlow • SQL • Verify M0 runner
file: scripts/sql/verify/run_verify_m0.ps1

Purpose:
  - Runs a verify SQL script against Postgres container (compose autodetect or explicit).
  - Streams SQL into `psql` running inside container.
  - IMPORTANT: Expands psql meta-includes (\i, \ir) on host side before streaming,
    because `psql` runs inside container and cannot access host filesystem paths.

Notes on include expansion:
  - \ir <path> is resolved relative to the directory of the including file (psql semantics).
  - \i  <path> is resolved relative to the current working directory (psql semantics).
  - Cycles are detected (include recursion stack).

DB selection (Gate/FreshDB):
  - By default PgDb = "foxproflow"
  - If env:FF_TEMP_DB is set (FreshDB drill), it overrides PgDb ALWAYS,
    even if -PgDb was passed explicitly (unless IgnoreTempDbEnv switch or env:FF_VERIFY_IGNORE_FF_TEMP_DB=true).
  - If env:FF_PG_DB is set, it overrides PgDb when FF_TEMP_DB is not set.
#>

[CmdletBinding()]
param(
  # Explicit container name overrides all auto-detection
  [string]$PgContainer = "",

  # Prefer this compose project (label com.docker.compose.project).
  # If not provided, uses $env:FF_COMPOSE_PROJECT, otherwise falls back to "foxproflow-mvp20".
  [string]$PreferProject = "",

  # If you explicitly requested PreferProject and it is NOT found:
  # - default behavior is to FAIL (safer)
  # - set this switch to allow fallback to the only/first candidate
  [switch]$AllowProjectMismatch,

  [string]$PgUser = "admin",
  [string]$PgDb = "foxproflow",

  [string]$VerifyFile = (Join-Path -Path (Split-Path -Parent $PSCommandPath) -ChildPath "verify_m0.sql"),

  # Disable host-side expansion of \i/\ir (rarely needed; mainly for debugging)
  [switch]$NoExpandIncludes,

  # Local override: do NOT allow FF_TEMP_DB to override PgDb (rare)
  [switch]$IgnoreTempDbEnv,

  # Optional: print env diagnostics (FF_TEMP_DB/FF_PG_DB/ignore flag)
  [switch]$PrintEnv
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --- preflight ---
$null = Get-Command docker -ErrorAction Stop

function _GetEnv {
  param([Parameter(Mandatory=$true)][string]$Name)
  try {
    return [Environment]::GetEnvironmentVariable($Name, "Process")
  } catch {
    return $null
  }
}

function _EnvBool {
  param([Parameter(Mandatory=$true)][string]$Name, [bool]$Default=$false)
  $v = _GetEnv -Name $Name
  if (-not $v) { return $Default }
  $s = $v.ToString().Trim().ToLowerInvariant()
  return $s -in @("1","true","yes","y","on","enable","enabled")
}

function Normalize-PathSeparators {
  param([Parameter(Mandatory=$true)][string]$Path)
  return ($Path -replace '[\\/]', [System.IO.Path]::DirectorySeparatorChar)
}

function Resolve-NormalizedPath {
  param([Parameter(Mandatory=$true)][string]$Path)
  $p = Normalize-PathSeparators -Path $Path
  return (Resolve-Path -LiteralPath $p -ErrorAction Stop).Path
}

function Get-ExpandedPsqlLines {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory=$true)]
    [string]$Path,

    # recursion stack (cycle detection). key: fully resolved path, value: $true
    [hashtable]$IncludeStack = $null
  )

  if (-not $IncludeStack) { $IncludeStack = @{} }

  if (-not (Test-Path -LiteralPath (Normalize-PathSeparators -Path $Path) -PathType Leaf)) {
    throw "Verify file not found: $Path"
  }

  $full = Resolve-NormalizedPath -Path $Path

  if ($IncludeStack.ContainsKey($full)) {
    $chain = ($IncludeStack.Keys | Sort-Object) -join " -> "
    throw "VERIFY include cycle detected at: $full. Include stack contains: $chain"
  }

  $IncludeStack[$full] = $true
  $baseDir = Split-Path -Parent $full

  $out = New-Object System.Collections.Generic.List[string]

  foreach ($line in (Get-Content -LiteralPath $full)) {
    $t = $line.TrimStart()

    # Expand psql meta includes on host side: \i / \ir
    if ($t -match '^(\\i)(r)?\s+(.+)$') {
      $isRelative = [bool]$Matches[2]      # 'r' present => \ir
      $argRaw = $Matches[3].Trim()

      # strip optional quotes
      if (
        ($argRaw.StartsWith("'") -and $argRaw.EndsWith("'") -and $argRaw.Length -ge 2) -or
        ($argRaw.StartsWith('"') -and $argRaw.EndsWith('"') -and $argRaw.Length -ge 2)
      ) {
        $argRaw = $argRaw.Substring(1, $argRaw.Length - 2)
      }

      $arg = Normalize-PathSeparators -Path $argRaw

      # psql semantics:
      #  - \ir: relative to directory of including file
      #  - \i : relative to current working directory
      $anchorDir = if ($isRelative) { $baseDir } else { (Get-Location).Path }

      $incPath = if ([System.IO.Path]::IsPathRooted($arg)) {
        $arg
      } else {
        Join-Path -Path $anchorDir -ChildPath $arg
      }

      if (-not (Test-Path -LiteralPath $incPath -PathType Leaf)) {
        throw "VERIFY include missing: '$argRaw' (resolved: '$incPath') referenced from '$full'"
      }

      Write-Verbose ("Expanding include from '{0}': {1} -> {2}" -f $full, ($isRelative ? "\ir" : "\i"), $incPath)

      $out.Add("-- BEGIN INCLUDE: $argRaw")
      $out.AddRange((Get-ExpandedPsqlLines -Path $incPath -IncludeStack $IncludeStack))
      $out.Add("-- END INCLUDE: $argRaw")
      continue
    }

    $out.Add($line)
  }

  $null = $IncludeStack.Remove($full)
  return ,$out.ToArray()
}

function Get-ExpandedPsqlText {
  [CmdletBinding()]
  param([Parameter(Mandatory=$true)][string]$Path)

  $lines = Get-ExpandedPsqlLines -Path $Path
  return ($lines -join "`n")
}

# -----------------------------
# Resolve PreferProject logic
# -----------------------------
$preferExplicit = $PSBoundParameters.ContainsKey('PreferProject')

if (-not $PreferProject -or $PreferProject.Trim() -eq "") {
  $PreferProject = _GetEnv -Name "FF_COMPOSE_PROJECT"
}
if (-not $PreferProject -or $PreferProject.Trim() -eq "") {
  $PreferProject = "foxproflow-mvp20"
}

# -----------------------------
# Resolve + normalize VerifyFile
# -----------------------------
$VerifyFile = Resolve-NormalizedPath -Path $VerifyFile

# -----------------------------
# PgDb selection (IMPORTANT)
# -----------------------------
$pgDbWasBound = $PSBoundParameters.ContainsKey('PgDb')
$pgDbSource = if ($pgDbWasBound) { "param" } else { "default" }

$ignoreTemp = $IgnoreTempDbEnv.IsPresent -or (_EnvBool -Name "FF_VERIFY_IGNORE_FF_TEMP_DB" -Default:$false)

$ffTempDb = _GetEnv -Name "FF_TEMP_DB"
$ffPgDb   = _GetEnv -Name "FF_PG_DB"

if ($PrintEnv.IsPresent) {
  Write-Host "Env diagnostics:"
  Write-Host "  FF_TEMP_DB = $ffTempDb"
  Write-Host "  FF_PG_DB   = $ffPgDb"
  Write-Host "  IgnoreTemp = $ignoreTemp"
}

if (-not $ignoreTemp -and $ffTempDb -and $ffTempDb.Trim() -ne "") {
  $old = $PgDb
  $PgDb = $ffTempDb.Trim()
  $pgDbSource = if ($pgDbWasBound) { "env:FF_TEMP_DB(overrode param '$old')" } else { "env:FF_TEMP_DB" }
}
elseif ($ffPgDb -and $ffPgDb.Trim() -ne "") {
  $old = $PgDb
  $PgDb = $ffPgDb.Trim()
  $pgDbSource = if ($pgDbWasBound) { "env:FF_PG_DB(overrode param '$old')" } else { "env:FF_PG_DB" }
}

# -----------------------------
# Load verify text (with include expansion by default)
# -----------------------------
$verifyText =
  if ($NoExpandIncludes) {
    Get-Content -LiteralPath $VerifyFile -Raw
  } else {
    Get-ExpandedPsqlText -Path $VerifyFile
  }

if (-not $verifyText -or $verifyText.Trim().Length -eq 0) {
  throw "Verify file is empty (after expansion=$(-not $NoExpandIncludes)): $VerifyFile"
}

function Get-ComposePostgresCandidates {
  # Returns objects: @{ Name=...; Project=... }
  $rows = @(
    docker ps --filter "label=com.docker.compose.service=postgres" --format "{{.Names}}|{{.Label ""com.docker.compose.project""}}"
  ) | Where-Object { $_ -and $_.Trim() }

  $parsed = foreach ($r in $rows) {
    $parts = $r -split '\|', 2
    [pscustomobject]@{
      Name    = $parts[0]
      Project = if ($parts.Count -gt 1) { $parts[1] } else { "" }
    }
  }

  return @($parsed)
}

function Get-PostgresContainerName {
  param(
    [string]$PreferProjectName,
    [bool]$PreferWasExplicit,
    [bool]$AllowMismatch
  )

  $candidates = Get-ComposePostgresCandidates
  if ($candidates.Count -gt 0) {
    Write-Verbose ("Compose postgres candidates: " + ($candidates | ForEach-Object { "$($_.Name)[$($_.Project)]" } | Sort-Object | Out-String).Trim())

    $exact = $candidates | Where-Object { $_.Project -eq $PreferProjectName } | Select-Object -First 1
    if ($exact) { return $exact.Name }

    if ($PreferWasExplicit -and -not $AllowMismatch) {
      $names = $candidates | ForEach-Object { "$($_.Name)[$($_.Project)]" } | Sort-Object
      throw ("PreferProject='$PreferProjectName' was requested, but no matching compose postgres container found. " +
             "Candidates: " + ($names -join ", ") + ". " +
             "Start the correct stack, or pass -PgContainer explicitly, or add -AllowProjectMismatch to override.")
    }

    if ($candidates.Count -eq 1) { return $candidates[0].Name }

    $names2 = $candidates | ForEach-Object { "$($_.Name)[$($_.Project)]" } | Sort-Object
    Write-Warning ("Multiple compose postgres containers found; none match PreferProject='$PreferProjectName'. " +
                   "Picking the first. Candidates: " + ($names2 -join ", "))
    return ($candidates | Select-Object -First 1).Name
  }

  if ($PreferWasExplicit -and -not $AllowMismatch) {
    throw ("PreferProject='$PreferProjectName' was requested, but no compose-labeled postgres containers were found. " +
           "Cannot safely choose a target. Start the stack or pass -PgContainer explicitly (or add -AllowProjectMismatch).")
  }

  $byImage = @(
    docker ps --filter "ancestor=postgres" --format "{{.Names}}"
  ) | Where-Object { $_ -and $_.Trim() } | Select-Object -Unique

  $byImage = @($byImage)
  if ($byImage.Count -eq 0) {
    throw "Postgres container not found. Is the stack up? (docker ps)"
  }

  if ($byImage.Count -gt 1) {
    Write-Warning ("Multiple postgres-image containers found (no compose labels). Picking the first: " + ($byImage -join ", "))
  }

  return $byImage[0]
}

function Assert-ContainerRunning {
  param([string]$Name)

  $running = docker inspect -f "{{.State.Running}}" $Name 2>$null
  if (-not $running) {
    throw "Container not found or inspect failed: $Name"
  }
  if ($running.Trim().ToLowerInvariant() -ne "true") {
    throw "Container is not running: $Name"
  }
}

# --- choose container ---
if (-not $PgContainer -or $PgContainer.Trim() -eq "") {
  $PgContainer = Get-PostgresContainerName -PreferProjectName $PreferProject -PreferWasExplicit:$preferExplicit -AllowMismatch:$AllowProjectMismatch.IsPresent
}

Assert-ContainerRunning -Name $PgContainer

Write-Host "Running VERIFY M0..."
Write-Host "  PgContainer: $PgContainer"
Write-Host "  PreferProject: $PreferProject"
Write-Host "  PgUser:      $PgUser"
Write-Host "  PgDb:        $PgDb"
Write-Host "  PgDbSource:  $pgDbSource"
Write-Host "  VerifyFile:  $VerifyFile"
Write-Host "  ExpandIncludes: $(-not $NoExpandIncludes)"

# -X: do not read ~/.psqlrc (determinism)
$verifyText | docker exec -i $PgContainer psql -X -U $PgUser -d $PgDb -v ON_ERROR_STOP=1

if ($LASTEXITCODE -ne 0) {
  throw "VERIFY M0 FAIL (psql/docker exitcode=$LASTEXITCODE)"
}

Write-Host "VERIFY M0 PASS"
