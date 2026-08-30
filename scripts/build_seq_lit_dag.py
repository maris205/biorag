#!/usr/bin/env python3
"""Build a CPU-only protein sequence-to-literature evidence DAG sample."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.config import load_config
from dnarag.seq_lit_dag import SeqLitDagBuilder


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    result = SeqLitDagBuilder(config).build(
        output_dir=args.output,
        limit_proteins=args.limit_proteins,
        min_pubmed_per_protein=args.min_pubmed_per_protein,
        max_go_annotations_per_protein=args.max_go_annotations_per_protein,
        max_windows_per_protein=args.max_windows_per_protein,
        pubmed_xml_limit=args.pubmed_xml_limit,
        pubmed_cache=args.pubmed_cache,
        reset=args.reset,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build BioRAG-SeqLit-DAG from local curated sources")
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--output", default="data/seq_lit_dag_swissprot_sample")
    parser.add_argument("--limit-proteins", type=int, default=200)
    parser.add_argument("--min-pubmed-per-protein", type=int, default=1)
    parser.add_argument("--max-go-annotations-per-protein", type=int, default=8)
    parser.add_argument("--max-windows-per-protein", type=int, default=2)
    parser.add_argument(
        "--pubmed-xml-limit",
        type=int,
        default=0,
        help="Number of local PubMed baseline XML files to scan for titles/abstracts; 0 keeps PMID-only paper nodes.",
    )
    parser.add_argument(
        "--pubmed-cache",
        default=None,
        help="Optional PubMed metadata JSONL cache; cache records take precedence over the local baseline scan.",
    )
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
