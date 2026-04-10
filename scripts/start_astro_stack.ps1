param(
    [string]$ProjectRoot = "D:\Astro",
    [int]$BackendPort = 8000
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$msg) {
    Write-Host "[ASTRO] $msg"
}

function Wait-DockerReady {
    $ready = $false
    for ($i = 1; $i -le 40; $i++) {
        try {
            docker version --format "{{.Server.Version}}" | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $ready = $true
                break
            }
        } catch {}
        Start-Sleep -Seconds 3
    }
    if (-not $ready) {
        throw "Docker daemon not ready."
    }
}

Write-Step "Project root: $ProjectRoot"
Set-Location $ProjectRoot

Write-Step "Ensuring Docker Desktop is running..."
try {
    docker version --format "{{.Server.Version}}" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "not ready" }
} catch {
    Start-Process -FilePath "C:\Program Files\Docker\Docker\Docker Desktop.exe" | Out-Null
}
Wait-DockerReady
Write-Step "Docker ready."

Write-Step "Starting Milvus container..."
docker compose -f "$ProjectRoot\compose.yaml" up -d milvus-standalone | Out-Null

Write-Step "Stopping existing backend on :$BackendPort (if any)..."
$conn = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    Stop-Process -Id $conn.OwningProcess -Force
    Start-Sleep -Seconds 1
}

$backendRoot = Join-Path $ProjectRoot "backend"
$py = Join-Path $backendRoot ".venv\Scripts\python.exe"
$out = Join-Path $backendRoot "logs\uvicorn.out.log"
$err = Join-Path $backendRoot "logs\uvicorn.err.log"

if (Test-Path $out) { Remove-Item $out -Force }
if (Test-Path $err) { Remove-Item $err -Force }

Write-Step "Starting backend..."
Start-Process -FilePath $py `
    -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port",$BackendPort `
    -WorkingDirectory $backendRoot `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err | Out-Null

Write-Step "Waiting for health endpoint..."
$healthOk = $false
for ($i = 1; $i -le 60; $i++) {
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/health" -Method Get -TimeoutSec 3
        if ($h.status -eq "ok") {
            $healthOk = $true
            break
        }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $healthOk) {
    Write-Step "Backend failed to become healthy. Last log:"
    if (Test-Path $err) { Get-Content $err -Tail 120 }
    throw "Backend startup failed."
}

Write-Step "Backend healthy. Checking model + image index status..."
$model = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/v1/model/status" -Method Get
$index = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/v1/image/index-status" -Method Get

Write-Host ""
Write-Host "Model loaded=$($model.loaded) text_ready=$($model.text_ready) vision_ready=$($model.vision_ready)"
Write-Host "Image index state=$($index.state) vectors=$($index.indexed_vectors) milvus_connected=$($index.milvus_connected)"
Write-Host ""
Write-Step "Done."
