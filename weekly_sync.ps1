#!/usr/bin/env pwsh
# weekly_sync.ps1 - Weekly sync QHI project to Git
# Run: Every Monday 08:00

$PROJECT_DIR = "E:\qhi_processor"
$LOG_DIR = "E:\Temp\bug"

# Create log file
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logFile = Join-Path $LOG_DIR "weekly_sync_$timestamp.log"
$null = New-Item -ItemType Directory -Path $LOG_DIR -Force -ErrorAction SilentlyContinue

# Write log helper
function Write-Log($msg, $level="INFO") {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$level] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Write-Log "============================================================"
Write-Log "QHI Project Weekly Sync"
Write-Log "Project: $PROJECT_DIR"
Write-Log "============================================================"

# Change to project directory
Set-Location $PROJECT_DIR

# 1. Pull remote changes
Write-Log "Step 1: Pull remote changes..."
git pull origin main 2>&1 | ForEach-Object { Write-Log "  $_" }

# 2. Check status
Write-Log "Step 2: Check file status..."
$status = git status --porcelain
if ($status) {
    Write-Log "Found $($status.Count) file(s) changed"
} else {
    Write-Log "No files changed, nothing to commit"
}

# 3. Stage all changes
Write-Log "Step 3: Stage all changes..."
git add -A

# 4. Create commit
$commitTime = Get-Date -Format "yyyy-MM-dd HH:mm"
$commitMsg = "[Auto Sync] $commitTime`n`nWeekly sync - Automated commit by weekly_sync.ps1"

# Check if there are staged changes
$staged = git diff --cached --name-only
if ($staged) {
    Write-Log "Step 4: Create commit..."
    git commit -m $commitMsg
    if ($LASTEXITCODE -eq 0) {
        $hash = git rev-parse --short HEAD
        Write-Log "Commit created: $hash" "SUCCESS"
        
        # 5. Push to remote
        Write-Log "Step 5: Push to remote..."
        git push origin main 2>&1 | ForEach-Object { Write-Log "  $_" }
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Push successful!" "SUCCESS"
        } else {
            Write-Log "Push failed" "ERROR"
        }
    }
} else {
    Write-Log "No staged changes, skip commit" "WARN"
}

# Show recent commits
Write-Log "============================================================"
Write-Log "Recent commits:"
git log --oneline -n 5 | ForEach-Object { Write-Log "  $_" }

Write-Log "============================================================"
Write-Log "Sync complete. Log: $logFile" "SUCCESS"
Write-Host ""