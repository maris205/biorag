#!/usr/bin/env python3
"""Generate free-form, citation-bounded SeqLit evidence notes."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.agent_review import audit_freeform_answer, build_freeform_prompt
from dnarag.seq_lit_dag.build import load_pubmed_cache, parse_go_obo
from scripts.generate_agent_qa import generate, load_model


def main() -> None:
    args = parse_args()
    queries = {str(row["id"]): row for row in read_jsonl(Path(args.queries))}
    selected_ids = load_ids(Path(args.query_ids_file))
    rows = [row for row in read_jsonl(Path(args.packs)) if str(row["pack"]["query_id"]) in selected_ids]
    rows.sort(key=lambda row: selected_ids[str(row["pack"]["query_id"])])
    if args.limit:
        rows = rows[: args.limit]
    if len(rows) != (min(len(selected_ids), args.limit) if args.limit else len(selected_ids)):
        raise ValueError(f"Pack/query count mismatch: {len(rows)} packs for {len(selected_ids)} selected IDs")
    go_terms = parse_go_obo(Path(args.go_obo))
    go_names = {go_id: term.name for go_id, term in go_terms.items()}
    pubmed = load_pubmed_cache(Path(args.pubmed_metadata)) if Path(args.pubmed_metadata).exists() else {}
    pubmed_metadata = {
        pmid: {
            "title": item.title,
            "abstract": item.abstract,
            "year": item.year,
            "journal": item.journal,
            "doi": item.doi,
        }
        for pmid, item in pubmed.items()
    }
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    model, frontend, model_interface = load_model(
        args.model,
        quantization=args.quantization,
        dtype=args.dtype,
        local_files_only=not args.allow_download,
        experts_implementation=args.experts_implementation,
    )
    model_load_s = time.perf_counter() - load_started
    outputs: list[dict[str, Any]] = []
    started = time.perf_counter()
    for index, row in enumerate(rows, start=1):
        pack = row["pack"]
        query_id = str(pack["query_id"])
        query = queries[query_id]
        context = build_freeform_prompt(
            query,
            pack,
            evidence_mode=args.evidence_mode,
            go_names=go_names,
            pubmed_metadata=pubmed_metadata,
        )
        answer, usage = generate(
            model,
            frontend,
            context["prompt"],
            max_new_tokens=args.max_new_tokens,
            model_interface=model_interface,
        )
        outputs.append(
            {
                "query_id": query_id,
                "route": args.route,
                "prompt": context["prompt"],
                "evidence_lines": context["evidence_lines"],
                "evidence_registry": context["evidence_registry"],
                "available_function_go_ids": context["available_function_go_ids"],
                "available_go_ids": context["available_go_ids"],
                "available_pmids": context["available_pmids"],
                "answer": answer,
                "audit": audit_freeform_answer(answer, context),
                **usage,
            }
        )
        print(json.dumps({"route": args.route, "generated": index, "total": len(rows)}), flush=True)
    latencies = [float(row["generation_s"]) for row in outputs]
    elapsed = time.perf_counter() - started
    result = {
        "dataset": "BioRAG SeqLit free-form expert review pilot",
        "status": "generated_pending_blinded_domain_review",
        "route": args.route,
        "evidence_mode": args.evidence_mode,
        "model": args.model,
        "model_interface": model_interface,
        "quantization": args.quantization,
        "dtype": args.dtype,
        "max_new_tokens": args.max_new_tokens,
        "query_count": len(outputs),
        "model_load_s": round(model_load_s, 3),
        "elapsed_s": round(elapsed, 3),
        "mean_generation_ms": round(1000 * sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "p95_generation_ms": round(1000 * percentile(latencies, 0.95), 3),
        "peak_gpu_memory_gib": round(torch.cuda.max_memory_allocated() / (1024**3), 3),
        "pubmed_metadata_records": len(pubmed_metadata),
        "outputs": outputs,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "queries": len(outputs)}, indent=2))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_ids(path: Path) -> dict[str, int]:
    return {
        query_id: index
        for index, query_id in enumerate(
            line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    }


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(int(quantile * len(ordered)), len(ordered) - 1)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate free-form SeqLit Agent evidence notes")
    parser.add_argument("--model", required=True)
    parser.add_argument("--route", required=True)
    parser.add_argument("--packs", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evidence-mode", choices=("raw", "graph_idf"), default="raw")
    parser.add_argument("--queries", default="data/seq_lit_dag_function_heldout_2k/queries.jsonl")
    parser.add_argument("--query-ids-file", default="reports/results/agent_expert_review/selected_query_ids.txt")
    parser.add_argument("--go-obo", default="/autodl-fs/data/open-rosalind-kb/standard/raw/go/go-basic.obo")
    parser.add_argument("--pubmed-metadata", default="reports/results/agent_expert_review/pubmed_metadata.jsonl")
    parser.add_argument("--max-new-tokens", type=int, default=320)
    parser.add_argument("--quantization", choices=("none", "4bit"), default="none")
    parser.add_argument("--dtype", choices=("auto", "bfloat16", "float16", "float32"), default="bfloat16")
    parser.add_argument("--experts-implementation")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


if __name__ == "__main__":
    main()
