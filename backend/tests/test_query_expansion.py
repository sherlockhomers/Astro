# QueryExpander 的测试：规则读取、扩展、重载
from __future__ import annotations

import json
from pathlib import Path

from app.services.query_expansion import ExpansionRule, QueryExpander, load_rules


class TestLoadRules:
    def test_loads_nested_rules(self, tmp_path: Path):
        path = tmp_path / "rules.json"
        path.write_text(
            json.dumps(
                {
                    "rules": [
                        {"triggers": ["黑洞"], "expansions": ["事件视界", "奇点"]},
                        {"triggers": ["火星"], "expansions": ["探测车"]},
                    ]
                }
            ),
            encoding="utf-8",
        )
        rules = load_rules(path)
        assert len(rules) == 2
        assert rules[0].triggers == ("黑洞",)
        assert rules[0].expansions == ("事件视界", "奇点")

    def test_loads_direct_list(self, tmp_path: Path):
        path = tmp_path / "rules.json"
        path.write_text(
            json.dumps(
                [{"triggers": ["x"], "expansions": ["y"]}]
            ),
            encoding="utf-8",
        )
        rules = load_rules(path)
        assert len(rules) == 1

    def test_skips_incomplete_rules(self, tmp_path: Path):
        path = tmp_path / "rules.json"
        # 只留完整的那条
        path.write_text(
            json.dumps(
                [
                    {"triggers": ["a"]},
                    {"expansions": ["b"]},
                    {"triggers": [], "expansions": ["x"]},
                    {"triggers": ["ok"], "expansions": ["yes"]},
                ]
            ),
            encoding="utf-8",
        )
        rules = load_rules(path)
        assert len(rules) == 1
        assert rules[0].triggers == ("ok",)

    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert load_rules(tmp_path / "nope.json") == []

    def test_malformed_json_returns_empty(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{ not json }", encoding="utf-8")
        assert load_rules(path) == []


class TestQueryExpander:
    def test_no_rules_returns_original(self, tmp_path: Path):
        qe = QueryExpander(path=tmp_path / "nonexistent.json")
        expanded, adds = qe.expand("任何查询")
        assert expanded == "任何查询"
        assert adds == []

    def test_expansion_appends_unique_terms(self, tmp_path: Path):
        path = tmp_path / "r.json"
        path.write_text(
            json.dumps({"rules": [{"triggers": ["黑洞"], "expansions": ["事件视界", "奇点"]}]}),
            encoding="utf-8",
        )
        qe = QueryExpander(path=path)
        expanded, adds = qe.expand("黑洞是什么")
        assert "事件视界" in expanded
        assert "奇点" in expanded
        assert adds == ["事件视界", "奇点"]

    def test_already_present_term_not_duplicated(self, tmp_path: Path):
        path = tmp_path / "r.json"
        path.write_text(
            json.dumps({"rules": [{"triggers": ["黑洞"], "expansions": ["事件视界", "奇点"]}]}),
            encoding="utf-8",
        )
        qe = QueryExpander(path=path)
        # 查询里已经写过"奇点"了，就别再拼一遍
        expanded, adds = qe.expand("黑洞和奇点的关系")
        assert "事件视界" in adds
        assert "奇点" not in adds

    def test_case_insensitive_trigger(self, tmp_path: Path):
        path = tmp_path / "r.json"
        path.write_text(
            json.dumps({"rules": [{"triggers": ["jupiter"], "expansions": ["Io", "Europa"]}]}),
            encoding="utf-8",
        )
        qe = QueryExpander(path=path)
        expanded, adds = qe.expand("JUPITER's moons")
        assert "Io" in adds
        assert "Europa" in adds

    def test_empty_query_returns_empty(self, tmp_path: Path):
        qe = QueryExpander(path=tmp_path / "nope.json")
        assert qe.expand("") == ("", [])
        assert qe.expand("   ") == ("", [])

    def test_reload_picks_up_changes(self, tmp_path: Path):
        path = tmp_path / "r.json"
        path.write_text(
            json.dumps({"rules": [{"triggers": ["x"], "expansions": ["v1"]}]}),
            encoding="utf-8",
        )
        qe = QueryExpander(path=path)
        _, adds = qe.expand("xxx")
        assert adds == ["v1"]

        path.write_text(
            json.dumps({"rules": [{"triggers": ["x"], "expansions": ["v2"]}]}),
            encoding="utf-8",
        )
        qe.reload()
        _, adds2 = qe.expand("xxx")
        assert adds2 == ["v2"]


class TestBundledDefaultExpansionRules:
    def test_default_expansion_file_exists(self):
        path = Path(__file__).resolve().parent.parent / "data" / "query_expansion_rules.default.json"
        assert path.exists()
        rules = load_rules(path)
        assert len(rules) >= 5
