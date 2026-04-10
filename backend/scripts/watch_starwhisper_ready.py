from __future__ import annotations

import json
import time
from pathlib import Path

import httpx


MODEL_DIR = Path("F:/StarWhisper-main")
INDEX_FILE = MODEL_DIR / "pytorch_model.bin.index.json"
BASE_URL = "http://127.0.0.1:8000"


def missing_shards() -> list[str]:
    if not INDEX_FILE.exists():
        return ["pytorch_model.bin.index.json"]
    payload = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    expected = sorted({v for v in (payload.get("weight_map") or {}).values() if v})
    return [name for name in expected if not (MODEL_DIR / name).exists()]


def main() -> int:
    print(f"[watch] model_dir={MODEL_DIR}")
    while True:
        miss = missing_shards()
        print(f"[watch] missing={len(miss)}")
        if miss:
            print(f"[watch] sample_missing={miss[:3]}")
            time.sleep(30)
            continue

        print("[watch] shards complete, triggering /api/v1/model/load ...")
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(f"{BASE_URL}/api/v1/model/load", json={})
                print(f"[watch] load_status={resp.status_code} body={resp.text[:600]}")
                status = client.get(f"{BASE_URL}/api/v1/model/status")
                print(f"[watch] model_status={status.status_code} body={status.text[:600]}")
        except Exception as exc:  # noqa: BLE001
            print(f"[watch] request_error={type(exc).__name__}: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
