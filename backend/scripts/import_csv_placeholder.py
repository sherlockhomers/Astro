"""
占位脚本：后续接入真实数据源（CSV目录或Excel）-> Neo4j 构图逻辑。

用法:
python scripts/import_csv_placeholder.py --csv-root "D:/dataset/天文学数据集.xlsx"
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="AstroGraph 数据源导入占位脚本")
    parser.add_argument("--csv-root", required=True, help="数据源路径（CSV目录或Excel .xlsx）")
    args = parser.parse_args()

    csv_root = Path(args.csv_root)
    if not csv_root.exists():
        raise SystemExit(f"路径不存在: {csv_root}")

    if csv_root.is_dir():
        csv_files = list(csv_root.glob("*.csv"))
        print(f"检测到 {len(csv_files)} 个 CSV 文件")
        for file in csv_files[:10]:
            print(f"- {file.name}")
        if len(csv_files) > 10:
            print("... (其余文件省略)")
    else:
        print(f"检测到单文件数据源: {csv_root.name}")

    print("当前是占位实现：尚未写入 Neo4j。")
    print("下一步可在这里接入字段映射、实体去重、关系构建与批量入库。")


if __name__ == "__main__":
    main()
