"""
将已加载数据集中的图片编码为 CLIP 向量并写入 Milvus。

前置:
  - Docker 已启动 Milvus (compose.yaml 中 milvus-standalone)
  - 已设置 MILVUS_ENABLED=true 与 CSV_ROOT
  - pip install -r requirements.txt (含 torch, open_clip_torch, pymilvus)

用法:
  cd backend
  .venv\\Scripts\\python scripts\\index_milvus_clip.py --csv-root "E:/.../天文学数据集.xlsx" --batch 32 --max-images 0
"""

from __future__ import annotations

import argparse
import os
import sys
import time

os.environ.setdefault("MILVUS_ENABLED", "true")

# 保证可导入 app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-root", required=True, help="数据源路径（CSV目录或Excel .xlsx）")
    parser.add_argument("--batch", type=int, default=16, help="每批插入条数")
    parser.add_argument("--clip-batch", type=int, default=24, help="CLIP 单次编码批量（CPU建议 8~24）")
    parser.add_argument("--max-images", type=int, default=0, help="最多索引张数，0 表示全部")
    parser.add_argument("--start-index", type=int, default=0, help="断点续跑起始索引（0-based）")
    parser.add_argument("--final-flush-timeout", type=float, default=0, help="最终 flush 超时秒数，<=0 表示跳过")
    args = parser.parse_args()

    from app.services.data_service import DataService
    from app.services.milvus_clip_service import milvus_clip_service

    svc = milvus_clip_service
    schema = svc.ensure_schema()
    print(schema)

    if not svc._ensure_model():
        print("CLIP 不可用:", svc.last_error)
        return 1

    ds = DataService()
    ds.load_data_source(args.csv_root, [])
    entities = ds.export_entities()
    image_entities = [e for e in entities if e.get("image_id")]
    unique_entities: list[dict] = []
    seen_image_ids: set[str] = set()
    for ent in image_entities:
        iid = str(ent.get("image_id", "")).strip()
        if not iid or iid in seen_image_ids:
            continue
        seen_image_ids.add(iid)
        unique_entities.append(ent)
    total_image_entities = len(unique_entities)
    start_index = max(0, int(args.start_index))
    if start_index > 0:
        unique_entities = unique_entities[start_index:]
    if args.max_images > 0:
        unique_entities = unique_entities[: args.max_images]
    print(f"总图片实体: {total_image_entities}")
    print(f"本次待索引图片实体: {len(unique_entities)} (start_index={start_index})")

    work_items: list[tuple[str, str]] = []
    for ent in unique_entities:
        iid = str(ent["image_id"])
        meta = ds.get_image_meta(iid)
        if not meta:
            continue
        ref = str(meta.get("ref", "")).strip()
        if not ref:
            continue
        work_items.append((iid, ref))

    if not work_items:
        print("没有可编码的图片路径。")
        return 0

    total = 0
    skipped = 0
    started = time.perf_counter()
    for i in range(0, len(work_items), args.batch):
        chunk = work_items[i : i + args.batch]
        encoded_rows, skipped_count = svc.encode_image_paths_batch(chunk, batch_size=args.clip_batch)
        skipped += int(skipped_count)
        if encoded_rows:
            total += svc.insert_vectors(encoded_rows, flush=False)
        elapsed = max(time.perf_counter() - started, 1e-6)
        done = min(i + len(chunk), len(work_items))
        speed = done / elapsed
        remaining = max(len(work_items) - done, 0)
        eta_sec = int(remaining / max(speed, 1e-6))
        print(f"进度 {done}/{len(work_items)} | 已插入 {total} | 跳过 {skipped} | {speed:.2f} img/s | ETA {eta_sec}s")

    if args.final_flush_timeout and args.final_flush_timeout > 0:
        try:
            svc.flush_collection(timeout=float(args.final_flush_timeout))
            print(f"已完成最终 flush/load (timeout={args.final_flush_timeout}s)")
        except Exception as exc:  # noqa: BLE001
            print("flush/load 失败（可稍后重试）:", exc)
    else:
        print("已跳过最终 flush/load（可后续手动执行）")
    total_elapsed = time.perf_counter() - started
    avg_speed = len(work_items) / max(total_elapsed, 1e-6)
    print(f"完成，共插入向量: {total}，跳过: {skipped}，总耗时: {int(total_elapsed)}s，平均速度: {avg_speed:.2f} img/s")
    print("实体数(Milvus):", svc.count_entities())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
