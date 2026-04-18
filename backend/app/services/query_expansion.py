# 检索时的同义词扩展。举例：用户搜「黑洞」，自动把「事件视界」「奇点」也拼到查询里，
# 给向量/BM25 多几个抓手，召回率会舒服一些。规则走配置文件，不写死。
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

logger = logging.getLogger("astrograph")


@dataclass(frozen=True)
class ExpansionRule:
    triggers: tuple[str, ...]
    expansions: tuple[str, ...]


def _parse(payload: object) -> list[ExpansionRule]:
    if isinstance(payload, dict):
        payload = payload.get("rules", [])
    if not isinstance(payload, list):
        return []
    rules: list[ExpansionRule] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        triggers = tuple(str(x).strip() for x in item.get("triggers", []) if str(x).strip())
        expansions = tuple(str(x).strip() for x in item.get("expansions", []) if str(x).strip())
        if triggers and expansions:
            rules.append(ExpansionRule(triggers=triggers, expansions=expansions))
    return rules


def load_rules(path: str | Path) -> list[ExpansionRule]:
    if not path:
        return []
    p = Path(path)
    if not p.exists() or not p.is_file():
        return []
    try:
        raw = p.read_text(encoding="utf-8", errors="ignore")
        return _parse(json.loads(raw))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("query_expansion: failed to load %s: %s", p, exc)
        return []


class QueryExpander:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path) if path else None
        self._rules: list[ExpansionRule] = []
        self._lock = Lock()
        self.reload()

    def reload(self) -> int:
        rules = load_rules(self._path) if self._path else []
        with self._lock:
            self._rules = rules
        if rules:
            logger.info("query_expansion: loaded %d rules from %s", len(rules), self._path)
        return len(rules)

    def expand(self, query: str) -> tuple[str, list[str]]:
        raw = str(query or "").strip()
        if not raw:
            return "", []
        lower = raw.lower()
        additions: list[str] = []
        with self._lock:
            rules = list(self._rules)
        for rule in rules:
            if any(trigger.lower() in lower for trigger in rule.triggers):
                for item in rule.expansions:
                    if item.lower() not in lower and item not in additions:
                        additions.append(item)
        if not additions:
            return raw, []
        expanded = f"{raw} {' '.join(additions[:6])}".strip()
        return expanded, additions
