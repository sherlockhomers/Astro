"""Tests for graph_service — adjacency cache, path finding, visualization."""
from __future__ import annotations

import pytest

from app.services.graph_service import GraphService


class TestGraphServiceStatus:
    def test_status_defaults(self, data_service_factory):
        ds = data_service_factory()
        svc = GraphService(ds)
        status = svc.status()
        assert status["graph_ready"] is False
        assert status["nodes_count"] == 0
        assert status["relations_count"] == 0


class TestGraphServiceAdjacencyCache:
    def test_adjacency_built_once_per_graph(self, data_service_factory, sample_csv_file):
        ds = data_service_factory()
        ds.load_data_source(str(sample_csv_file.parent), [])
        svc = GraphService(ds)
        svc.build_graph(str(sample_csv_file.parent), [], write_neo4j=False)
        # First call builds
        adj1 = svc._build_adjacency()
        # Second call returns cached
        adj2 = svc._build_adjacency()
        assert adj1 is adj2  # Same object reference

    def test_adjacency_invalidated_on_rebuild(self, data_service_factory, sample_csv_file):
        ds = data_service_factory()
        svc = GraphService(ds)
        svc.build_graph(str(sample_csv_file.parent), [], write_neo4j=False)
        svc._build_adjacency()
        assert svc._adjacency is not None
        # Rebuild clears cache
        svc.rebuild_from_loaded_entities()
        assert svc._adjacency is None


class TestGraphServiceResolveEntityName:
    def test_resolve_returns_input_for_empty(self, data_service_factory, sample_csv_file):
        ds = data_service_factory()
        ds.load_data_source(str(sample_csv_file.parent), [])
        svc = GraphService(ds)
        svc.build_graph(str(sample_csv_file.parent), [], write_neo4j=False)
        assert svc._resolve_entity_name("") == ""
        assert svc._resolve_entity_name("   ") == ""

    def test_resolve_canonical_by_alias(self, data_service_factory, sample_csv_file):
        ds = data_service_factory()
        ds.load_data_source(str(sample_csv_file.parent), [])
        svc = GraphService(ds)
        svc.build_graph(str(sample_csv_file.parent), [], write_neo4j=False)
        result = svc._resolve_entity_name("Kepler-186f")
        assert result == "Kepler-186f"

    def test_resolve_cache_hit(self, data_service_factory, sample_csv_file):
        ds = data_service_factory()
        ds.load_data_source(str(sample_csv_file.parent), [])
        svc = GraphService(ds)
        svc.build_graph(str(sample_csv_file.parent), [], write_neo4j=False)
        # First call populates cache
        r1 = svc._resolve_entity_name("Kepler-186f")
        # Second call hits cache
        assert svc._resolve_entity_name("Kepler-186f") == r1
        assert "Kepler-186f" in svc._resolve_cache


class TestGraphServiceVisualization:
    def test_visualization_graph_returns_nodes_and_links(self, data_service_factory, sample_csv_file):
        ds = data_service_factory()
        ds.load_data_source(str(sample_csv_file.parent), [])
        svc = GraphService(ds)
        svc.build_graph(str(sample_csv_file.parent), [], write_neo4j=False)
        result = svc.visualization_graph(max_nodes=100, max_links=200)
        assert "nodes" in result
        assert "links" in result
        assert isinstance(result["nodes"], list)
        assert isinstance(result["links"], list)
