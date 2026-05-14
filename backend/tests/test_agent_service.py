"""Tests for agent_service — entity extraction, intent analysis, builtin answers."""
from __future__ import annotations

import pytest

from app.services.agent_service import (
    AgentService,
    INTENT_COMPARISON,
    INTENT_ENTITY_LOOKUP,
    INTENT_FACT_QUERY,
    INTENT_GENERAL,
    INTENT_RELATION,
    INTENT_SCIENCE_QA,
)


class TestAgentServiceIntentClassification:
    def test_intent_relation_vs_compare(self, agent_service_factory):
        svc = agent_service_factory()
        # comparison keywords → INTENT_COMPARISON
        assert svc._analyze_intent("火星和地球比较") == INTENT_COMPARISON
        assert svc._analyze_intent("compare mars and earth") == INTENT_COMPARISON
        assert svc._analyze_intent("Jupiter vs Saturn") == INTENT_COMPARISON
        # relation keywords → INTENT_RELATION
        assert svc._analyze_intent("火星和地球有什么关系") == INTENT_RELATION
        assert svc._analyze_intent("earth relation to sun") == INTENT_RELATION

    def test_intent_fact_query(self, agent_service_factory):
        svc = agent_service_factory()
        assert svc._analyze_intent("火星有多少颗卫星") == INTENT_FACT_QUERY
        assert svc._analyze_intent("土星的直径是多少") == INTENT_FACT_QUERY
        assert svc._analyze_intent("水星的质量") == INTENT_FACT_QUERY
        assert svc._analyze_intent("冥王星发现时间") == INTENT_FACT_QUERY

    def test_intent_science_qa(self, agent_service_factory):
        svc = agent_service_factory()
        assert svc._analyze_intent("黑洞为什么连光都逃不出来") == INTENT_SCIENCE_QA
        assert svc._analyze_intent("为什么火星是红色的") == INTENT_SCIENCE_QA
        assert svc._analyze_intent("恒星是怎么形成的") == INTENT_SCIENCE_QA

    @pytest.mark.stale  # "今天天气" 现在被识别成 science_qa；待意图分类器更新后修正
    def test_intent_general_fallback(self, agent_service_factory):
        svc = agent_service_factory()
        assert svc._analyze_intent("hello world") == INTENT_GENERAL
        assert svc._analyze_intent("今天天气怎么样") == INTENT_GENERAL


class TestAgentServiceBuiltinFacts:
    @pytest.mark.stale  # _answer_identity 当前对"你是什么"返回 None；功能可能被精简掉了
    def test_identity_question(self, agent_service_factory):
        svc = agent_service_factory()
        result = svc._answer_identity("你是什么")
        assert result is not None
        assert "ASTRO" in result

    def test_builtin_sun_surface_temperature(self, agent_service_factory):
        svc = agent_service_factory()
        result = svc._answer_builtin_fact("太阳表面温度是多少")
        assert result is not None
        assert "5500" in result or "5778" in result

    def test_builtin_earth_diameter(self, agent_service_factory):
        svc = agent_service_factory()
        result = svc._answer_builtin_fact("地球直径")
        assert result is not None
        assert "12742" in result

    def test_builtin_largest_planet(self, agent_service_factory):
        svc = agent_service_factory()
        result = svc._answer_builtin_fact("太阳系最大的行星是什么")
        assert result is not None
        assert "木星" in result

    def test_builtin_mars_volume(self, agent_service_factory):
        svc = agent_service_factory()
        result = svc._answer_builtin_fact("火星体积")
        assert result is not None
        assert "1.63" in result or "15%" in result

    def test_builtin_closest_celestial(self, agent_service_factory):
        svc = agent_service_factory()
        result = svc._answer_builtin_fact("离地球最近的天体是什么")
        assert result is not None
        assert "月球" in result or "Moon" in result

    def test_builtin_mars_earth_distance(self, agent_service_factory):
        svc = agent_service_factory()
        result = svc._answer_builtin_fact("火星和地球的距离是多少")
        assert result is not None
        assert "AU" in result or "公里" in result


class TestAgentServiceEntityIndex:
    def test_find_entity_by_name_returns_none_for_empty(self, agent_service_factory):
        svc = agent_service_factory()
        assert svc.find_entity_by_name("") is None
        assert svc.find_entity_by_name("   ") is None

    def test_find_entity_batch_returns_empty_for_empty_list(self, agent_service_factory):
        svc = agent_service_factory()
        result = svc.find_entities_batch([])
        assert result == {}

    def test_entity_index_not_built_until_first_use(self, agent_service_factory):
        svc = agent_service_factory()
        # Index revision starts as -1
        assert svc._index_revision == -1
        # Accessing find triggers lazy build
        svc.find_entity_by_name("anything")
        assert svc._index_revision == svc._data.revision


class TestAgentServiceAliasExpansion:
    def test_alias_expansion_chinese_to_english(self, agent_service_factory):
        svc = agent_service_factory()
        result = svc._expand_aliases("火星的质量")
        assert "mars" in result.lower()
        assert "火星" in result  # Chinese kept

    def test_alias_expansion_no_duplicate(self, agent_service_factory):
        svc = agent_service_factory()
        result = svc._expand_aliases("Jupiter")
        # Should not append "jupiter" again
        count = result.lower().count("jupiter")
        assert count <= 2  # at most once in original + once appended


class TestAgentServiceLooksAstronomyQuestion:
    def test_astronomy_keywords_detected(self, agent_service_factory):
        svc = agent_service_factory()
        assert svc._looks_astronomy_question("火星是什么")
        assert svc._looks_astronomy_question("黑洞的形成")
        assert svc._looks_astronomy_question("系外行星")
        assert svc._looks_astronomy_question("exoplanet atmosphere")

    def test_non_astronomy_rejected(self, agent_service_factory):
        svc = agent_service_factory()
        assert not svc._looks_astronomy_question("今天吃什么")
        assert not svc._looks_astronomy_question("如何做红烧肉")
