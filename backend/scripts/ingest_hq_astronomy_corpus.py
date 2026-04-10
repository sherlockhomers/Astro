from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# allow script to import app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest high-quality astronomy corpus into Astro backend.")
    parser.add_argument("--csv-root", default=r"D:/Astro/data/astronomy_dataset.xlsx", help="Main dataset path.")
    parser.add_argument(
        "--kb-jsonl",
        default=r"D:/Astro/data/high_quality/clean/astronomy_kb_clean.jsonl",
        help="Clean text corpus JSONL file.",
    )
    parser.add_argument(
        "--fact-jsonl",
        default=r"D:/Astro/data/high_quality/clean/exoplanet_facts.jsonl",
        help="Structured exoplanet facts JSONL.",
    )
    parser.add_argument("--chunk-size", type=int, default=1100, help="Chunk size for text ingestion.")
    parser.add_argument("--overlap", type=int, default=180, help="Chunk overlap for text ingestion.")
    parser.add_argument(
        "--category-prefix",
        default="hq_astro_kb",
        help="Category prefix for text chunks.",
    )
    parser.add_argument(
        "--provider-tag",
        default="nasa_exoplanet_archive",
        help="Provider name for structured facts.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    csv_root = Path(args.csv_root)
    kb_jsonl = Path(args.kb_jsonl)
    fact_jsonl = Path(args.fact_jsonl)

    if not csv_root.exists():
        raise SystemExit(f"csv root not found: {csv_root}")
    if not kb_jsonl.exists():
        raise SystemExit(f"kb jsonl not found: {kb_jsonl}")
    if not fact_jsonl.exists():
        raise SystemExit(f"fact jsonl not found: {fact_jsonl}")

    from app.services.data_service import DataService
    from app.services.graph_service import GraphService

    ds = DataService()
    # Ensure main dataset and images catalog are loaded first.
    load_result = ds.load_data_source(str(csv_root), [])

    ingest_result = ds.ingest_text_corpus(
        text_root=str(kb_jsonl),
        category_prefix=str(args.category_prefix),
        chunk_size=int(args.chunk_size),
        overlap=int(args.overlap),
    )

    facts = _load_jsonl(fact_jsonl)
    inserted = 0
    updated = 0
    for row in facts:
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        result = ds.upsert_dynamic_fact(name, row, provider=str(args.provider_tag))
        if bool(result.get("inserted", False)):
            inserted += 1
        else:
            updated += 1

    gs = GraphService(ds)
    graph_ok, graph_msg, graph_task_id = gs.rebuild_from_loaded_entities(write_neo4j=False)
    graph_status = gs.status()

    payload = {
        "load_result": load_result,
        "ingest_result": ingest_result,
        "facts_total": len(facts),
        "facts_inserted": inserted,
        "facts_updated": updated,
        "graph_rebuild_ok": graph_ok,
        "graph_task_id": graph_task_id,
        "graph_message": graph_msg,
        "graph_status": graph_status,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
