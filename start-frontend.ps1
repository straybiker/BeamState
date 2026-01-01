# BeamState Frontend Startup Script
# Safely stops any process on port 5173, then starts the frontend

Write-Host "BeamState Frontend Startup" -ForegroundColor Cyan
Write-Host "==========================" -ForegroundColor Cyan

# Find process using port 5173
$port = 5173
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
}
else {
    Write-Host "Port $port is free" -ForegroundColor Green
}

# Start frontend
Write-Host ""
Write-Host "Starting frontend..." -ForegroundColor Cyan
Set-Location "$PSScriptRoot\frontend"
npm run dev
