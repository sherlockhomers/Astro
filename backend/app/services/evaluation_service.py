from __future__ import annotations

import json
import math
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


class EvaluationService:
    def __init__(self, qa_service: Any) -> None:
        self._qa_service = qa_service
        backend_root = Path(__file__).resolve().parents[2]
        self._dataset_path = backend_root / "data" / "qa_eval_set.json"
        self._report_path = backend_root / "tmp" / "qa_eval_last_report.json"
        self._report_path.parent.mkdir(parents=True, exist_ok=True)

    def load_dataset(self) -> list[dict[str, Any]]:
        if not self._dataset_path.exists():
            return []
        try:
            payload = json.loads(self._dataset_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return [dict(item) for item in payload if isinstance(item, dict)]

    def latest_report(self) -> dict[str, Any]:
        if not self._report_path.exists():
            dataset = self.load_dataset()
            return {
                "generated_at": None,
                "dataset_size": len(dataset),
                "sample_size": 0,
                "summary": {},
                "category_breakdown": [],
                "cases": [],
            }
        try:
            return json.loads(self._report_path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "generated_at": None,
                "dataset_size": 0,
                "sample_size": 0,
                "summary": {},
                "category_breakdown": [],
                "cases": [],
            }

    def run(self, sample_size: int = 12, use_cache: bool = True) -> dict[str, Any]:
        dataset = self.load_dataset()
        if not dataset:
            return {
                "generated_at": None,
                "dataset_size": 0,
                "sample_size": 0,
                "summary": {"message": "未找到评测数据集。"},
                "category_breakdown": [],
                "cases": [],
            }

        sample_size = max(1, min(int(sample_size), len(dataset)))
        selected = dataset[:sample_size]

        if not use_cache and hasattr(self._qa_service, "clear_cache"):
            try:
                self._qa_service.clear_cache()
            except Exception:
                pass

        results: list[dict[str, Any]] = []
        category_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for idx, item in enumerate(selected, start=1):
            question = str(item.get("question", "")).strip()
            category = str(item.get("category", "未分类")).strip() or "未分类"
            if not question:
                continue
            session_id = f"eval-{idx:03d}-{int(time.time())}"
            detail = self._qa_service.ask_detailed(question, session_id)
            result = self._score_case(item, detail)
            results.append(result)
            category_buckets[category].append(result)

        latencies = [float(x.get("latency_ms", 0.0)) for x in results]
        scores = [float(x.get("score", 0.0)) for x in results]
        passes = [bool(x.get("passed", False)) for x in results]
        cache_hits = [1.0 if x.get("cache_hit") else 0.0 for x in results]
        chinese_hits = [1.0 if x.get("is_chinese") else 0.0 for x in results]
        number_hits = [1.0 if x.get("number_ok") else 0.0 for x in results if x.get("needs_number")]

        category_breakdown: list[dict[str, Any]] = []
        for category, bucket in category_buckets.items():
            category_breakdown.append(
                {
                    "category": category,
                    "count": len(bucket),
                    "pass_rate": round(sum(1 for x in bucket if x.get("passed")) / max(len(bucket), 1), 4),
                    "avg_score": round(sum(float(x.get("score", 0.0)) for x in bucket) / max(len(bucket), 1), 4),
                    "avg_latency_ms": round(
                        sum(float(x.get("latency_ms", 0.0)) for x in bucket) / max(len(bucket), 1),
                        2,
                    ),
                }
            )
        category_breakdown.sort(key=lambda x: x["avg_score"], reverse=True)

        report = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "dataset_size": len(dataset),
            "sample_size": len(results),
            "summary": {
                "pass_rate": round(sum(1 for x in passes if x) / max(len(passes), 1), 4),
                "avg_score": round(sum(scores) / max(len(scores), 1), 4),
                "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1), 2),
                "p95_latency_ms": round(self._percentile(latencies, 95), 2),
                "avg_answer_chars": round(
                    sum(int(x.get("answer_chars", 0)) for x in results) / max(len(results), 1),
                    1,
                ),
                "cache_hit_rate": round(sum(cache_hits) / max(len(cache_hits), 1), 4),
                "chinese_output_rate": round(sum(chinese_hits) / max(len(chinese_hits), 1), 4),
                "numeric_compliance_rate": round(sum(number_hits) / max(len(number_hits), 1), 4) if number_hits else 1.0,
                "judge_comment": self._judge_comment(results),
            },
            "category_breakdown": category_breakdown,
            "cases": sorted(results, key=lambda x: (x["passed"], x["score"]), reverse=False),
        }
        self._report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    def _score_case(self, item: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
        answer = str(detail.get("answer", "")).strip()
        answer_low = answer.lower()
        required = [str(x).strip() for x in item.get("required_keywords", []) if str(x).strip()]
        preferred = [str(x).strip() for x in item.get("preferred_keywords", []) if str(x).strip()]
        forbidden = [str(x).strip() for x in item.get("forbidden_keywords", []) if str(x).strip()]
        needs_number = bool(item.get("needs_number", False))

        matched_required = [kw for kw in required if kw.lower() in answer_low]
        matched_preferred = [kw for kw in preferred if kw.lower() in answer_low]
        hit_forbidden = [kw for kw in forbidden if kw.lower() in answer_low]

        required_score = len(matched_required) / max(len(required), 1)
        preferred_score = len(matched_preferred) / max(len(preferred), 1) if preferred else 1.0
        number_ok = (not needs_number) or bool(re.search(r"\d", answer))
        is_chinese = bool(re.search(r"[\u4e00-\u9fff]", answer))
        richness_score = min(1.0, len(answer) / 180.0)

        score = (
            required_score * 0.55
            + preferred_score * 0.1
            + (1.0 if number_ok else 0.0) * 0.15
            + (1.0 if is_chinese else 0.0) * 0.1
            + richness_score * 0.1
        )
        if hit_forbidden:
            score = min(score, 0.35)

        passed = score >= 0.72 and required_score >= 0.5 and not hit_forbidden
        timings = detail.get("timings_ms", {}) or {}

        return {
            "id": str(item.get("id", "")).strip(),
            "category": str(item.get("category", "未分类")).strip() or "未分类",
            "question": str(item.get("question", "")).strip(),
            "answer_preview": answer[:260],
            "answer_chars": len(answer),
            "latency_ms": float(timings.get("total", 0.0) or 0.0),
            "score": round(score, 4),
            "passed": passed,
            "required_keywords": required,
            "matched_required": matched_required,
            "missing_required": [kw for kw in required if kw not in matched_required],
            "preferred_keywords": preferred,
            "matched_preferred": matched_preferred,
            "forbidden_hits": hit_forbidden,
            "needs_number": needs_number,
            "number_ok": number_ok,
            "is_chinese": is_chinese,
            "cache_hit": bool((detail.get("cache", {}) or {}).get("hit", False)),
            "mode": str(detail.get("mode", "")),
        }

    @staticmethod
    def _percentile(values: list[float], pct: int) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * pct / 100) - 1))
        return float(ordered[index])

    @staticmethod
    def _judge_comment(results: list[dict[str, Any]]) -> str:
        if not results:
            return "当前还没有可用的评测结果。"
        pass_rate = sum(1 for x in results if x.get("passed")) / max(len(results), 1)
        avg_latency = sum(float(x.get("latency_ms", 0.0)) for x in results) / max(len(results), 1)
        avg_score = sum(float(x.get("score", 0.0)) for x in results) / max(len(results), 1)

        if pass_rate >= 0.85 and avg_latency <= 7000:
            return "问答链路已经具备较好的比赛展示稳定性，下一步应继续扩大图文混合场景的评测覆盖。"
        if pass_rate >= 0.7:
            return "问答链路已经达到可展示水平，但仍需针对低分问题补足知识和答案约束。"
        if avg_score >= 0.55:
            return "系统已经具备基本问答能力，但在稳定性和完整性上还需要继续打磨，尤其要修复低分样例。"
        return "当前问答链路仍偏原型态，建议优先修复低分样例，再进行正式答辩演示。"
