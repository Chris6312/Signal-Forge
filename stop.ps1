#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot
$ComposeFile = Join-Path $ProjectRoot 'docker-compose.yml'

Write-Host 'Stopping Signal Forge...' -ForegroundColor Cyan
Set-Location $ProjectRoot

# Graceful shutdown: SIGTERM then SIGKILL after 30 s per container.
docker compose -f $ComposeFile down --timeout 30

if ($LASTEXITCODE -eq 0) {
    Write-Host ''
    Write-Host 'All containers stopped.' -ForegroundColor Green
    Write-Host ''
    Write-Host '  Data volumes are preserved.' -ForegroundColor DarkGray
    Write-Host '  To also remove volumes: docker compose down -v' -ForegroundColor DarkGray
} else {
    Write-Warning 'docker compose down returned a non-zero exit code.'
    Write-Host 'Check container state with: docker compose ps' -ForegroundColor Yellow
    exit 1
}
