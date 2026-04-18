# 疑问类型识别 + 答案格式校验的测试。
# 这块是 orchestrator 面对"谁/何时/多少"类问题时的一道防线，回归了会直接让答案质量塌方。

from __future__ import annotations

import pytest

from app.services.adaptive_agent_orchestrator import AdaptiveAgentOrchestrator as O


class TestQuestionTypeClassifier:
    @pytest.mark.parametrize("question,expected", [
        ("谁是第一个到月球的国家", "who"),
        ("阿波罗11号是哪国发射的", "who"),
        ("哪国最先发射了人造卫星", "who"),
        ("这个任务由谁负责", "who"),
        ("Who was the first on the Moon?", "who"),
    ])
    def test_who_questions(self, question, expected):
        assert O._classify_question_type(question) == expected

    @pytest.mark.parametrize("question,expected", [
        ("哈勃望远镜什么时候发射的", "when"),
        ("韦伯望远镜是哪年升空的", "when"),
        ("空间站大概何时建成", "when"),
        ("嫦娥四号几月登月的", "when"),
        ("When was JWST launched?", "when"),
    ])
    def test_when_questions(self, question, expected):
        assert O._classify_question_type(question) == expected

    @pytest.mark.parametrize("question,expected", [
        ("木星有多少颗卫星", "count"),
        ("火星距离地球多远", "count"),
        ("太阳直径多大", "count"),
        ("How many moons does Saturn have?", "count"),
    ])
    def test_count_questions(self, question, expected):
        assert O._classify_question_type(question) == expected

    def test_why_question(self):
        assert O._classify_question_type("黑洞为什么会吸引光") == "why"

    def test_how_question(self):
        assert O._classify_question_type("怎么观测暗物质") == "how"

    def test_general_fallback(self):
        # 没有疑问代词的陈述型查询都算 general
        assert O._classify_question_type("介绍一下银河系") == "general"


class TestAnswerShapeValidator:
    # 答得头头是道但没答到点子上的情况，这里要能识别出来

    def test_who_answer_without_country_fails(self):
        bad = "月球是地球的天然卫星，距离约38万公里，表面有许多环形山和月海。"
        assert O._answer_has_expected_shape(bad, "who") is False

    def test_who_answer_with_country_passes(self):
        good = "美国是第一个登陆月球的国家，1969 年阿波罗 11 号完成这一壮举。"
        assert O._answer_has_expected_shape(good, "who") is True

    def test_who_answer_with_mission_name_passes(self):
        good = "是阿波罗 11 号任务首次完成载人登月。"
        assert O._answer_has_expected_shape(good, "who") is True

    def test_when_answer_without_year_fails(self):
        bad = "哈勃太空望远镜是美国 NASA 发射的重要空间观测设备。"
        assert O._answer_has_expected_shape(bad, "when") is False

    def test_when_answer_with_year_passes(self):
        good = "1990 年 4 月 24 日，哈勃望远镜由航天飞机送入太空。"
        assert O._answer_has_expected_shape(good, "when") is True

    def test_count_answer_without_number_fails(self):
        bad = "木星有非常多的卫星，是太阳系中卫星最多的行星。"
        assert O._answer_has_expected_shape(bad, "count") is False

    def test_count_answer_with_number_passes(self):
        good = "木星目前已发现 95 颗卫星，其中最大的是伽利略四卫星。"
        assert O._answer_has_expected_shape(good, "count") is True

    def test_general_always_passes(self):
        assert O._answer_has_expected_shape("任何文本", "general") is True
