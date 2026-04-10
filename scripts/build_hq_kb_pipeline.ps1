param(
  [string]$ProjectRoot = "D:\Astro",
  [string]$OutputRoot = "D:\Astro\data\high_quality",
  [string]$CsvRoot = "D:\Astro\data\astronomy_dataset.xlsx",
  [int]$ArxivMaxResults = 240,
  [int]$ApodCount = 100,
  [int]$ExoplanetMaxRows = 4000,
  [int]$DownloadPdfLimit = 0,
  [string]$NasaApiKey = ""
)

$ErrorActionPreference = "Stop"

$backendRoot = Join-Path $ProjectRoot "backend"
$pythonExe = Join-Path $backendRoot ".venv\Scripts\python.exe"
if (!(Test-Path $pythonExe)) {
  throw "Python venv not found: $pythonExe"
}

$buildScript = Join-Path $backendRoot "scripts\build_hq_astronomy_corpus.py"
$ingestScript = Join-Path $backendRoot "scripts\ingest_hq_astronomy_corpus.py"

if (!(Test-Path $buildScript)) { throw "Missing script: $buildScript" }
if (!(Test-Path $ingestScript)) { throw "Missing script: $ingestScript" }

$apiKey = "DEMO_KEY"
if (-not [string]::IsNullOrWhiteSpace($NasaApiKey)) {
  $apiKey = $NasaApiKey.Trim()
}
elseif (-not [string]::IsNullOrWhiteSpace($env:NASA_API_KEY)) {
  $apiKey = $env:NASA_API_KEY.Trim()
}

Push-Location $backendRoot
try {
  $env:SQLITE_PATH = "D:/Astro/backend/astrograph.db"

  Write-Host "[1/2] Download + clean HQ astronomy data..."
  & $pythonExe $buildScript `
    --output-root $OutputRoot `
    --arxiv-max-results $ArxivMaxResults `
    --apod-count $ApodCount `
    --exoplanet-max-rows $ExoplanetMaxRows `
    --download-pdf-limit $DownloadPdfLimit `
    --nasa-api-key $apiKey

  Write-Host "[2/2] Ingest into knowledge base + rebuild graph..."
  & $pythonExe $ingestScript `
    --csv-root $CsvRoot `
    --kb-jsonl (Join-Path $OutputRoot "clean\astronomy_kb_clean.jsonl") `
    --fact-jsonl (Join-Path $OutputRoot "clean\exoplanet_facts.jsonl")
}
finally {
  Pop-Location
}

Write-Host "HQ KB pipeline completed."
