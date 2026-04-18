# FactRulesLoader 的测试：读 JSON / 匹配 / 热重载都跑一遍
from __future__ import annotations

import json
from pathlib import Path

from app.services.fact_rules_loader import FactRule, FactRuleBundle, FactRulesLoader, load_rules_from_path


class TestFactRule:
    def test_matches_all_of_only(self):
        rule = FactRule(all_of=("黑洞",), any_of=(), answer="x")
        assert rule.matches("黑洞是什么")
        assert not rule.matches("中子星是什么")

    def test_matches_any_of_only(self):
        rule = FactRule(all_of=(), any_of=("光", "逃逸"), answer="x")
        assert rule.matches("光能逃离黑洞吗")
        assert rule.matches("那么逃逸速度是多少")
        assert not rule.matches("引力波是什么")

    def test_matches_all_and_any_combined(self):
        rule = FactRule(all_of=("火星",), any_of=("距离",), answer="x")
        assert rule.matches("火星离地球的距离")
        assert not rule.matches("火星的温度")   # 没命中 any_of
        assert not rule.matches("太阳距离地球")  # 没命中 all_of

    def test_case_insensitive(self):
        rule = FactRule(all_of=("MARS",), any_of=(), answer="x")
        assert rule.matches("MARS is red")
        assert rule.matches("mars is red")
        assert rule.matches("Mars rover")


class TestFactRuleBundle:
    def test_empty_bundle_returns_empty(self):
        bundle = FactRuleBundle()
        assert bundle.match("任何问题") == ""

    def test_match_returns_first_rule(self):
        r1 = FactRule(all_of=("火星",), any_of=(), answer="answer-1")
        r2 = FactRule(all_of=("火星",), any_of=("距离",), answer="answer-2")
        bundle = FactRuleBundle(rules=[r1, r2])
        # 顺序很关键：r1 无条件命中"火星"，r2 就轮不到
        assert bundle.match("火星距离") == "answer-1"

    def test_empty_question_returns_empty(self):
        r1 = FactRule(all_of=("x",), any_of=(), answer="a")
        bundle = FactRuleBundle(rules=[r1])
        assert bundle.match("") == ""
        assert bundle.match(None) == ""  # type: ignore[arg-type]


class TestLoadFromPath:
    def test_loads_jsonl(self, tmp_path: Path):
        path = tmp_path / "rules.jsonl"
        # 空行和以 # 开头的行应当被忽略，方便人写注释
        path.write_text(
            "\n".join(
                [
                    json.dumps({"all_of": ["a"], "any_of": [], "answer": "A"}, ensure_ascii=False),
                    json.dumps({"all_of": [], "any_of": ["b"], "answer": "B"}, ensure_ascii=False),
                    "  ",
                    "# 这是文件里的注释",
                ]
            ),
            encoding="utf-8",
        )
        rules = load_rules_from_path(path)
        assert len(rules) == 2
        assert rules[0].answer == "A"
        assert rules[1].answer == "B"

    def test_loads_json_list(self, tmp_path: Path):
        path = tmp_path / "rules.json"
        path.write_text(
            json.dumps(
                [
                    {"all_of": ["x"], "any_of": [], "answer": "X"},
                    {"all_of": [], "any_of": ["y"], "answer": "Y"},
                ]
            ),
            encoding="utf-8",
        )
        rules = load_rules_from_path(path)
        assert len(rules) == 2

    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert load_rules_from_path(tmp_path / "nope.jsonl") == []

    def test_empty_path_returns_empty(self):
        assert load_rules_from_path("") == []

    def test_skips_entries_without_answer(self, tmp_path: Path):
        path = tmp_path / "rules.jsonl"
        path.write_text(
            "\n".join(
                [
                    json.dumps({"all_of": ["a"], "any_of": [], "answer": ""}),
                    json.dumps({"all_of": ["b"], "any_of": [], "answer": "OK"}),
                ]
            ),
            encoding="utf-8",
        )
        rules = load_rules_from_path(path)
        assert len(rules) == 1
        assert rules[0].answer == "OK"

    def test_handles_invalid_jsonl_line(self, tmp_path: Path, caplog):
        path = tmp_path / "rules.jsonl"
        path.write_text(
            '{"all_of": ["a"], "answer": "A"}\nNOT JSON\n{"all_of": ["b"], "answer": "B"}\n',
            encoding="utf-8",
        )
        rules = load_rules_from_path(path)
        assert len(rules) == 2


class TestFactRulesLoaderMerge:
    def test_multiple_files_merged_in_order(self, tmp_path: Path):
        default = tmp_path / "default.jsonl"
        local = tmp_path / "local.jsonl"
        default.write_text(
            json.dumps({"all_of": ["a"], "answer": "default"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        local.write_text(
            json.dumps({"all_of": ["b"], "answer": "local"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        loader = FactRulesLoader(paths=[str(default), str(local)])
        assert len(loader.bundle.rules) == 2
        # default 列在前面，两条都能命中时先用它
        assert loader.match("aaa bbb") == "default"
        assert loader.match("只有 bbb") == "local"

    def test_skip_blank_paths(self):
        loader = FactRulesLoader(paths=["", "   ", None])  # type: ignore[list-item]
        assert loader.bundle.rules == []

    def test_reload_picks_up_changes(self, tmp_path: Path):
        path = tmp_path / "rules.jsonl"
        path.write_text(
            json.dumps({"all_of": ["a"], "answer": "v1"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        loader = FactRulesLoader(paths=[str(path)])
        assert loader.match("aaa") == "v1"

        path.write_text(
            json.dumps({"all_of": ["a"], "answer": "v2"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        loader.reload()
        assert loader.match("aaa") == "v2"


class TestBundledDefaultRules:
    # 随代码分发的那份默认规则文件，至少得能读出来、能匹上几个常见问题

    def test_default_rules_file_exists_and_loads(self):
        path = Path(__file__).resolve().parent.parent / "data" / "domain_fact_rules.default.jsonl"
        assert path.exists(), f"默认规则文件缺失: {path}"
        rules = load_rules_from_path(path)
        assert len(rules) >= 10
        assert all(r.answer for r in rules)

    def test_default_rules_match_common_astronomy_questions(self):
        path = Path(__file__).resolve().parent.parent / "data" / "domain_fact_rules.default.jsonl"
        loader = FactRulesLoader(paths=[str(path)])
        samples = [
            "火星距离地球多远",
            "黑洞时间膨胀效应",
            "银河系多大",
        ]
        hits = [bool(loader.match(q)) for q in samples]
        assert sum(hits) >= 2, f"默认规则应覆盖常见问题，命中：{hits}"
