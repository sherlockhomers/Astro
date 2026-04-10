from __future__ import annotations

import argparse
import asyncio
import time
from statistics import mean

import httpx


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simple async load test for AstroGraph APIs.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--path", default="/api/v1/retrieval/search", help="Target API path")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrent workers")
    parser.add_argument("--requests", type=int, default=200, help="Total request count")
    return parser


async def one_request(client: httpx.AsyncClient, url: str, idx: int) -> tuple[float, int]:
    payload = {
        "query": f"木星 {idx % 10}",
        "top_k": 5,
        "image_hint": None,
    }
    started = time.perf_counter()
    resp = await client.post(url, json=payload, timeout=30.0)
    elapsed = (time.perf_counter() - started) * 1000
    return elapsed, resp.status_code


async def run(args: argparse.Namespace) -> int:
    url = f"{args.base_url.rstrip('/')}{args.path}"
    semaphore = asyncio.Semaphore(args.concurrency)
    latencies: list[float] = []
    statuses: dict[int, int] = {}

    async with httpx.AsyncClient() as client:
        async def worker(i: int) -> None:
            async with semaphore:
                elapsed, status = await one_request(client, url, i)
                latencies.append(elapsed)
                statuses[status] = statuses.get(status, 0) + 1

        await asyncio.gather(*(worker(i) for i in range(args.requests)))

    if not latencies:
        print("No requests were executed.")
        return 1

    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[int(len(latencies_sorted) * 0.50)]
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
    p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]
    print(f"url: {url}")
    print(f"requests: {args.requests}, concurrency: {args.concurrency}")
    print(f"mean: {mean(latencies):.2f} ms, p50: {p50:.2f} ms, p95: {p95:.2f} ms, p99: {p99:.2f} ms")
    print(f"status distribution: {statuses}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
