from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.data_service import DataService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate image manifest for MinIO sync.")
    parser.add_argument("--csv-root", required=True, help="Dataset path (CSV dir or Excel .xlsx)")
    parser.add_argument("--output", required=True, help="Output jsonl path")
    parser.add_argument("--query", default="", help="Optional filter query")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    csv_root = Path(args.csv_root)
    output_path = Path(args.output)

    service = DataService()
    service.load_data_source(str(csv_root))
    page = 1
    page_size = 100
    rows: list[dict] = []

    while True:
        payload = service.list_images(query=args.query, page=page, page_size=page_size)
        rows.extend(payload["items"])
        if not payload["has_next"]:
            break
        page += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for item in rows:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"manifest written: {output_path}")
    print(f"rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
