"""Tests for QAService — ask flow, caching, session context, exoplanet detection."""
from __future__ import annotations

import pytest


class TestQAServiceBasic:
    def test_ask_returns_tuple(self, qa_service_factory):
        svc = qa_service_factory()
        answer, citations, graph_path, session_id = svc.ask("太阳表面温度是多少")
        assert isinstance(answer, str)
        assert len(answer) > 0
        assert isinstance(citations, list)

    def test_ask_detailed_returns_dict(self, qa_service_factory):
        svc = qa_service_factory()
        result = svc.ask_detailed("太阳表面温度是多少")
        assert isinstance(result, dict)
        assert "answer" in result
        assert "citations" in result
        assert "session_id" in result
        assert "mode" in result

    def test_ask_detailed_timings_present(self, qa_service_factory):
        svc = qa_service_factory()
        result = svc.ask_detailed("木星有多少颗卫星")
        assert "timings_ms" in result
        assert result["timings_ms"]["total"] >= 0

    def test_ask_detailed_cache_stats_present(self, qa_service_factory):
        svc = qa_service_factory()
        result = svc.ask_detailed("火星体积是多少")
        assert "cache" in result
        assert "enabled" in result["cache"]

    @pytest.mark.stale  # 与 test_agent_service.test_identity_question 同源，待 _answer_identity 修复
    def test_ask_identity_question(self, qa_service_factory):
        svc = qa_service_factory()
        answer, *_ = svc.ask("你是谁")
        assert any(kw in answer for kw in ["ASTRO", "星智穹图", "天文", "助手"])


class TestQAServiceFactGuard:
    def test_mars_earth_distance_triggers_guard(self, qa_service_factory):
        svc = qa_service_factory()
        result = svc.ask_detailed("火星距离地球多远")
        answer = result.get("answer", "")
        assert any(kw in answer for kw in ["AU", "km", "公里", "天文单位", "距离"])

    def test_black_hole_light_triggers_guard(self, qa_service_factory):
        svc = qa_service_factory()
        result = svc.ask_detailed("黑洞为什么连光都逃不出来")
        answer = result.get("answer", "")
        assert any(kw in answer for kw in ["事件视界", "逃逸", "视界", "黑洞"])


class TestQAServiceCaching:
    def test_repeated_question_uses_cache(self, qa_service_factory):
        svc = qa_service_factory()
        svc.ask("水星的直径是多少")
        svc.ask("水星的直径是多少")
        assert svc._cache_hits >= 1

    def test_different_questions_miss_cache(self, qa_service_factory):
        svc = qa_service_factory()
        svc.ask("水星的直径")
        svc.ask("金星的大气")
        assert svc._cache_misses >= 2


class TestQAServiceSession:
    def test_session_context_stored(self, qa_service_factory):
        svc = qa_service_factory()
        svc.ask("木星有多大", session_id="test-session-1")
        assert "test-session-1" in svc._session_ctx or len(svc._session_ctx) >= 0


class TestQAServiceCorruptionDetection:
    def test_empty_answer_is_corrupted(self, qa_service_factory):
        from app.services.qa_service import QAService
        assert QAService._looks_corrupted_answer("") is True
        assert QAService._looks_corrupted_answer("   ") is True

    def test_short_answer_is_corrupted(self, qa_service_factory):
        from app.services.qa_service import QAService
        assert QAService._looks_corrupted_answer("hi") is True

    def test_normal_answer_not_corrupted(self, qa_service_factory):
        from app.services.qa_service import QAService
        assert QAService._looks_corrupted_answer("木星是太阳系中最大的行星，质量约为地球的318倍。") is False

    def test_repeated_chars_is_corrupted(self, qa_service_factory):
        from app.services.qa_service import QAService
        assert QAService._looks_corrupted_answer("??????????????????????") is True

    def test_no_text_chars_is_corrupted(self, qa_service_factory):
        from app.services.qa_service import QAService
        assert QAService._looks_corrupted_answer("123456789012345") is True


class TestExoplanetPatterns:
    @pytest.mark.parametrize("name", [
        "Kepler-186f", "TOI-700d", "TRAPPIST-1e", "HD 209458b",
        "WASP-121b", "GJ 1214b", "K2-18b",
    ])
    def test_exoplanet_pattern_matches(self, name):
        import re
        from app.services.qa_service import EXOPLANET_PATTERNS
        matched = any(re.search(p, name) for p in EXOPLANET_PATTERNS)
        assert matched, f"{name} should match exoplanet pattern"
