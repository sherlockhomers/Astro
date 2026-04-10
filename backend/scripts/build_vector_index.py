from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.data_service import DataService
from app.services.vector_search_service import VectorSearchService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build local vector index snapshot for dataset entities.")
    parser.add_argument("--csv-root", required=True, help="Dataset path (CSV dir or Excel .xlsx)")
    parser.add_argument("--output", required=True, help="Output json path")
    parser.add_argument("--top-k", type=int, default=5, help="Sample retrieval top-k")
    parser.add_argument("--query", default="木星", help="Sample query")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    data_service = DataService()
    data_service.load_data_source(args.csv_root)
    vector_service = VectorSearchService(data_service)
    sample = vector_service.hybrid_search(args.query, None, top_k=args.top_k)
    payload = {
        "schema": vector_service.get_schema(),
        "entity_count": data_service.entity_count,
        "sample_query": args.query,
        "sample_results": sample,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"vector index snapshot: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
