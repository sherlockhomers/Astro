from __future__ import annotations

import re
from typing import Any

DOT = "\u3002"


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    text = str(val).strip()
    if not text or text.lower() in {"none", "nan", "n/a", "unknown", "null"}:
        return None
    text = re.sub(r"[^\d.eE+\-]", "", text.replace(",", ""))
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _normalize_sentence(sent: str) -> str:
    return re.sub(r"\s+", " ", sent).strip(" \t\r\n.;,!?，。；：")


def _join_sentences(sentences: list[str]) -> str:
    clean = [_normalize_sentence(s) for s in sentences if _normalize_sentence(s)]
    if not clean:
        return ""
    return DOT.join(clean) + DOT


def extract_relevant_sentences(body: str, question: str, max_sentences: int = 6) -> list[str]:
    if not body:
        return []
    parts = re.split(r"[。！？!?；;\n\r]+", body)
    sentences = [_normalize_sentence(s) for s in parts if len(_normalize_sentence(s)) >= 8]
    if not sentences:
        return []
    words = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9\-\._]{2,}", question.lower()))
    scored: list[tuple[float, int, str]] = []
    for idx, sent in enumerate(sentences):
        lower = sent.lower()
        score = 0.0
        for w in words:
            if w in lower:
                score += 2.0
        if idx <= 2:
            score += 0.3
        scored.append((score, idx, sent))
    scored.sort(key=lambda x: (-x[0], x[1]))
    keep = [x for x in scored[: max(1, max_sentences)] if x[0] > 0]
    keep.sort(key=lambda x: x[1])
    return [x[2] for x in keep]


def format_general_qa(
    question: str,
    entity_name: str,
    category: str,
    body_text: str,
    extra_facts: dict[str, str] | None = None,
) -> str:
    relevant = extract_relevant_sentences(body_text, question, max_sentences=4)
    chunks: list[str] = []
    if relevant:
        chunks.append(_join_sentences(relevant))
    elif body_text:
        brief = _normalize_sentence(body_text[:420])
        if brief:
            chunks.append(brief + DOT)

    if extra_facts:
        kv = [f"{k}: {v}" for k, v in extra_facts.items() if str(v).strip()]
        if kv:
            chunks.append("\u8865\u5145\u4fe1\u606f\uff1a" + "\uff1b".join(kv) + DOT)

    if chunks:
        return "\n\n".join(chunks)
    return (
        f"\u77e5\u8bc6\u5e93\u4e2d\u6682\u65f6\u6ca1\u6709 {entity_name} "
        "\u7684\u53ef\u4fe1\u8d44\u6599\uff0c\u53ef\u4ee5\u63d0\u4f9b\u66f4\u5177\u4f53\u7684\u63cf\u8ff0\u518d\u67e5\u8be2\u3002"
    )


def format_science_article(question: str, entity_name: str, category: str, body_text: str) -> str:
    if not body_text:
        return (
            f"{entity_name} \u662f\u5929\u6587\u5b66\u4e2d\u7684\u7814\u7a76\u5bf9\u8c61\uff0c"
            "\u4f46\u5f53\u524d\u8d44\u6599\u4e0d\u8db3\u4ee5\u7ed9\u51fa\u5b8c\u6574\u79d1\u666e\u89e3\u91ca\u3002"
        )
    relevant = extract_relevant_sentences(body_text, question, max_sentences=6)
    if relevant:
        return _join_sentences(relevant)
    brief = _normalize_sentence(body_text[:520])
    return (brief + DOT) if brief else (
        f"{entity_name} \u7684\u8d44\u6599\u53ef\u8bfb\u6027\u8f83\u4f4e\uff0c"
        "\u5efa\u8bae\u6362\u4e2a\u5173\u952e\u8bcd\u6216\u8865\u5145\u4e0a\u4e0b\u6587\u3002"
    )


def format_comparison(entity_a: dict[str, Any], entity_b: dict[str, Any], question: str) -> str:
    name_a = str(entity_a.get("name", "")).strip() or "A"
    name_b = str(entity_b.get("name", "")).strip() or "B"
    cat_a = str(entity_a.get("category", "")).strip()
    cat_b = str(entity_b.get("category", "")).strip()

    parts: list[str] = []
    if cat_a and cat_b:
        if cat_a == cat_b:
            parts.append(f"{name_a} \u4e0e {name_b} \u540c\u5c5e\u4e8e {cat_a}\uff0c\u4f46\u5b58\u5728\u5173\u952e\u5dee\u5f02{DOT}")
        else:
            parts.append(f"{name_a} \u5c5e\u4e8e {cat_a}\uff0c{name_b} \u5c5e\u4e8e {cat_b}{DOT}")

    body_a = _get_body(entity_a)
    body_b = _get_body(entity_b)
    sa = extract_relevant_sentences(body_a, f"{name_a} {question}", max_sentences=2) if body_a else []
    sb = extract_relevant_sentences(body_b, f"{name_b} {question}", max_sentences=2) if body_b else []
    if sa:
        parts.append(f"{name_a}\uff1a{_join_sentences(sa)}")
    if sb:
        parts.append(f"{name_b}\uff1a{_join_sentences(sb)}")

    metric_line = _compare_metrics(entity_a.get("raw", {}), entity_b.get("raw", {}), name_a, name_b)
    if metric_line:
        parts.append(metric_line)

    if parts:
        return "\n\n".join(parts)
    return f"\u6682\u65f6\u7f3a\u5c11 {name_a} \u4e0e {name_b} \u7684\u53ef\u6bd4\u5bf9\u8d44\u6599\u3002"


