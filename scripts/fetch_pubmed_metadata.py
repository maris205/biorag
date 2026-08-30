#!/usr/bin/env python3
"""Fetch a compact, resumable PubMed metadata cache for SeqLit-DAG PMIDs."""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.seq_lit_dag.build import pubmed_record_from_xml


EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def main() -> None:
    args = parse_args()
    pmids = load_pmids(Path(args.input))
    existing = load_existing(Path(args.output)) if args.resume else {}
    pending = [pmid for pmid in pmids if pmid not in existing]
    fetched = dict(existing)
    for start in range(0, len(pending), args.batch_size):
        batch = pending[start : start + args.batch_size]
        root = fetch_batch(batch, retries=args.retries, timeout=args.timeout)
        for elem in root.findall(".//PubmedArticle"):
            record = pubmed_record_from_xml(elem)
            if record:
                fetched[record.pmid] = dataclasses.asdict(record)
        write_cache(Path(args.output), fetched)
        print(json.dumps({"processed": min(start + len(batch), len(pending)), "pending": len(pending), "cached": len(fetched)}))
        if start + args.batch_size < len(pending):
            time.sleep(args.delay)


def load_pmids(path: Path) -> list[str]:
    pmids: set[str] = set()
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            pmids.update(str(item) for item in row.get("expected_pmids", []))
            pmids.update(str(item) for item in (row.get("labels") or {}).get("pmids", []))
    return sorted(pmids, key=int)


def load_existing(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, object]] = {}
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                rows[str(row["pmid"])] = row
    return rows


def fetch_batch(pmids: list[str], *, retries: int, timeout: float) -> ET.Element:
    payload = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}).encode("ascii")
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(EFETCH_URL, data=payload, headers={"User-Agent": "BioRAG-SeqLit-DAG/0.1"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return ET.fromstring(response.read())
        except (OSError, ET.ParseError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"PubMed fetch failed after {retries + 1} attempts") from last_error


def write_cache(path: Path, rows: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wt", encoding="utf-8") as handle:
        for pmid in sorted(rows, key=int):
            handle.write(json.dumps(rows[pmid], ensure_ascii=False) + "\n")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch PubMed metadata for SeqLit-DAG PMIDs")
    parser.add_argument("--input", default="data/seq_lit_dag_swissprot_sample/documents.jsonl")
    parser.add_argument("--output", default="data/seq_lit_dag_swissprot_sample/pubmed_metadata.jsonl")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--delay", type=float, default=0.34)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()
