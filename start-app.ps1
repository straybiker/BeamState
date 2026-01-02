# BeamState Full Application Startup Script
# Safely stops any leftover processes, then starts both backend and frontend

Write-Host "BeamState Application Startup" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan
Write-Host ""

# Function to aggressive cleanup
function Cleanup-Zombies {
    Write-Host "Cleaning up potential zombie processes..." -ForegroundColor Yellow
    Stop-Process -Name "python", "node", "uvicorn" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Run cleanup
Cleanup-Zombies

# Function to stop process on a specific port (Legacy check)
function Stop-PortProcess {
    param(
        [int]$Port,
        [string]$ServiceName
    )
    
    $netstatOutput = netstat -ano | Select-String ":$Port " | Select-String "LISTENING"
    
    if ($netstatOutput) {
        Write-Host "[$ServiceName] Found process on port $Port, stopping..." -ForegroundColor Yellow
        
        $procId = ($netstatOutput -split '\s+')[-1]
        
        if ($procId -match '^\d+$') {
            $process = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "[$ServiceName] Stopping: $($process.ProcessName) (PID: $procId)" -ForegroundColor Yellow
                Stop-Process -Id $procId -Force
                Start-Sleep -Seconds 1
                Write-Host "[$ServiceName] Process stopped" -ForegroundColor Green
            }
        }
    }
    else {
        Write-Host "[$ServiceName] Port $Port is free" -ForegroundColor Green
    }
}

# Clean up ports (Double check)
Stop-PortProcess -Port 8000 -ServiceName "Backend"
Stop-PortProcess -Port 5173 -ServiceName "Frontend"

Write-Host ""
Write-Host "Starting services..." -ForegroundColor Cyan
Write-Host ""

# Start backend in new window (autoclose on exit)
Write-Host "[Backend] Starting on port 8000..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-Command", "cd '$PSScriptRoot\backend'; python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000; Read-Host 'Backend stopped. Press Enter to close.'" -WorkingDirectory "$PSScriptRoot"

Start-Sleep -Seconds 3

# Start frontend in new window (autoclose on exit)
Write-Host "[Frontend] Starting on port 5173..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-Command", "cd '$PSScriptRoot\frontend'; npm run dev; Read-Host 'Frontend stopped. Press Enter to close.'" -WorkingDirectory "$PSScriptRoot"

Write-Host ""
Write-Host "BeamState started!" -ForegroundColor Green
Write-Host "Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "Frontend: http://localhost:5173" -ForegroundColor White
Write-Host ""
Write-Host "Press any key to exit this window..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