def format_entity_detail(entity: dict[str, Any], question: str) -> str:
    name = str(entity.get("name", "")).strip() or "\u76ee\u6807\u5929\u4f53"
    body = _get_body(entity)
    if body:
        sents = extract_relevant_sentences(body, question, max_sentences=5)
        if sents:
            return _join_sentences(sents)
        brief = _normalize_sentence(body[:500])
        if brief:
            return brief + DOT

    facts = _extract_key_facts(entity.get("raw", {}))
    if facts:
        items = [f"{k}: {v}" for k, v in facts.items()]
        return f"{name} \u7684\u5173\u952e\u4fe1\u606f\uff1a" + "\uff1b".join(items) + DOT

    return f"\u5f53\u524d\u6ca1\u6709 {name} \u7684\u7ed3\u6784\u5316\u8be6\u60c5\u8bb0\u5f55\u3002"


def format_relation_path(source: str, target: str, path: list[dict[str, str]]) -> str:
    if not path:
        return (
            f"\u5728\u5f53\u524d\u56fe\u8c31\u4e2d\uff0c\u672a\u627e\u5230 {source} \u5230 {target} "
            f"\u7684\u6709\u6548\u8def\u5f84{DOT}"
        )
    steps: list[str] = []
    for idx, edge in enumerate(path, start=1):
        rel = str(edge.get("rel", "RELATED_TO")).replace("REVERSE_", "REVERSE ").replace("_", " ")
        steps.append(f"{idx}. {edge.get('from', '?')} -[{rel}]-> {edge.get('to', '?')}")
    return (
        f"\u627e\u5230 {source} \u5230 {target} \u7684 {len(path)} \u8df3\u8def\u5f84\uff1a\n"
        + "\n".join(steps)
    )


def format_no_result(question: str) -> str:
    return (
        f"\u77e5\u8bc6\u5e93\u4e2d\u6682\u672a\u627e\u5230\u4e0e\u300c{question}\u300d\u9ad8\u76f8\u5173\u7684\u6761\u76ee{DOT}"
        "\u53ef\u4ee5\u6539\u7528\u66f4\u5177\u4f53\u7684\u5b9e\u4f53\u540d\u79f0\u6216\u63d0\u4f9b\u7ea6\u675f\u6761\u4ef6\u3002"
    )


def _get_body(entity: dict[str, Any]) -> str:
    body = str(entity.get("description", "")).strip()
    if body:
        return body
    raw = entity.get("raw", {})
    for key in (
        "\u6b63\u6587",
        "\u5185\u5bb9",
        "\u63cf\u8ff0",
        "description",
        "summary",
        "body",
        "content",
        "text",
    ):
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _extract_key_facts(raw: dict[str, Any]) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    norm = {str(k).strip().lower(): v for k, v in raw.items()}
    mapping = {
        "\u8d28\u91cf": ["mass", "mass (earth masses)", "\u8d28\u91cf", "pl_bmasse"],
        "\u534a\u5f84": ["radius", "radius (km)", "\u534a\u5f84", "pl_rade"],
        "\u8f68\u9053\u5468\u671f": ["period (days)", "orbital_period", "\u8f68\u9053\u5468\u671f", "pl_orbper"],
        "\u53d1\u73b0\u5e74\u4efd": ["discovery year", "disc year", "disc_year", "\u53d1\u73b0\u5e74\u4efd"],
        "\u53d1\u73b0\u65b9\u5f0f": ["discovery method", "discovery_method", "\u53d1\u73b0\u65b9\u5f0f"],
        "\u8ddd\u79bb": ["distance", "distance (ly)", "distance_pc", "\u8ddd\u79bb", "sy_dist"],
    }
    out: dict[str, str] = {}
    for label, keys in mapping.items():
        for k in keys:
            v = norm.get(k.lower())
            if v is None:
                continue
            txt = str(v).strip()
            if txt and txt.lower() not in {"nan", "none", "null", "unknown"}:
                out[label] = txt
                break
    return out


def _compare_metrics(raw_a: dict[str, Any], raw_b: dict[str, Any], name_a: str, name_b: str) -> str:
    fields = [
        ("\u8d28\u91cf", ["mass", "mass (earth masses)", "\u8d28\u91cf", "pl_bmasse"]),
        ("\u534a\u5f84", ["radius", "radius (km)", "\u534a\u5f84", "pl_rade"]),
        ("\u8f68\u9053\u5468\u671f", ["period (days)", "\u8f68\u9053\u5468\u671f", "pl_orbper"]),
        ("\u8ddd\u79bb", ["distance", "distance_pc", "\u8ddd\u79bb", "sy_dist"]),
    ]
    norm_a = {str(k).strip().lower(): v for k, v in (raw_a or {}).items()}
    norm_b = {str(k).strip().lower(): v for k, v in (raw_b or {}).items()}
    chunks: list[str] = []
    for label, keys in fields:
        va: Any = None
        vb: Any = None
        for key in keys:
            if va is None and norm_a.get(key.lower()) not in (None, "", "nan", "None"):
                va = norm_a.get(key.lower())
            if vb is None and norm_b.get(key.lower()) not in (None, "", "nan", "None"):
                vb = norm_b.get(key.lower())
        if va is not None and vb is not None:
            chunks.append(f"{label}\uff1a{name_a}={va}\uff0c{name_b}={vb}")
    if not chunks:
        return ""
    return "\u5173\u952e\u6570\u503c\u5bf9\u6bd4\uff1a" + "\uff1b".join(chunks) + DOT
