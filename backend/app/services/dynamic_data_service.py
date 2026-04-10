from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.services.sqlite_service import get_sqlite_connection


class DynamicDataService:
    """
    Dynamic authority data fetcher with cache.
    Current provider: NASA Exoplanet Archive TAP API.
    """

    _TAP_ENDPOINT = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

    def __init__(self) -> None:
        self._db_path = settings.sqlite_path
        self._init_db()

    def query_exoplanet(self, name: str) -> dict[str, Any] | None:
        planet_name = str(name or "").strip()
        if not planet_name:
            return None

        cached = self._get_cached(planet_name, allow_stale=False)
        if cached is not None:
            return cached

        fetched = self._fetch_from_nasa(planet_name)
        if fetched is not None:
            self._save_cache(planet_name, fetched)
            return fetched

        # Graceful degradation: if real-time fails, return stale cache if present.
        stale = self._get_cached(planet_name, allow_stale=True)
        if stale is not None:
            stale["stale"] = True
            return stale
        return None

    @staticmethod
    def is_probable_exoplanet_name(text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        patterns = (
            r"\b(?:TOI|HD|K2|Kepler|WASP|TRAPPIST|LHS|GJ|Gliese|CoRoT|HIP|KIC)[-\s]?\d+[A-Za-z]?(?:\s*[bcdefg])?\b",
            r"\b[A-Z]{2,6}\s?\d{2,6}\s?[bcdefg]\b",
        )
        for p in patterns:
            if re.search(p, value, flags=re.IGNORECASE):
                return True
        return False

    def _fetch_from_nasa(self, planet_name: str) -> dict[str, Any] | None:
        def sql_for(candidate: str) -> list[str]:
            safe = candidate.replace("'", "''")
            safe_nospace = re.sub(r"\s+", "", candidate).replace("'", "''")
            return [
                (
                    "select top 1 "
                    "pl_name, hostname, disc_year, discoverymethod, "
                    "pl_bmasse, pl_rade, pl_orbper, pl_orbsmax, "
                    "st_teff, st_mass, st_rad, sy_dist "
                    "from pscomppars "
                    f"where lower(replace(pl_name,' ',''))=lower('{safe_nospace}')"
                ),
                (
                    "select top 1 "
                    "pl_name, hostname, disc_year, discoverymethod, "
                    "pl_bmasse, pl_rade, pl_orbper, pl_orbsmax, "
                    "st_teff, st_mass, st_rad, sy_dist "
                    "from pscomppars "
                    f"where lower(replace(pl_name,' ','')) like lower('%{safe_nospace}%')"
                ),
                (
                    "select top 1 "
                    "pl_name, hostname, disc_year, discoverymethod, "
                    "pl_bmasse, pl_rade, pl_orbper, pl_orbsmax, "
                    "st_teff, st_mass, st_rad, sy_dist "
                    "from pscomppars "
                    f"where lower(pl_name)=lower('{safe}')"
                ),
            ]

        candidates = self._planet_name_variants(planet_name)
        timeout_s = max(1.5, float(settings.dynamic_timeout_seconds))
        with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
            for candidate in candidates:
                for sql in sql_for(candidate):
                    try:
                        resp = client.get(
                            self._TAP_ENDPOINT,
                            params={"query": sql, "format": "json"},
                        )
                        resp.raise_for_status()
                        rows = resp.json()
                    except Exception:
                        continue
                    if not isinstance(rows, list) or not rows:
                        continue
                    return self._normalize_row(rows[0], requested=planet_name)
        return None

    @staticmethod
    def _planet_name_variants(planet_name: str) -> list[str]:
        base = re.sub(r"\s+", " ", str(planet_name or "").strip())
        if not base:
            return []
        variants: list[str] = [base]
        # Kepler-452b -> Kepler-452 b
        spaced = re.sub(r"(?<=\d)([bcdefg])$", r" \1", base, flags=re.IGNORECASE)
        if spaced != base:
            variants.append(spaced)
        compact = re.sub(r"\s+", "", base)
        if compact != base:
            variants.append(compact)
        if spaced:
            spaced_compact = re.sub(r"\s+", "", spaced)
            if spaced_compact not in variants:
                variants.append(spaced_compact)
        out: list[str] = []
        seen: set[str] = set()
        for v in variants:
            key = v.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(v)
        return out

    def _normalize_row(self, row: dict[str, Any], requested: str) -> dict[str, Any]:
        def _num(key: str) -> float | None:
            value = row.get(key)
            if value in (None, ""):
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _year(key: str) -> int | None:
            value = row.get(key)
            if value in (None, ""):
                return None
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None

        payload = {
            "name": str(row.get("pl_name") or requested).strip(),
            "requested_name": str(requested).strip(),
            "host_star": str(row.get("hostname") or "").strip(),
            "discovery_method": str(row.get("discoverymethod") or "").strip(),
            "discovery_year": _year("disc_year"),
            "mass_earth": _num("pl_bmasse"),
            "radius_earth": _num("pl_rade"),
            "orbital_period_days": _num("pl_orbper"),
            "semi_major_axis_au": _num("pl_orbsmax"),
            "star_teff_k": _num("st_teff"),
            "star_mass_solar": _num("st_mass"),
            "star_radius_solar": _num("st_rad"),
            "distance_pc": _num("sy_dist"),
            "provider": "nasa_exoplanet_archive",
            "source_url": "https://exoplanetarchive.ipac.caltech.edu/",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        return payload

    def _connect(self) -> sqlite3.Connection:
        return get_sqlite_connection(self._db_path)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dynamic_facts (
                    cache_key TEXT PRIMARY KEY,
                    entity_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_dynamic_facts_entity ON dynamic_facts(entity_name)"
            )
            conn.commit()
        finally:
            conn.close()

    def _cache_key(self, entity_name: str) -> str:
        return str(entity_name).strip().lower()

    def _get_cached(self, entity_name: str, allow_stale: bool) -> dict[str, Any] | None:
        key = self._cache_key(entity_name)
        if not key:
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT payload_json, expires_at
                FROM dynamic_facts
                WHERE cache_key = ?
                """,
                (key,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            payload = json.loads(str(row["payload_json"]))
        except json.JSONDecodeError:
            return None

        expires_at = str(row["expires_at"])
        now = datetime.now(timezone.utc)
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            exp_dt = now

        if exp_dt >= now or allow_stale:
            return payload if isinstance(payload, dict) else None
        return None

    def _save_cache(self, entity_name: str, payload: dict[str, Any]) -> None:
        key = self._cache_key(entity_name)
        if not key:
            return
        now = datetime.now(timezone.utc)
        ttl_hours = max(1, int(settings.dynamic_cache_ttl_hours))
        exp = now + timedelta(hours=ttl_hours)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO dynamic_facts (cache_key, entity_name, provider, payload_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    entity_name = excluded.entity_name,
                    provider = excluded.provider,
                    payload_json = excluded.payload_json,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at
                """,
                (
                    key,
                    str(entity_name).strip(),
                    str(payload.get("provider", "unknown")),
                    json.dumps(payload, ensure_ascii=False),
                    now.isoformat(),
                    exp.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
