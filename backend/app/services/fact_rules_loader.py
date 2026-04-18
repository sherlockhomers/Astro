# 天文事实护栏：RAG 答错或偏题时，拿这里的固定答复兜底。
# 规则本身从 JSONL 读，不写死在代码里，运营可以直接改文件后调 reload。
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Iterable, Sequence

logger = logging.getLogger("astrograph")


@dataclass(frozen=True)
class FactRule:
    all_of: tuple[str, ...]
    any_of: tuple[str, ...]
    answer: str

    def matches(self, text: str) -> bool:
        # 大小写不敏感，关键词是子串就算命中；传原文进来就行
        text_lower = (text or "").lower()
        if self.all_of and not all(kw.lower() in text_lower for kw in self.all_of):
            return False
        if self.any_of and not any(kw.lower() in text_lower for kw in self.any_of):
            return False
        return True


@dataclass
class FactRuleBundle:
    rules: list[FactRule] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def match(self, question: str) -> str:
        if not question or not self.rules:
            return ""
        for rule in self.rules:
            if rule.matches(question):
                return rule.answer
        return ""


def _parse_payload(raw_list: Iterable[object]) -> list[FactRule]:
    parsed: list[FactRule] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        answer = str(item.get("answer", "")).strip()
        if not answer:
            continue
        all_of = tuple(str(x) for x in item.get("all_of", []) if str(x).strip())
        any_of = tuple(str(x) for x in item.get("any_of", []) if str(x).strip())
        parsed.append(FactRule(all_of=all_of, any_of=any_of, answer=answer))
    return parsed


def load_rules_from_path(path: str | Path) -> list[FactRule]:
    if not path:
        return []
    p = Path(path)
    if not p.exists() or not p.is_file():
        return []
    try:
        raw = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        logger.warning("fact_rules: failed to read %s: %s", p, exc)
        return []

    if p.suffix.lower() == ".jsonl":
        items: list[object] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("fact_rules: invalid JSONL line in %s: %s", p.name, exc)
        return _parse_payload(items)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("fact_rules: invalid JSON in %s: %s", p.name, exc)
        return []
    if isinstance(payload, list):
        return _parse_payload(payload)
    return []


class FactRulesLoader:
    # 多路径按顺序合并；reload 可以热更新规则（运行时不用重启进程）
    def __init__(self, paths: Sequence[str | Path]) -> None:
        self._paths: tuple[Path, ...] = tuple(Path(p) for p in paths if p)
        self._bundle: FactRuleBundle = FactRuleBundle()
        self._lock = Lock()
        self.reload()

    @property
    def bundle(self) -> FactRuleBundle:
        with self._lock:
            return self._bundle

    def reload(self) -> FactRuleBundle:
        rules: list[FactRule] = []
        sources: list[str] = []
        for path in self._paths:
            loaded = load_rules_from_path(path)
            if loaded:
                rules.extend(loaded)
                sources.append(str(path))
                logger.info("fact_rules: loaded %d rules from %s", len(loaded), path)
        bundle = FactRuleBundle(rules=rules, sources=sources)
        with self._lock:
            self._bundle = bundle
        return bundle

    def match(self, question: str) -> str:
        return self.bundle.match(question)
