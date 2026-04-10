"""Tests for data_service — CSV loading, indexing, SQLite persistence."""
from __future__ import annotations

import pytest

from app.services.data_service import DataService


class TestDataServiceCsvLoading:
    def test_load_csv_updates_revision(self, data_service_factory, sample_csv_file):
        svc = data_service_factory()
        assert svc.revision == 0
        svc.load_data_source(str(sample_csv_file.parent), [])
        assert svc.revision > 0

    def test_load_csv_creates_entities(self, data_service_factory, sample_csv_file):
        svc = data_service_factory()
        svc.load_data_source(str(sample_csv_file.parent), [])
        entities = svc.export_entities()
        assert len(entities) >= 3
        names = [e.get("name", "") for e in entities]
        assert "Kepler-186f" in names
        assert "Proxima Centauri b" in names

    def test_load_csv_sets_loaded_flag(self, data_service_factory, sample_csv_file):
        svc = data_service_factory()
        assert not svc.loaded
        svc.load_data_source(str(sample_csv_file.parent), [])
        assert svc.loaded

    def test_load_csv_preserves_raw_fields(self, data_service_factory, sample_csv_file):
        svc = data_service_factory()
        svc.load_data_source(str(sample_csv_file.parent), [])
        entities = svc.export_entities()
        kepler = next((e for e in entities if e.get("name") == "Kepler-186f"), None)
        assert kepler is not None
        raw = kepler.get("raw", {})
        assert str(raw.get("orbital_period_days", "")) == "130"

    def test_load_idempotent(self, data_service_factory, sample_csv_file):
        svc = data_service_factory()
        svc.load_data_source(str(sample_csv_file.parent), [])
        r1 = svc.revision
        svc.load_data_source(str(sample_csv_file.parent), [])
        r2 = svc.revision
        assert r2 > r1

    def test_get_status_reflects_loaded_state(self, data_service_factory, sample_csv_file):
        svc = data_service_factory()
        status = svc.get_status()
        assert status["loaded"] is False
        svc.load_data_source(str(sample_csv_file.parent), [])
        status = svc.get_status()
        assert status["loaded"] is True
        assert status["entity_count"] >= 3
