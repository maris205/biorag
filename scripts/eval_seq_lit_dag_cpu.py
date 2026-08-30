#!/usr/bin/env python3
"""Run the CPU-only SeqLit-DAG path sanity evaluation."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.seq_lit_dag.evaluate import evaluate_sequence_to_paper


def main() -> None:
    args = parse_args()
    result = evaluate_sequence_to_paper(
        queries_path=Path(args.queries),
        documents_path=Path(args.documents),
        graph_db=Path(args.graph_db),
        blast_db=Path(args.blast_db) if args.blast_db else None,
        limit=args.limit,
        top_k=args.top_k,
        paper_k=args.paper_k,
        kmer_size=args.kmer_size,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    with csv_path.open("wt", encoding="utf-8", newline="") as handle:
        fields = ["query_id", "method", "accession_hit", "paper_hit", "paper_recall", "path_complete", "candidate_ms"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in result["details"])
    print(json.dumps({key: value for key, value in result.items() if key != "details"}, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate CPU SeqLit-DAG sequence-to-paper path sanity")
    root = "data/seq_lit_dag_swissprot_sample"
    parser.add_argument("--queries", default=f"{root}/sample_queries.jsonl")
    parser.add_argument("--documents", default=f"{root}/documents.jsonl")
    parser.add_argument("--graph-db", default=f"{root}/graph.sqlite")
    parser.add_argument("--blast-db", default="/autodl-fs/data/open-rosalind-kb/standard/index/blast/swissprot")
    parser.add_argument("--output", default="reports/results/seq_lit_dag_cpu_sanity.json")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--paper-k", type=int, default=50)
    parser.add_argument("--kmer-size", type=int, default=3)
    return parser.parse_args()


if __name__ == "__main__":
    main()
