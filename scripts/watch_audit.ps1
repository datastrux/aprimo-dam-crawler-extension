# Watch Audit Pipeline Progress
# Monitors the persistent status JSON file and displays live progress.
# Run in a separate terminal while audit pipeline is running.
#
# Usage:
#   .\scripts\watch_audit.ps1
#   .\scripts\watch_audit.ps1 -StatusFile "custom_status.json"

param(
    [string]$StatusFile = "assets\audit\pipeline_status.json"
)

$StatusPath = Join-Path $PSScriptRoot "..\$StatusFile"

if (-not (Test-Path $StatusPath)) {
    Write-Host "⚠️  Status file not found: $StatusPath" -ForegroundColor Yellow
    Write-Host "   Start the audit pipeline first:" -ForegroundColor Gray
    Write-Host "   python scripts\run_audit_standalone.py" -ForegroundColor Gray
    exit 1
}

Write-Host "🔍 Monitoring Audit Pipeline" -ForegroundColor Cyan
Write-Host "   Status file: $StatusPath" -ForegroundColor Gray
Write-Host "   Press Ctrl+C to stop watching`n" -ForegroundColor Gray

$lastUpdate = $null

while ($true) {
    try {
        $status = Get-Content $StatusPath -Raw | ConvertFrom-Json
        
        # Only refresh if status changed
        $currentUpdate = $status.updated_at
        if ($currentUpdate -eq $lastUpdate) {
            Start-Sleep -Seconds 2
            continue
        }
        $lastUpdate = $currentUpdate
        
        Clear-Host
        
        # Header
        Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
        Write-Host " 🔍 AUDIT PIPELINE MONITOR" -ForegroundColor Cyan
        Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
        Write-Host ""
        
        # Overall status
        $statusColor = switch ($status.status) {
            "running"   { "Yellow" }
            "completed" { "Green" }
            "error"     { "Red" }
            default     { "White" }
        }
        
        Write-Host "Status:   " -NoNewline
        Write-Host $status.status.ToUpper() -ForegroundColor $statusColor
        
        if ($status.current_stage) {
            Write-Host "Stage:    $($status.current_stage)" -ForegroundColor White
        }
        
        Write-Host "Progress: " -NoNewline
        $pct = [math]::Round($status.pipeline_percent, 1)
        Write-Host "$pct% " -NoNewline -ForegroundColor Yellow
        Write-Host "($($status.current_stage_num)/$($status.total_stages) stages)" -ForegroundColor Gray
        
        # Progress bar
        $barWidth = 50
        $filled = [math]::Floor(($pct / 100) * $barWidth)
        $empty = $barWidth - $filled
        $bar = ("█" * $filled) + ("░" * $empty)
        Write-Host "          [$bar]" -ForegroundColor Yellow
        
        Write-Host ""
        Write-Host "───────────────────────────────────────────────────────────" -ForegroundColor DarkGray
        Write-Host " STAGES" -ForegroundColor Cyan
        Write-Host "───────────────────────────────────────────────────────────" -ForegroundColor DarkGray
        
        # Stage list
        foreach ($stageProp in $status.stages.PSObject.Properties) {
            $stageName = $stageProp.Name
            $stageData = $stageProp.Value
            $stageStatus = $stageData.status
            
            $icon = switch ($stageStatus) {
                "completed" { "✅" }
                "running"   { "⏳" }
                "error"     { "❌" }
                default     { "○" }
            }
            
            $color = switch ($stageStatus) {
                "completed" { "Green" }
                "running"   { "Yellow" }
                "error"     { "Red" }
                default     { "DarkGray" }
            }
            
            Write-Host " $icon " -NoNewline -ForegroundColor $color
            Write-Host $stageName.PadRight(40) -NoNewline -ForegroundColor White
            Write-Host $stageStatus.ToUpper().PadRight(12) -NoNewline -ForegroundColor $color
            
            # Show duration if completed
            if ($stageData.duration_seconds) {
                $duration = [math]::Round($stageData.duration_seconds, 1)
                Write-Host "${duration}s" -ForegroundColor Gray
            }
            else {
                Write-Host ""
            }
            
            # Show progress for running stage
            if ($stageStatus -eq "running" -and $stageData.last_progress) {
                $prog = $stageData.last_progress
                
                if ($prog.urls_completed -and $prog.urls_total) {
                    $stagePct = [math]::Round(($prog.urls_completed / $prog.urls_total) * 100, 1)
                    Write-Host "    └─ URLs: $($prog.urls_completed)/$($prog.urls_total) ($stagePct%)" -ForegroundColor DarkYellow
                }
                
                if ($prog.images_detected) {
                    $remaining = if ($prog.images_remaining) { " ($($prog.images_remaining) pending)" } else { "" }
                    Write-Host "    └─ Images: $($prog.images_detected) detected$remaining" -ForegroundColor DarkYellow
                }
            }
        }
        
        Write-Host ""
        Write-Host "───────────────────────────────────────────────────────────" -ForegroundColor DarkGray
        
        # Timestamps
        if ($status.started_at) {
            $startTime = [DateTimeOffset]::FromUnixTimeSeconds($status.started_at).LocalDateTime
            Write-Host "Started:  $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Gray
        }
        
        if ($status.completed_at) {
            $endTime = [DateTimeOffset]::FromUnixTimeSeconds($status.completed_at).LocalDateTime
            $totalDuration = $status.completed_at - $status.started_at
            Write-Host "Finished: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Gray
            Write-Host "Duration: $([math]::Round($totalDuration, 1))s" -ForegroundColor Gray
        }
        elseif ($status.started_at) {
            $elapsed = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $status.started_at
            Write-Host "Elapsed:  $([math]::Round($elapsed, 1))s" -ForegroundColor Gray
        }
        
        $updateTime = [DateTimeOffset]::FromUnixTimeSeconds($status.updated_at).LocalDateTime
        Write-Host "Updated:  $($updateTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor DarkGray
        
        Write-Host ""
        
    }
    catch {
        Write-Host "ERROR: Failed to read status file: $_" -ForegroundColor Red
    }
    
    Start-Sleep -Seconds 2
}
