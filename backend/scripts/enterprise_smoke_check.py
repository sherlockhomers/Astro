from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx


def ok_line(name: str, passed: bool, detail: str) -> str:
    flag = "PASS" if passed else "FAIL"
    return f"[{flag}] {name}: {detail}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Enterprise smoke check for Astro backend.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base url")
    parser.add_argument("--text-query", default="spiral galaxy", help="Text query for image search")
    parser.add_argument("--cn-query", default="银河 星云", help="Chinese text query for image search")
    parser.add_argument("--csv-root", default="", help="Optional: graph not ready时自动触发 graph/build（CSV目录或Excel）")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    out: list[str] = []
    failed = 0

    with httpx.Client(timeout=120.0) as client:
        # 1) Backend health + status
        try:
            health = client.get(f"{base}/health").json()
            out.append(ok_line("backend.health", health.get("status") == "ok", json.dumps(health, ensure_ascii=False)))
            if health.get("status") != "ok":
                failed += 1
        except Exception as exc:  # noqa: BLE001
            out.append(ok_line("backend.health", False, str(exc)))
            failed += 1

        # 2) Milvus vector status
        try:
            vs = client.get(f"{base}/api/v1/image/vector-status").json()
            cond = bool(vs.get("milvus_connected")) and int(vs.get("indexed_vectors", 0)) > 0
            out.append(ok_line("milvus.vector_status", cond, json.dumps(vs, ensure_ascii=False)))
            if not cond:
                failed += 1
        except Exception as exc:  # noqa: BLE001
            out.append(ok_line("milvus.vector_status", False, str(exc)))
            failed += 1

        # 3) Text-to-image + pagination
        first_image_bytes: bytes | None = None
        try:
            p1 = client.get(
                f"{base}/api/v1/image/search-by-text",
                params={"query": args.text_query, "page": 1, "page_size": 4},
            ).json()
            p2 = client.get(
                f"{base}/api/v1/image/search-by-text",
                params={"query": args.text_query, "page": 2, "page_size": 4},
            ).json()
            items1 = p1.get("items", [])
            items2 = p2.get("items", [])
            ids1 = {x.get("id") for x in items1 if x.get("id")}
            ids2 = {x.get("id") for x in items2 if x.get("id")}
            no_overlap = len(ids1.intersection(ids2)) == 0
            cond = len(items1) > 0 and bool(p1.get("mode") == "clip_milvus") and no_overlap
            out.append(
                ok_line(
                    "image.text_search",
                    cond,
                    f"p1={len(items1)}, p2={len(items2)}, mode={p1.get('mode')}, overlap={len(ids1.intersection(ids2))}",
                )
            )
            if not cond:
                failed += 1

            if items1:
                image_url = items1[0].get("image_url")
                if isinstance(image_url, str) and image_url:
                    img_resp = client.get(f"{base}{image_url}" if image_url.startswith("/") else image_url)
                    if img_resp.status_code == 200:
                        first_image_bytes = img_resp.content
                    out.append(ok_line("image.preview_access", img_resp.status_code == 200, f"status={img_resp.status_code}"))
                    if img_resp.status_code != 200:
                        failed += 1
                else:
                    out.append(ok_line("image.preview_access", False, "no image_url in result"))
                    failed += 1
        except Exception as exc:  # noqa: BLE001
            out.append(ok_line("image.text_search", False, str(exc)))
            failed += 1

        # 4) Chinese text query
        try:
            cn = client.get(
                f"{base}/api/v1/image/search-by-text",
                params={"query": args.cn_query, "page": 1, "page_size": 4},
            ).json()
            cond = len(cn.get("items", [])) > 0 and cn.get("mode") == "clip_milvus"
            out.append(ok_line("image.text_search_cn", cond, f"items={len(cn.get('items', []))}, mode={cn.get('mode')}"))
            if not cond:
                failed += 1
        except Exception as exc:  # noqa: BLE001
            out.append(ok_line("image.text_search_cn", False, str(exc)))
            failed += 1

        # 5) Image-to-image query
        try:
            if first_image_bytes is None:
                out.append(ok_line("image.image_search", False, "no source image bytes from text search"))
                failed += 1
            else:
                files = {"file": ("probe.jpg", first_image_bytes, "image/jpeg")}
                img1 = client.post(
                    f"{base}/api/v1/image/search-by-image",
                    params={"page": 1, "page_size": 4},
                    files=files,
                ).json()
                img2 = client.post(
                    f"{base}/api/v1/image/search-by-image",
                    params={"page": 2, "page_size": 4},
                    files=files,
                ).json()
                ids1 = {x.get("id") for x in img1.get("items", []) if x.get("id")}
                ids2 = {x.get("id") for x in img2.get("items", []) if x.get("id")}
                cond = len(ids1) > 0 and img1.get("mode") == "clip_milvus" and len(ids1.intersection(ids2)) == 0
                out.append(
                    ok_line(
                        "image.image_search",
                        cond,
                        f"p1={len(ids1)}, p2={len(ids2)}, mode={img1.get('mode')}, overlap={len(ids1.intersection(ids2))}",
                    )
                )
                if not cond:
                    failed += 1
        except Exception as exc:  # noqa: BLE001
            out.append(ok_line("image.image_search", False, str(exc)))
            failed += 1

        # 6) Graph endpoints and images_catalog filtering symptom
        try:
            gs = client.get(f"{base}/api/v1/graph/status").json()
            if not gs.get("graph_ready") and args.csv_root:
                client.post(
                    f"{base}/api/v1/graph/build",
                    json={"csv_root": args.csv_root, "categories": [], "write_neo4j": False},
                    timeout=600,
                )
                gs = client.get(f"{base}/api/v1/graph/status").json()
            vg = client.get(f"{base}/api/v1/visualization/graph", params={"max_nodes": 1200}).json()
            node_names = [str(x.get("name", "")) for x in vg.get("nodes", [])]
            bad = [n for n in node_names if "asteroid belt " in n.lower() and n.split()[-1].isdigit()]
            cond = bool(gs.get("graph_ready")) and len(bad) == 0
            out.append(
                ok_line(
                    "graph.visualization",
                    cond,
                    f"graph_ready={gs.get('graph_ready')}, nodes={len(node_names)}, bad_numbered_nodes={len(bad)}",
                )
            )
            if not cond:
                failed += 1
        except Exception as exc:  # noqa: BLE001
            out.append(ok_line("graph.visualization", False, str(exc)))
            failed += 1

    for line in out:
        print(line)
    print(f"\nTOTAL: {len(out) - failed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
