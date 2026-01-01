# BeamState Full Application Startup Script
# Safely stops any leftover processes, then starts both backend and frontend

Write-Host "BeamState Application Startup" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan
Write-Host ""

# Function to stop process on a specific port
function Stop-PortProcess {
    param(
        [int]$Port,
        [string]$ServiceName
    )
    
    $netstatOutput = netstat -ano | Select-String ":$Port " | Select-String "LISTENING"
    
    if ($netstatOutput) {
        Write-Host "[$ServiceName] Found process on port $Port, stopping..." -ForegroundColor Yellow
        
        $pid = ($netstatOutput -split '\s+')[-1]
        
        if ($pid -match '^\d+$') {
            $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "[$ServiceName] Stopping: $($process.ProcessName) (PID: $pid)" -ForegroundColor Yellow
                Stop-Process -Id $pid -Force
                Start-Sleep -Seconds 1
                Write-Host "[$ServiceName] Process stopped" -ForegroundColor Green
            }
        }
    }
    else {
        Write-Host "[$ServiceName] Port $Port is free" -ForegroundColor Green
    }
}

# Clean up ports
Stop-PortProcess -Port 8000 -ServiceName "Backend"
Stop-PortProcess -Port 5173 -ServiceName "Frontend"

Write-Host ""
Write-Host "Starting services..." -ForegroundColor Cyan
Write-Host ""

# Start backend in new window
Write-Host "[Backend] Starting on port 8000..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\backend'; python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000" -WorkingDirectory "$PSScriptRoot"

Start-Sleep -Seconds 3

# Start frontend in new window
Write-Host "[Frontend] Starting on port 5173..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\frontend'; npm run dev" -WorkingDirectory "$PSScriptRoot"

Write-Host ""
Write-Host "BeamState started!" -ForegroundColor Green
Write-Host "Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "Frontend: http://localhost:5173" -ForegroundColor White
Write-Host ""
Write-Host "Press any key to exit this window..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
