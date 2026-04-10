# 启动本仓库自带的 Milvus standalone（需已安装 Docker Desktop 并确保 docker 在 PATH）
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$docker = $null
if (Get-Command docker -ErrorAction SilentlyContinue) {
    $docker = "docker"
} elseif (Test-Path "${env:ProgramFiles}\Docker\Docker\resources\bin\docker.exe") {
    $docker = "${env:ProgramFiles}\Docker\Docker\resources\bin\docker.exe"
}
if (-not $docker) {
    Write-Host "未找到 docker。请先安装 Docker Desktop for Windows，安装后重启终端，再运行本脚本。" -ForegroundColor Red
    exit 1
}
Set-Location $here
& $docker compose up -d
Write-Host "Milvus 已在后台启动。等待约 60～120 秒后，可用端口 19530 连接。" -ForegroundColor Green
& $docker compose ps
