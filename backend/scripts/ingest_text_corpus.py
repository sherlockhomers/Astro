from __future__ import annotations

import argparse
import os
import sys

# 让脚本可直接导入 app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest local text corpus into Astro backend knowledge base.")
    parser.add_argument("--text-root", required=True, help="文本语料目录或文件路径（txt/md/jsonl/json）")
    parser.add_argument("--category", default="text_knowledge", help="文本实体分类标签")
    parser.add_argument("--chunk-size", type=int, default=900, help="文本分块长度")
    parser.add_argument("--overlap", type=int, default=150, help="分块重叠长度")
    parser.add_argument("--csv-root", default="", help="可选：同时加载主数据源（CSV目录或Excel）")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    from app.services.data_service import DataService
    from app.services.graph_service import GraphService

    ds = DataService()
    if args.csv_root:
        ds.load_data_source(args.csv_root, [])
    result = ds.ingest_text_corpus(
        text_root=args.text_root,
        category_prefix=args.category,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    print(result)

    # 脚本模式下可立即重建内存图谱，便于后续问答使用新文本。
    if args.csv_root:
        gs = GraphService(ds)
        ok, message, task_id = gs.build_graph(
            csv_root=args.csv_root,
            categories=[],
            write_neo4j=False,
        )
        print({"graph_rebuilt": ok, "task_id": task_id, "message": message})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
