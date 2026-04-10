from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx


ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _clean_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _looks_meaningful(text: str, min_chars: int) -> bool:
    text = _clean_ws(text)
    if len(text) < min_chars:
        return False
    alpha = sum(1 for c in text if c.isalpha())
    return alpha >= max(40, int(min_chars * 0.2))


def _normalize_title_key(title: str) -> str:
    t = _clean_ws(title).lower()
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", t)
    return t


@dataclass
class BuildConfig:
    output_root: Path
    arxiv_max_results: int
    apod_count: int
    exoplanet_max_rows: int
    min_abstract_chars: int
    arxiv_query: str
    timeout_seconds: float
    max_retries: int
    download_pdf_limit: int
    sleep_seconds: float
    nasa_api_key: str


class HQAstronomyCorpusBuilder:
    def __init__(self, cfg: BuildConfig) -> None:
        self.cfg = cfg
        self.client = httpx.Client(timeout=cfg.timeout_seconds, follow_redirects=True)
        self._seen_keys: set[str] = set()

    def run(self) -> dict[str, Any]:
        raw_root = self.cfg.output_root / "raw"
        clean_root = self.cfg.output_root / "clean"
        pdf_root = self.cfg.output_root / "papers" / "pdf"
        raw_root.mkdir(parents=True, exist_ok=True)
        clean_root.mkdir(parents=True, exist_ok=True)
        if self.cfg.download_pdf_limit > 0:
            pdf_root.mkdir(parents=True, exist_ok=True)

        arxiv_docs = self._fetch_arxiv()
        apod_docs = self._fetch_apod()
        exoplanet_rows = self._fetch_exoplanets()

        # Persist source raw payloads.
        self._write_jsonl(raw_root / "arxiv.jsonl", arxiv_docs)
        self._write_jsonl(raw_root / "apod.jsonl", apod_docs)
        self._write_jsonl(raw_root / "exoplanets.jsonl", exoplanet_rows)

        # Build unified clean text corpus.
        corpus_docs: list[dict[str, Any]] = []
        corpus_docs.extend(self._to_text_docs_from_arxiv(arxiv_docs))
        corpus_docs.extend(self._to_text_docs_from_apod(apod_docs))
        corpus_docs.extend(self._to_text_docs_from_exoplanets(exoplanet_rows))

        deduped_docs = self._dedupe_docs(corpus_docs)
        self._write_jsonl(clean_root / "astronomy_kb_clean.jsonl", deduped_docs)

        # Structured facts for graph-friendly ingestion.
        fact_rows = self._to_fact_rows(exoplanet_rows)
        self._write_jsonl(clean_root / "exoplanet_facts.jsonl", fact_rows)

        if self.cfg.download_pdf_limit > 0 and arxiv_docs:
            self._download_arxiv_pdfs(arxiv_docs, pdf_root, self.cfg.download_pdf_limit)

        stats = {
            "output_root": str(self.cfg.output_root),
            "arxiv_docs": len(arxiv_docs),
            "apod_docs": len(apod_docs),
            "exoplanet_rows": len(exoplanet_rows),
            "clean_corpus_docs": len(deduped_docs),
            "fact_rows": len(fact_rows),
            "pdf_downloaded": len(list(pdf_root.glob("*.pdf"))) if pdf_root.exists() else 0,
            "generated_at_unix": int(time.time()),
            "sources": [
                "https://export.arxiv.org/api/query",
                "https://api.nasa.gov/planetary/apod",
                "https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
            ],
        }
        (clean_root / "build_stats.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return stats

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for _ in range(max(1, self.cfg.max_retries)):
            try:
                resp = self.client.request(method=method, url=url, **kwargs)
                resp.raise_for_status()
                return resp
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(max(0.2, self.cfg.sleep_seconds))
        assert last_exc is not None
        raise RuntimeError(f"request failed after retries: {url} -> {type(last_exc).__name__}: {last_exc}")

    def _fetch_arxiv(self) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        start = 0
        batch = 100
        target = max(0, self.cfg.arxiv_max_results)
        while start < target:
            take = min(batch, target - start)
            url = (
                "https://export.arxiv.org/api/query?"
                f"search_query={self.cfg.arxiv_query}&start={start}&max_results={take}"
            )
            resp = self._request("GET", url)
            root = ET.fromstring(resp.text.encode("utf-8", errors="ignore"))
            entries = root.findall("atom:entry", ARXIV_NS)
            if not entries:
                break

            for e in entries:
                arxiv_id = _clean_ws(e.findtext("atom:id", default="", namespaces=ARXIV_NS)).split("/")[-1]
                title = _clean_ws(e.findtext("atom:title", default="", namespaces=ARXIV_NS))
                summary = _clean_ws(e.findtext("atom:summary", default="", namespaces=ARXIV_NS))
                if not arxiv_id or not title or not _looks_meaningful(summary, self.cfg.min_abstract_chars):
                    continue
                published = _clean_ws(e.findtext("atom:published", default="", namespaces=ARXIV_NS))
                updated = _clean_ws(e.findtext("atom:updated", default="", namespaces=ARXIV_NS))
                categories = [x.attrib.get("term", "").strip() for x in e.findall("atom:category", ARXIV_NS)]
                categories = [x for x in categories if x]
                authors = [
                    _clean_ws(a.findtext("atom:name", default="", namespaces=ARXIV_NS))
                    for a in e.findall("atom:author", ARXIV_NS)
                ]
                authors = [x for x in authors if x]
                links = [l.attrib.get("href", "").strip() for l in e.findall("atom:link", ARXIV_NS)]
                pdf_url = ""
                for link in links:
                    if "/pdf/" in link or link.endswith(".pdf"):
                        pdf_url = link
                        break
                if not pdf_url:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

                docs.append(
                    {
                        "source": "arxiv",
                        "source_id": arxiv_id,
                        "title": title,
                        "summary": summary,
                        "published": published,
                        "updated": updated,
                        "categories": categories,
                        "authors": authors[:12],
                        "url": f"https://arxiv.org/abs/{arxiv_id}",
                        "pdf_url": pdf_url,
                    }
                )
            start += take
            time.sleep(self.cfg.sleep_seconds)
        return docs

    def _fetch_apod(self) -> list[dict[str, Any]]:
        if self.cfg.apod_count <= 0:
            return []
        url = "https://api.nasa.gov/planetary/apod"
        rows: list[dict[str, Any]] = []
        seen_source_ids: set[str] = set()
        remaining = int(self.cfg.apod_count)
        while remaining > 0:
            take = min(remaining, 40)
            try:
                resp = self._request(
                    "GET",
                    url,
                    params={"api_key": self.cfg.nasa_api_key, "count": int(take)},
                )
            except Exception:
                break
            payload = resp.json()
            if isinstance(payload, dict):
                batch = [payload]
            elif isinstance(payload, list):
                batch = payload
            else:
                batch = []
            if not batch:
                break
            for item in batch:
                if isinstance(item, dict):
                    sid = _clean_ws(item.get("date", "") or item.get("title", ""))
                    if sid and sid in seen_source_ids:
                        continue
                    if sid:
                        seen_source_ids.add(sid)
                    rows.append(item)
            remaining -= len(batch)
            if len(batch) < take:
                break
            time.sleep(self.cfg.sleep_seconds)

        if remaining > 0:
            for item in self._fetch_apod_archive_fallback(remaining):
                sid = _clean_ws(item.get("date", "") or item.get("title", ""))
                if sid and sid in seen_source_ids:
                    continue
                if sid:
                    seen_source_ids.add(sid)
                rows.append(item)
                remaining -= 1
                if remaining <= 0:
                    break

        docs: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = _clean_ws(row.get("title", ""))
            explanation = _clean_ws(row.get("explanation", ""))
            date = _clean_ws(row.get("date", ""))
            media_type = _clean_ws(row.get("media_type", ""))
            if not title or not _looks_meaningful(explanation, min_chars=80):
                continue
            docs.append(
                {
                    "source": "nasa_apod",
                    "source_id": date or title[:32],
                    "title": title,
                    "summary": explanation,
                    "published": date,
                    "media_type": media_type,
                    "url": _clean_ws(row.get("hdurl", "") or row.get("url", "")),
                    "copyright": _clean_ws(row.get("copyright", "")),
                }
            )
        return docs

    def _fetch_apod_archive_fallback(self, needed: int) -> list[dict[str, Any]]:
        needed = max(0, int(needed))
        if needed <= 0:
            return []

        archive_url = "https://apod.nasa.gov/apod/archivepixFull.html"
        try:
            resp = self._request("GET", archive_url)
        except Exception:
            return []

        link_rows = re.findall(r'<a href="(ap\d{6}\.html)">([^<]+)</a>', resp.text, flags=re.IGNORECASE)
        if not link_rows:
            return []

        out: list[dict[str, Any]] = []
        for rel_link, fallback_title in link_rows[: max(needed * 3, needed)]:
            if len(out) >= needed:
                break
            page_url = urljoin("https://apod.nasa.gov/apod/", rel_link)
            try:
                page = self._request("GET", page_url).text
            except Exception:
                continue

            title = self._extract_apod_title(page) or _clean_ws(fallback_title)
            explanation = self._extract_apod_explanation(page)
            if not title or not _looks_meaningful(explanation, 80):
                continue

            date = self._extract_apod_date_from_link(rel_link)
            media_url = self._extract_apod_media_url(page, page_url)
            out.append(
                {
                    "title": title,
                    "explanation": explanation,
                    "date": date,
                    "media_type": "image",
                    "url": media_url or page_url,
                }
            )
            time.sleep(self.cfg.sleep_seconds)
        return out

    @staticmethod
    def _extract_apod_title(page_html: str) -> str:
        m = re.search(r"<title>\s*([^<]+)\s*</title>", page_html, flags=re.IGNORECASE)
        if not m:
            return ""
        title_raw = _clean_ws(html.unescape(m.group(1)))
        if " - " in title_raw:
            title_raw = title_raw.split(" - ", 1)[-1].strip()
        return title_raw

    @staticmethod
    def _extract_apod_explanation(page_html: str) -> str:
        text = re.sub(r"(?is)<script.*?>.*?</script>", " ", page_html)
        text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</p>", "\n", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = _clean_ws(html.unescape(text))
        if not text:
            return ""
        marker = "Explanation:"
        pos = text.find(marker)
        if pos >= 0:
            tail = text[pos + len(marker) :].strip()
            end_markers = ["Tomorrow's picture", "Tomorrow's APOD", "Copyright"]
            end_idx = len(tail)
            for em in end_markers:
                p = tail.find(em)
                if p > 20:
                    end_idx = min(end_idx, p)
            tail = tail[:end_idx].strip()
            return _clean_ws(tail)
        return text[:2000]

    @staticmethod
    def _extract_apod_date_from_link(rel_link: str) -> str:
        m = re.match(r"ap(\d{2})(\d{2})(\d{2})\.html", rel_link, flags=re.IGNORECASE)
        if not m:
            return ""
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = 1900 + yy if yy >= 95 else 2000 + yy
        return f"{year:04d}-{mm:02d}-{dd:02d}"

    @staticmethod
    def _extract_apod_media_url(page_html: str, page_url: str) -> str:
        img = re.search(r'(?i)<img[^>]+src="([^"]+)"', page_html)
        if img:
            return urljoin(page_url, _clean_ws(img.group(1)))
        href = re.search(r'(?i)<a[^>]+href="([^"]+\.(?:jpg|jpeg|png|gif|webp))"', page_html)
        if href:
            return urljoin(page_url, _clean_ws(href.group(1)))
        return ""

    def _fetch_exoplanets(self) -> list[dict[str, Any]]:
        if self.cfg.exoplanet_max_rows <= 0:
            return []
        query = (
            "select+top+{top}+"
            "pl_name,hostname,disc_year,discoverymethod,pl_orbper,pl_rade,pl_bmasse,sy_dist,st_spectype,"
            "pl_eqt,pl_orbeccen,disc_facility+from+pscomppars"
        ).format(top=int(self.cfg.exoplanet_max_rows))
        url = f"https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query={query}&format=csv"
        resp = self._request("GET", url)
        text = resp.text

        rows: list[dict[str, Any]] = []
        reader = csv.DictReader(text.splitlines())
        for row in reader:
            if not isinstance(row, dict):
                continue
            name = _clean_ws(row.get("pl_name", ""))
            host = _clean_ws(row.get("hostname", ""))
            if not name:
                continue
            rows.append(
                {
                    "source": "nasa_exoplanet_archive",
                    "source_id": name,
                    "pl_name": name,
                    "host_star": host,
                    "disc_year": _clean_ws(row.get("disc_year", "")),
                    "discovery_method": _clean_ws(row.get("discoverymethod", "")),
                    "orbital_period_days": _clean_ws(row.get("pl_orbper", "")),
                    "radius_earth": _clean_ws(row.get("pl_rade", "")),
                    "mass_earth": _clean_ws(row.get("pl_bmasse", "")),
                    "distance_pc": _clean_ws(row.get("sy_dist", "")),
                    "star_spectral_type": _clean_ws(row.get("st_spectype", "")),
                    "eq_temp_k": _clean_ws(row.get("pl_eqt", "")),
                    "eccentricity": _clean_ws(row.get("pl_orbeccen", "")),
                    "disc_facility": _clean_ws(row.get("disc_facility", "")),
                    "url": "https://exoplanetarchive.ipac.caltech.edu/",
                }
            )
        return rows

    def _to_text_docs_from_arxiv(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for d in docs:
            cats = ", ".join(d.get("categories", [])[:6])
            authors = ", ".join(d.get("authors", [])[:6])
            text = (
                f"Title: {d.get('title', '')}\n"
                f"Published: {d.get('published', '')}\n"
                f"Categories: {cats}\n"
                f"Authors: {authors}\n"
                f"Abstract: {d.get('summary', '')}\n"
                f"Source URL: {d.get('url', '')}"
            )
            out.append(
                {
                    "doc_id": f"arxiv::{d.get('source_id', '')}",
                    "title": d.get("title", ""),
                    "text": _clean_ws(text),
                    "source": "arxiv",
                    "url": d.get("url", ""),
                    "quality_score": 0.97,
                }
            )
        return out

    def _to_text_docs_from_apod(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for d in docs:
            text = (
                f"APOD Date: {d.get('published', '')}\n"
                f"Title: {d.get('title', '')}\n"
                f"Media Type: {d.get('media_type', '')}\n"
                f"Explanation: {d.get('summary', '')}\n"
                f"Source URL: {d.get('url', '')}"
            )
            out.append(
                {
                    "doc_id": f"apod::{d.get('source_id', '')}",
                    "title": d.get("title", ""),
                    "text": _clean_ws(text),
                    "source": "nasa_apod",
                    "url": d.get("url", ""),
                    "quality_score": 0.91,
                }
            )
        return out

    def _to_text_docs_from_exoplanets(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows:
            name = row.get("pl_name", "")
            host = row.get("host_star", "")
            text = (
                f"{name} is an exoplanet in the NASA Exoplanet Archive.\n"
                f"Host star: {host or 'unknown'}.\n"
                f"Discovery year: {row.get('disc_year', 'unknown')}.\n"
                f"Discovery method: {row.get('discovery_method', 'unknown')}.\n"
                f"Orbital period (days): {row.get('orbital_period_days', 'unknown')}.\n"
                f"Radius (Earth radii): {row.get('radius_earth', 'unknown')}.\n"
                f"Mass (Earth masses): {row.get('mass_earth', 'unknown')}.\n"
                f"Distance (pc): {row.get('distance_pc', 'unknown')}.\n"
                f"Equilibrium temperature (K): {row.get('eq_temp_k', 'unknown')}.\n"
                f"Discovery facility: {row.get('disc_facility', 'unknown')}."
            )
            out.append(
                {
                    "doc_id": f"exo::{name}",
                    "title": name,
                    "text": _clean_ws(text),
                    "source": "nasa_exoplanet_archive",
                    "url": "https://exoplanetarchive.ipac.caltech.edu/",
                    "quality_score": 0.93,
                }
            )
        return out

    def _to_fact_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        for row in rows:
            name = row.get("pl_name", "")
            if not name:
                continue
            facts.append(
                {
                    "name": name,
                    "host_star": row.get("host_star", ""),
                    "discovery_year": row.get("disc_year", ""),
                    "discovery_method": row.get("discovery_method", ""),
                    "orbital_period_days": row.get("orbital_period_days", ""),
                    "radius_earth": row.get("radius_earth", ""),
                    "mass_earth": row.get("mass_earth", ""),
                    "distance_pc": row.get("distance_pc", ""),
                    "star_spectral_type": row.get("star_spectral_type", ""),
                    "eq_temp_k": row.get("eq_temp_k", ""),
                    "eccentricity": row.get("eccentricity", ""),
                    "provider": "nasa_exoplanet_archive",
                    "source_url": "https://exoplanetarchive.ipac.caltech.edu/",
                }
            )
        return facts

    def _dedupe_docs(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for doc in docs:
            title = str(doc.get("title", "")).strip()
            text = str(doc.get("text", "")).strip()
            if not title or not _looks_meaningful(text, 80):
                continue
            key = f"{doc.get('source', '')}|{doc.get('doc_id', '')}|{_normalize_title_key(title)}"
            if key in self._seen_keys:
                continue
            self._seen_keys.add(key)
            out.append(doc)
        return out

    def _download_arxiv_pdfs(self, docs: list[dict[str, Any]], pdf_root: Path, limit: int) -> None:
        done = 0
        for d in docs:
            if done >= limit:
                break
            arxiv_id = str(d.get("source_id", "")).replace("/", "_")
            if not arxiv_id:
                continue
            out = pdf_root / f"{arxiv_id}.pdf"
            if out.exists() and out.stat().st_size > 0:
                done += 1
                continue
            pdf_url = str(d.get("pdf_url", "")).strip()
            if not pdf_url:
                continue
            try:
                resp = self._request("GET", pdf_url)
                out.write_bytes(resp.content)
                done += 1
                time.sleep(self.cfg.sleep_seconds)
            except Exception:
                continue

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and clean high-quality astronomy corpus.")
    parser.add_argument(
        "--output-root",
        default=r"D:/Astro/data/high_quality",
        help="Output directory on disk.",
    )
    parser.add_argument("--arxiv-max-results", type=int, default=240, help="Max arXiv entries.")
    parser.add_argument("--apod-count", type=int, default=100, help="NASA APOD rows.")
    parser.add_argument("--exoplanet-max-rows", type=int, default=4000, help="Max exoplanet rows.")
    parser.add_argument("--min-abstract-chars", type=int, default=220, help="Min chars for paper abstract.")
    parser.add_argument(
        "--arxiv-query",
        default="cat:astro-ph.*",
        help="arXiv query expression.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0, help="HTTP timeout.")
    parser.add_argument("--max-retries", type=int, default=3, help="Retry times per request.")
    parser.add_argument("--download-pdf-limit", type=int, default=0, help="Optionally download top-N arXiv PDFs.")
    parser.add_argument("--sleep-seconds", type=float, default=0.35, help="Small delay between requests.")
    parser.add_argument(
        "--nasa-api-key",
        default=(os.getenv("NASA_API_KEY", "").strip() or "DEMO_KEY"),
        help="NASA API key for APOD download.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = BuildConfig(
        output_root=Path(args.output_root),
        arxiv_max_results=max(0, int(args.arxiv_max_results)),
        apod_count=max(0, int(args.apod_count)),
        exoplanet_max_rows=max(0, int(args.exoplanet_max_rows)),
        min_abstract_chars=max(80, int(args.min_abstract_chars)),
        arxiv_query=str(args.arxiv_query),
        timeout_seconds=max(5.0, float(args.timeout_seconds)),
        max_retries=max(1, int(args.max_retries)),
        download_pdf_limit=max(0, int(args.download_pdf_limit)),
        sleep_seconds=max(0.0, float(args.sleep_seconds)),
        nasa_api_key=str(args.nasa_api_key or "DEMO_KEY").strip() or "DEMO_KEY",
    )
    builder = HQAstronomyCorpusBuilder(cfg)
    stats = builder.run()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
