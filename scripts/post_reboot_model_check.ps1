$backendDir = 'D:\Astro\backend'
$pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'

Write-Host 'Starting backend...'
$proc = Start-Process -FilePath $pythonExe -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $backendDir -PassThru
Write-Host "Backend PID: $($proc.Id)"

Start-Sleep -Seconds 8

try {
    $health = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 12
    Write-Host "Health: $($health.status)"
} catch {
    Write-Host 'Health check failed.' -ForegroundColor Red
    throw
}

$status = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/v1/model/status' -TimeoutSec 20
Write-Host ''
Write-Host 'Model Status:'
$status | ConvertTo-Json -Depth 4

if ($status.loaded -and $status.text_ready) {
    Write-Host ''
    Write-Host 'SUCCESS: StarWhisper text model is ready.' -ForegroundColor Green
} else {
    Write-Host ''
    Write-Host 'NOT READY: check last_error above.' -ForegroundColor Yellow
}
