"""Tests for RetrievalService — search, hybrid_search, query expansion, caching."""
from __future__ import annotations

import pytest


class TestRetrievalServiceSearch:
    def test_search_returns_items_and_note(self, retrieval_service_factory):
        svc = retrieval_service_factory()
        items, note = svc.search("black hole", top_k=5)
        assert isinstance(items, list)
        assert isinstance(note, str)

    def test_search_top_k_clamped(self, retrieval_service_factory):
        svc = retrieval_service_factory()
        items, _ = svc.search("black hole", top_k=100)
        assert len(items) <= 20

    def test_search_top_k_minimum(self, retrieval_service_factory):
        svc = retrieval_service_factory()
        items, _ = svc.search("sun", top_k=0)
        assert isinstance(items, list)


class TestRetrievalServiceHybridSearch:
    def test_hybrid_search_returns_items(self, retrieval_service_factory):
        svc = retrieval_service_factory()
        items, note = svc.hybrid_search("neutron star", None, top_k=5)
        assert isinstance(items, list)
        assert isinstance(note, str)


class TestRetrievalServiceCaching:
    def test_repeated_search_uses_cache(self, retrieval_service_factory):
        svc = retrieval_service_factory()
        svc.search("galaxy", top_k=5)
        svc.search("galaxy", top_k=5)
        assert svc._cache_hits >= 1

    def test_cache_stats_tracked(self, retrieval_service_factory):
        svc = retrieval_service_factory()
        svc.search("planet", top_k=3)
        total = svc._cache_hits + svc._cache_misses
        assert total >= 1


class TestQueryExpansion:
    def test_expand_query_adds_terms(self, retrieval_service_factory):
        svc = retrieval_service_factory()
        expanded, terms = svc._expand_query("black hole")
        assert isinstance(expanded, str)
        assert len(expanded) >= len("black hole")
