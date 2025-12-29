# Run BeamState Locally

# 1. Install Backend Deps
Write-Host "Installing Backend Dependencies..."
pip install -r backend/requirements.txt

# 2. Start Backend (New Window/Background)
Write-Host "Starting Backend..."
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m uvicorn main:app --app-dir backend --reload --port 8000"

# 3. Start Frontend
Write-Host "Starting Frontend..."
Set-Location frontend
if (!(Test-Path node_modules)) {
    npm install
}
npm run dev
