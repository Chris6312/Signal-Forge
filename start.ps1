#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot
$ComposeFile = Join-Path $ProjectRoot 'docker-compose.yml'

function Write-Step([int]$n, [int]$total, [string]$msg) {
    Write-Host "[$n/$total] $msg" -ForegroundColor Cyan
}
function Write-OK([string]$msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  WARN $msg" -ForegroundColor Yellow }

# ── 1. Ensure Docker daemon is reachable ──────────────────────────────────────
Write-Step 1 5 'Checking Docker...'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error 'docker not found on PATH. Install Docker Desktop and retry.'
}

docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn 'Docker Desktop is not running. Attempting to start...'
    $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path $desktop)) {
        Write-Error "Docker Desktop not found at '$desktop'. Start it manually and retry."
    }
    Start-Process $desktop
    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    do {
        Start-Sleep -Seconds 4
        docker info 2>&1 | Out-Null
    } while ($LASTEXITCODE -ne 0 -and [DateTime]::UtcNow -lt $deadline)
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'Docker did not start within 90 s. Start Docker Desktop manually and retry.'
    }
}
Write-OK 'Docker is running.'

# ── 2. Start containers ───────────────────────────────────────────────────────
Write-Step 2 5 'Starting containers (docker compose up -d)...'
Set-Location $ProjectRoot
docker compose -f $ComposeFile up -d
if ($LASTEXITCODE -ne 0) { Write-Error 'docker compose up failed.' }
Write-OK 'Containers started.'

# ── 3. Wait for all services to be healthy ────────────────────────────────────
Write-Step 3 5 'Waiting for services to be healthy (up to 120 s)...'
$deadline = [DateTime]::UtcNow.AddSeconds(120)
$healthy  = $false
do {
    Start-Sleep -Seconds 4
    $psOut   = (docker compose -f $ComposeFile ps 2>&1) -join "`n"
    $healthy = $psOut -notmatch '(?i)(starting|unhealthy|restarting|exited)'
} while (-not $healthy -and [DateTime]::UtcNow -lt $deadline)

if ($healthy) {
    Write-OK 'All services healthy.'
} else {
    Write-Warn 'One or more services may not be fully healthy.'
    Write-Warn 'Run: docker compose ps   to investigate.'
}

# ── 4. Run database migrations (idempotent) ───────────────────────────────────
Write-Step 4 5 'Running database migrations...'
docker compose -f $ComposeFile exec backend alembic upgrade head 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warn 'Migrations returned a non-zero exit code.'
    Write-Warn 'Run: docker compose logs backend   to investigate.'
} else {
    Write-OK 'Migrations applied.'
}

# ── 5. Open Windows Terminal with one tab per service ─────────────────────────
Write-Step 5 5 'Opening Windows Terminal log tabs...'

if (-not (Get-Command wt -ErrorAction SilentlyContinue)) {
    Write-Warn 'Windows Terminal (wt) not found. Skipping tab launch.'
    Write-Warn 'Tail logs manually: docker compose logs -f <service>'
} else {
    # Base64-encode each tab's pwsh command so wt never sees embedded quotes.
    # This avoids the quoting-mangling that causes error 0x80070002.
    function ConvertTo-EncodedCmd([string]$cmd) {
        $bytes = [System.Text.Encoding]::Unicode.GetBytes($cmd)
        [Convert]::ToBase64String($bytes)
    }

    $tabDefs = @(
        @{ Title = 'Postgres';        Svc = 'postgres' },
        @{ Title = 'Redis';           Svc = 'redis'    },
        @{ Title = 'Backend+Workers'; Svc = 'backend'  },
        @{ Title = 'Frontend';        Svc = 'frontend' }
    )

    $tabParts = foreach ($t in $tabDefs) {
        $cmd     = "Set-Location '$ProjectRoot'; docker compose -f '$ComposeFile' logs -f $($t.Svc)"
        $enc     = ConvertTo-EncodedCmd $cmd
        "new-tab --title `"$($t.Title)`" -- pwsh -NoExit -EncodedCommand $enc"
    }

    Start-Process wt -ArgumentList ($tabParts -join ' ; ')
    Write-OK 'Windows Terminal launched.'
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host 'Signal Forge is running.' -ForegroundColor Green
Write-Host ''
Write-Host '  Backend API  : http://localhost:8100'      -ForegroundColor White
Write-Host '  Swagger docs : http://localhost:8100/docs' -ForegroundColor White
Write-Host '  Frontend     : http://localhost:5180'      -ForegroundColor White
Write-Host ''
Write-Host "  Stop: .\stop.ps1" -ForegroundColor DarkGray
