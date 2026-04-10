# High-Quality Astronomy KB Pipeline

This project now includes a two-step backend pipeline for high-quality astronomy data:

1. Download and clean trusted sources:
- arXiv (astro-ph papers/abstracts)
- NASA APOD descriptions
- NASA Exoplanet Archive structured rows

2. Ingest into backend knowledge base and rebuild graph.

## One-command (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File D:\Astro\scripts\build_hq_kb_pipeline.ps1
```

Optional tuning:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Astro\scripts\build_hq_kb_pipeline.ps1 `
  -ArxivMaxResults 300 `
  -ApodCount 120 `
  -ExoplanetMaxRows 5000 `
  -DownloadPdfLimit 20
```

## Output paths

- Clean corpus: `D:\Astro\data\high_quality\clean\astronomy_kb_clean.jsonl`
- Structured facts: `D:\Astro\data\high_quality\clean\exoplanet_facts.jsonl`
- Build stats: `D:\Astro\data\high_quality\clean\build_stats.json`
- Optional PDFs: `D:\Astro\data\high_quality\papers\pdf\*.pdf`

## Restart backend after ingestion

The ingestion script writes to sqlite knowledge chunks. If the API process is already running, restart backend to ensure in-memory services reload latest entities.
