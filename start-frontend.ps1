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
    $procId = ($netstatOutput -split '\s+')[-1]
    
    if ($procId -match '^\d+$') {
        $process = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Stopping process: $($process.ProcessName) (PID: $procId)" -ForegroundColor Yellow
            Stop-Process -Id $procId -Force
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
