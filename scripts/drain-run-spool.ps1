<#
.SYNOPSIS
    Drains undelivered model-run telemetry from the run spool to vaultwares-api.

.DESCRIPTION
    The recorder POSTs directly and only writes to the spool when that fails, so
    anything here is a batch the API never received. Without this script those
    files sit on disk forever -- which is exactly what happened between
    2026-08-10 and the day this was written.

    Mirrors agent-ledger/scripts/drain-spool.ps1: one JSON batch object per
    line, POST each line, rename the file *.sent once every line in it
    succeeded. A partial failure leaves the file for the next run, so ingest
    must be idempotent -- it is: runs dedupe on run_id and request_id, and
    rollups overwrite their (hour, host, dimensions) cell.

    Runs and rollups go to different endpoints. The filename prefix decides:
    `rollups-YYYY-MM-DD.jsonl` is the hourly grain, anything else is raw runs.
#>
[CmdletBinding()]
param(
    [string]$SpoolDir = $env:VW_RUNS_SPOOL_DIR,
    [string]$ApiUrl,
    [string]$ApiKey,
    [int]$PruneSentDays = 14,
    [switch]$WhatIfOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $SpoolDir) { $SpoolDir = "D:\AiHistory\run-spool" }
if (-not $ApiUrl) {
    $ApiUrl = $env:VW_API_URL
    if (-not $ApiUrl) { $ApiUrl = [Environment]::GetEnvironmentVariable("VW_API_URL", "Machine") }
    if (-not $ApiUrl) { $ApiUrl = "https://api.vaultwares.ca" }
}
if (-not $ApiKey) {
    $ApiKey = $env:VW_TELEMETRY_API_KEY
    if (-not $ApiKey) { $ApiKey = [Environment]::GetEnvironmentVariable("VW_TELEMETRY_API_KEY", "Machine") }
    if (-not $ApiKey) { $ApiKey = [Environment]::GetEnvironmentVariable("VW_TELEMETRY_API_KEY", "User") }
}

$LogDir = Join-Path (Split-Path -Parent $PSScriptRoot) "_logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogPath = Join-Path $LogDir ("run-spool-drain-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-DrainLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "ddd, dd MMM yyyy HH:mm"), $Message
    Add-Content -Path $LogPath -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
    Write-Host $line
}

if (-not (Test-Path $SpoolDir)) {
    Write-DrainLog "Spool directory not found: $SpoolDir - nothing to drain."
    exit 0
}

$files = @(Get-ChildItem -Path $SpoolDir -Filter "*.jsonl" -File | Sort-Object Name)
if ($files.Count -eq 0) {
    Write-DrainLog "No undelivered spool files."
} else {
    Write-DrainLog "Found $($files.Count) spool file(s). API: $ApiUrl"
}

$totalSent = 0
$totalErrors = 0

foreach ($file in $files) {
    # The prefix decides the endpoint; the two grains are not interchangeable.
    $isRollup = $file.Name -like "rollups-*"
    $endpoint = if ($isRollup) { "$ApiUrl/api/telemetry/ai-runs/rollups/batches" }
                else { "$ApiUrl/api/telemetry/ai-runs/batches" }

    $lines = @(Get-Content -Path $file.FullName -Encoding UTF8 | Where-Object { $_.Trim() })
    Write-DrainLog "  $($file.Name): $($lines.Count) batch(es) -> $(if ($isRollup) {'rollups'} else {'runs'})"

    if ($WhatIfOnly) { continue }

    $sent = 0
    $failed = 0
    foreach ($line in $lines) {
        $headers = @{ "Content-Type" = "application/json"; "User-Agent" = "vw-run-spool-drain/1" }
        if ($ApiKey) { $headers["x-api-key"] = $ApiKey }
        try {
            Invoke-RestMethod -Uri $endpoint -Method Post -Body $line.Trim() `
                -Headers $headers -ContentType "application/json" -TimeoutSec 20 -ErrorAction Stop | Out-Null
            $sent++; $totalSent++
        }
        catch {
            $failed++; $totalErrors++
            $status = ""
            try { $status = $_.Exception.Response.StatusCode.value__ } catch {}
            Write-DrainLog "    ERROR status=$status $($_.Exception.Message)"
            # Stop on the first failure in a file: the API is probably down, and
            # hammering it with the rest of the backlog helps nobody.
            break
        }
    }

    if ($failed -eq 0) {
        Move-Item -Path $file.FullName -Destination "$($file.FullName).sent" -Force
        Write-DrainLog "    sent $sent/$($lines.Count); renamed to $($file.Name).sent"
    } else {
        Write-DrainLog "    partial: $sent sent, $failed failed. File kept for retry."
    }
}

# Delivered files are kept briefly as evidence, then removed so the spool does
# not grow without bound.
if ($PruneSentDays -gt 0) {
    $cutoff = (Get-Date).AddDays(-$PruneSentDays)
    $stale = @(Get-ChildItem -Path $SpoolDir -Filter "*.sent" -File |
               Where-Object { $_.LastWriteTime -lt $cutoff })
    if ($stale.Count -gt 0) {
        $stale | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-DrainLog "Pruned $($stale.Count) delivered file(s) older than $PruneSentDays days."
    }
}

Write-DrainLog "Done. sent=$totalSent errors=$totalErrors"
exit $(if ($totalErrors -gt 0) { 1 } else { 0 })
