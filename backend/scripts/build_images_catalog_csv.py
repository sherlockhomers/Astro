from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build images_catalog.csv from dataset image tree for AstroGraph."
    )
    parser.add_argument(
        "--dataset-root",
        required=True,
        help="Dataset root path, which contains images/ and info/ folders.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output csv path. Default: <dataset-root>/info/images_catalog.csv",
    )
    parser.add_argument(
        "--splits",
        default="train",
        help="Comma-separated splits to include, e.g. train or train,test",
    )
    parser.add_argument(
        "--max-per-class",
        type=int,
        default=0,
        help="Optional cap per class (0 means no cap).",
    )
    return parser


def _normalize_name(stem: str) -> str:
    text = stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(text.split())


def _make_id(rel_image_path: str) -> str:
    digest = hashlib.sha1(rel_image_path.encode("utf-8")).hexdigest()[:20]
    return f"imgcat_{digest}"


def main() -> int:
    args = build_parser().parse_args()
    dataset_root = Path(args.dataset_root)
    images_root = dataset_root / "images"
    info_root = dataset_root / "info"
    output_path = Path(args.output) if args.output else info_root / "images_catalog.csv"
    wanted_splits = {x.strip().lower() for x in args.splits.split(",") if x.strip()}
    max_per_class = max(0, int(args.max_per_class))

    if not dataset_root.exists() or not dataset_root.is_dir():
        raise SystemExit(f"dataset root not found: {dataset_root}")
    if not images_root.exists() or not images_root.is_dir():
        raise SystemExit(f"images root not found: {images_root}")
    if not info_root.exists() or not info_root.is_dir():
        raise SystemExit(f"info root not found: {info_root}")

    rows: list[dict[str, str]] = []
    total_seen = 0
    per_class_counter: dict[tuple[str, str, str], int] = {}

    for split_dir in sorted(p for p in images_root.iterdir() if p.is_dir()):
        split = split_dir.name.strip().lower()
        if wanted_splits and split not in wanted_splits:
            continue
        for group_dir in sorted(p for p in split_dir.iterdir() if p.is_dir()):
            group = group_dir.name.strip().replace(" ", "_").lower()
            for class_dir in sorted(p for p in group_dir.iterdir() if p.is_dir()):
                class_name = class_dir.name.strip().replace(" ", "_").lower()
                class_key = (split, group, class_name)
                per_class_counter.setdefault(class_key, 0)
                for img in sorted(class_dir.rglob("*")):
                    if not img.is_file() or img.suffix.lower() not in IMAGE_EXTS:
                        continue
                    total_seen += 1
                    if max_per_class and per_class_counter[class_key] >= max_per_class:
                        continue
                    rel_image = img.relative_to(dataset_root).as_posix()
                    name = _normalize_name(img.stem)
                    rows.append(
                        {
                            "id": _make_id(rel_image),
                            "name": name or img.stem,
                            "description": f"{class_name} image from {split} split ({group}).",
                            "category": class_name,
                            "image_path": rel_image,
                            "split": split,
                            "group": group,
                            "source_file": "images_catalog.csv",
                        }
                    )
                    per_class_counter[class_key] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["id", "name", "description", "category", "image_path", "split", "group", "source_file"]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    class_count = len({k[2] for k in per_class_counter.keys()})
    print(f"dataset_root: {dataset_root}")
    print(f"output: {output_path}")
    print(f"splits: {sorted(wanted_splits) if wanted_splits else 'all'}")
    print(f"classes: {class_count}")
    print(f"images_seen: {total_seen}")
    print(f"rows_written: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

