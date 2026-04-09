<#
.SYNOPSIS
    Signal Forge — Git-Tracked File Backup

.DESCRIPTION
    Backs up every file tracked by Git into a timestamped ZIP archive.
    Archives are written to C:\dev\Signal_Forge\Backups.
    Each run appends a log entry (branch, commit, dirty-file list) to
    Backups\backup_log.txt and prunes the oldest archives when the
    count exceeds -MaxKeep.

    Uncommitted edits to tracked files ARE included — the backup
    captures the current working-tree state, not just the last commit.

.PARAMETER MaxKeep
    How many ZIP archives to retain before pruning the oldest.
    Default: 10.

.PARAMETER Message
    Optional free-text note written to the log entry (e.g. "before refactor").

.PARAMETER DryRun
    Lists every file that would be backed up without creating an archive.

.EXAMPLE
    .\backup.ps1
    .\backup.ps1 -Message "before datetime refactor"
    .\backup.ps1 -MaxKeep 20
    .\backup.ps1 -DryRun
#>

param(
    [int]   $MaxKeep = 10,
    [string]$Message = "",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Paths ─────────────────────────────────────────────────────────────────────
$Root      = $PSScriptRoot
$BackupDir = Join-Path $Root "Backups"
$LogFile   = Join-Path $BackupDir "backup_log.txt"

# ── Require Git ───────────────────────────────────────────────────────────────
Push-Location $Root
try {
    git rev-parse --is-inside-work-tree 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Not a Git repository: $Root"; return
    }
} finally { Pop-Location }

# ── Git metadata ──────────────────────────────────────────────────────────────
Push-Location $Root
$Branch      = git rev-parse --abbrev-ref HEAD
$CommitHash  = git rev-parse --short HEAD
$CommitMsg   = git log -1 --pretty=format:"%s"
$DirtyLines  = @(git status --short)
Pop-Location

# ── Collect git-tracked files ─────────────────────────────────────────────────
Push-Location $Root
$TrackedPaths = @(git ls-files)
Pop-Location

$FilesToBackup = $TrackedPaths | Where-Object { $_ -ne "" } | ForEach-Object {
    $full = Join-Path $Root ($_ -replace '/', '\')
    if (Test-Path $full -PathType Leaf) {
        [PSCustomObject]@{ Relative = $_; Full = $full }
    }
} | Where-Object { $_ -ne $null }

$TotalFiles = $FilesToBackup.Count

# ── Timestamp & archive name ──────────────────────────────────────────────────
$Now        = Get-Date
$Stamp      = $Now.ToString("yyyy-MM-dd_HH-mm-ss")
$SafeBranch = $Branch -replace '[^a-zA-Z0-9_-]', '-'
$ZipName    = "signal_forge_${Stamp}_${SafeBranch}_${CommitHash}.zip"
$ZipPath    = Join-Path $BackupDir $ZipName

# ── Dry run ───────────────────────────────────────────────────────────────────
if ($DryRun) {
    Write-Host ""
    Write-Host "=== DRY RUN — Signal Forge Backup ===" -ForegroundColor Yellow
    Write-Host "Branch  : $Branch  ($CommitHash)"
    Write-Host "Commit  : $CommitMsg"
    Write-Host "Archive : $ZipPath"
    Write-Host "Files   : $TotalFiles git-tracked files"
    Write-Host ""
    $FilesToBackup | ForEach-Object { Write-Host "  $($_.Relative)" }
    Write-Host ""
    return
}

# ── Ensure Backups directory ──────────────────────────────────────────────────
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
    Write-Host "Created : $BackupDir" -ForegroundColor Green
}

# ── Build ZIP ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Signal Forge Backup ===" -ForegroundColor Cyan
Write-Host "Branch  : $Branch  ($CommitHash)"
Write-Host "Commit  : $CommitMsg"
Write-Host "Files   : $TotalFiles git-tracked files"
Write-Host "Archive : $ZipName"
Write-Host ""

Add-Type -AssemblyName System.IO.Compression.FileSystem
$Zip     = [System.IO.Compression.ZipFile]::Open($ZipPath, 'Create')
$Skipped = 0
foreach ($f in $FilesToBackup) {
    try {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $Zip, $f.Full, $f.Relative,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    } catch {
        Write-Warning "Skipped : $($f.Relative) — $_"
        $Skipped++
    }
}
$Zip.Dispose()

$ZipSizeMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 3)

# ── Prune oldest archives ─────────────────────────────────────────────────────
$AllZips = @(Get-ChildItem -Path $BackupDir -Filter "signal_forge_*.zip" |
           Sort-Object Name)
if ($AllZips.Count -gt $MaxKeep) {
    $ToDelete = $AllZips | Select-Object -First ($AllZips.Count - $MaxKeep)
    foreach ($z in $ToDelete) {
        Remove-Item $z.FullName -Force
        Write-Host "Pruned  : $($z.Name)" -ForegroundColor DarkGray
    }
}

# ── Append log entry ──────────────────────────────────────────────────────────
$Divider = "=" * 72
if (-not (Test-Path $LogFile)) {
    @(
        "Signal Forge — Backup Log",
        $Divider
    ) | Set-Content $LogFile -Encoding UTF8
}

$LogEntry = [System.Collections.Generic.List[string]]::new()
$LogEntry.Add("")
$LogEntry.Add($Divider)
$LogEntry.Add("Date    : $($Now.ToString('yyyy-MM-dd HH:mm:ss'))")
$LogEntry.Add("Archive : $ZipName")
$LogEntry.Add("Size    : $ZipSizeMB MB   |   Files : $TotalFiles   |   Skipped : $Skipped")
$LogEntry.Add("Branch  : $Branch")
$LogEntry.Add("Commit  : $CommitHash — $CommitMsg")

if ($Message) {
    $LogEntry.Add("Note    : $Message")
}

if ($DirtyLines.Count -gt 0) {
    $LogEntry.Add("Dirty   : $($DirtyLines.Count) uncommitted change(s)")
    foreach ($line in $DirtyLines) { $LogEntry.Add("  $line") }
} else {
    $LogEntry.Add("Dirty   : (clean — working tree matches HEAD)")
}

$LogEntry | Add-Content $LogFile -Encoding UTF8

# ── Console summary ───────────────────────────────────────────────────────────
Write-Host "Archive : $ZipPath" -ForegroundColor Green
Write-Host "Size    : $ZipSizeMB MB"
Write-Host "Files   : $TotalFiles  (skipped: $Skipped)"
Write-Host "Branch  : $Branch  @ $CommitHash"

if ($DirtyLines.Count -gt 0) {
    Write-Host "Dirty   : $($DirtyLines.Count) uncommitted change(s) captured" -ForegroundColor Yellow
    $DirtyLines | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkYellow }
} else {
    Write-Host "Dirty   : clean" -ForegroundColor DarkGreen
}

if ($Message) { Write-Host "Note    : $Message" }
Write-Host "Log     : $LogFile"
Write-Host ""
