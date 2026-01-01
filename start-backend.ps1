# BeamState Backend Startup Script
# Safely stops any process on port 8000, then starts the backend

Write-Host "BeamState Backend Startup" -ForegroundColor Cyan
Write-Host "=========================" -ForegroundColor Cyan

# Find process using port 8000
$port = 8000
$netstatOutput = netstat -ano | Select-String ":$port " | Select-String "LISTENING"

if ($netstatOutput) {
    Write-Host "Found process on port $port, stopping..." -ForegroundColor Yellow
    
    # Extract PID from netstat output
    $pid = ($netstatOutput -split '\s+')[-1]
    
    if ($pid -match '^\d+$') {
        $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Stopping process: $($process.ProcessName) (PID: $pid)" -ForegroundColor Yellow
            Stop-Process -Id $pid -Force
            Start-Sleep -Seconds 2
            Write-Host "Process stopped" -ForegroundColor Green
        }
    }
} else {
    Write-Host "Port $port is free" -ForegroundColor Green
}

# Start backend
Write-Host ""
Write-Host "Starting backend..." -ForegroundColor Cyan
Set-Location "$PSScriptRoot\backend"
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
