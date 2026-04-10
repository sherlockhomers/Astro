"""
一键从数据源（CSV目录或 Excel）构建知识图谱，并可导出 Cypher。

示例：
python scripts/build_kg_from_csv.py --csv-root "D:/dataset/天文学数据集.xlsx" --output-cypher "D:/Astro/output/graph.cypher"
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.services.data_service import DataService
from app.services.graph_service import GraphService


def main() -> None:
    parser = argparse.ArgumentParser(description="AstroGraph 数据源 -> KG 构建脚本")
    parser.add_argument("--csv-root", required=True, help="数据源路径（CSV目录或Excel .xlsx）")
    parser.add_argument("--output-cypher", default="", help="可选，导出 cypher 文件路径")
    parser.add_argument("--write-neo4j", action="store_true", help="可选，直接写入 Neo4j")
    args = parser.parse_args()

    csv_root = Path(args.csv_root)
    if not csv_root.exists():
        raise SystemExit(f"路径不存在: {csv_root}")

    data_service = DataService()
    graph_service = GraphService(data_service)
    ok, message, task_id = graph_service.build_graph(
        csv_root=str(csv_root),
        categories=[],
        write_neo4j=args.write_neo4j,
    )
    print(f"[build] ok={ok} task_id={task_id}")
    print(f"[build] {message}")

    if args.output_cypher:
        ok2, node_count, relation_count, message2 = graph_service.export_cypher(args.output_cypher)
        print(
            f"[export] ok={ok2} nodes={node_count} relations={relation_count}\n"
            f"[export] {message2}"
        )


if __name__ == "__main__":
    main()
