#!/usr/bin/env python3
"""Evaluate a live R2R collection as the generic text-RAG sequence control."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.integrations.r2r import build_r2r_text_control_pack, search_r2r_text_control


def main() -> None:
    args = parse_args()
    try:
        import r2r
        from r2r import R2RClient
    except ImportError as exc:
        raise SystemExit("Install the frozen optional runtime with `bash scripts/setup_r2r_runtime.sh`.") from exc
    client = R2RClient(base_url=args.base_url)
    runtime = collect_runtime_metadata(
        client,
        collection_id=args.collection_id,
        sdk_version=str(getattr(r2r, "__version__", "unknown")),
    )
    queries = read_jsonl(Path(args.queries))
    corpus_manifest = json.loads(Path(args.bundle_manifest).read_text(encoding="utf-8"))
    if args.test_ids:
        test_ids = {
            line.strip()
            for line in Path(args.test_ids).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        queries = [query for query in queries if str(query["id"]) in test_ids]
    if args.query_limit:
        queries = queries[: args.query_limit]
    details = []
    packs = []
    latencies = []
    for index, query in enumerate(queries, start=1):
        started = time.perf_counter()
        chunks = search_r2r_text_control(
            client,
            str(query["query"]),
            collection_id=args.collection_id,
            limit=args.top_k,
        )
        latency_ms = 1000.0 * (time.perf_counter() - started)
        latencies.append(latency_ms)
        route = build_r2r_text_control_pack(query, chunks)
        route["retrieval"]["api_latency_ms"] = latency_ms
        packs.append(route)
        accessions = [str(item["accession"]) for item in route["pack"]["candidates"]]
        pmids = [str(item) for item in route["pack"]["papers"]]
        details.append(
            {
                "query_id": str(query["id"]),
                "method": "r2r_text_only",
                "top_accessions": accessions,
                "top_pmids": pmids,
                "latency_ms": latency_ms,
                "chunks": chunks if args.keep_chunks else [],
            }
        )
        print(json.dumps({"query": index, "total": len(queries), "latency_ms": round(latency_ms, 3)}), flush=True)
    result = {
        "dataset": "BioRAG SeqLit held-out R2R text-only control",
        "claim_scope": (
            "This is the generic R2R semantic text route over an explicitly frozen collection. "
            "It is a deployment control, not a biological sequence embedding baseline."
        ),
        "r2r_base_url": args.base_url,
        "collection_id": args.collection_id,
        "embedding_label": args.embedding_label,
        "embedding_artifact": {
            "serving_runtime": args.embedding_server,
            "model": "qwen3-embedding:0.6b",
            "digest": args.embedding_digest,
            "parameters": args.embedding_parameters,
            "quantization": args.embedding_quantization,
            "dimension": 1024,
        },
        "runtime": runtime,
        "corpus": {
            "manifest": args.bundle_manifest,
            "source_snapshot": corpus_manifest.get("source_snapshot"),
            "documents_source": corpus_manifest.get("documents_source"),
            "include_sequence_documents": corpus_manifest.get("include_sequence_documents"),
            "documents_only": corpus_manifest.get("documents_only"),
            "counts": corpus_manifest.get("counts"),
            "leakage_audit": corpus_manifest.get("leakage_audit"),
        },
        "retrieval_configuration": {
            "search_mode": "custom",
            "semantic_search": True,
            "fulltext_search": False,
            "hybrid_search": False,
            "graph_search": False,
            "collection_filter": args.collection_id,
        },
        "test_ids": args.test_ids,
        "query_count": len(details),
        "top_k": args.top_k,
        "latency": {
            "mean_ms": statistics.mean(latencies) if latencies else 0.0,
            "p50_ms": percentile(latencies, 0.50),
            "p95_ms": percentile(latencies, 0.95),
        },
        "retrieval_summary": summarize_retrieval(packs),
        "agent_packs": str(args.packs_output),
        "details": details,
    }
    packs_output = Path(args.packs_output)
    packs_output.parent.mkdir(parents=True, exist_ok=True)
    packs_output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in packs),
        encoding="utf-8",
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "latency": result["latency"]}, indent=2))


def collect_runtime_metadata(client: Any, *, collection_id: str, sdk_version: str) -> dict[str, Any]:
    """Record the live retriever configuration without exporting credentials."""
    health = _model_dict(client.system.health()).get("results", {})
    status = _model_dict(client.system.status()).get("results", {})
    settings = _model_dict(client.system.settings()).get("results", {}).get("config", {})
    collection = _model_dict(client.collections.retrieve(collection_id)).get("results", {})
    embedding = dict(settings.get("embedding") or {})
    ingestion = dict(settings.get("ingestion") or {})
    database = dict(settings.get("database") or {})
    app = dict(settings.get("app") or {})
    return {
        "r2r_sdk_version": sdk_version,
        "dependency_versions": {
            package: _package_version(package)
            for package in ("pydantic", "litellm", "openai", "unstructured-client", "supabase")
        },
        "health_message": health.get("message"),
        "server_start_time": status.get("start_time"),
        "project_name": app.get("project_name"),
        "embedding": {
            key: embedding.get(key)
            for key in (
                "provider",
                "base_model",
                "base_dimension",
                "batch_size",
                "concurrent_request_limit",
            )
        },
        "ingestion": {
            "provider": ingestion.get("provider"),
            "automatic_extraction": ingestion.get("automatic_extraction"),
            "chunking_strategy": ingestion.get("chunking_strategy"),
            "chunk_size": ingestion.get("chunk_size"),
            "chunk_overlap": ingestion.get("chunk_overlap"),
        },
        "database_provider": database.get("provider"),
        "collection": {
            key: collection.get(key)
            for key in ("id", "name", "document_count", "created_at", "updated_at")
        },
    }


def _model_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return value
    return {}


def _package_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def summarize_retrieval(rows: list[dict[str, Any]]) -> dict[str, float]:
    keys = (
        "candidate_hit",
        "candidate_recall",
        "function_prompt_gold_recall",
        "literature_prompt_gold_recall",
    )
    return {
        key: statistics.mean(float(row["retrieval"][key]) for row in rows) if rows else 0.0
        for key in keys
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the live R2R text-only application control")
    parser.add_argument("--base-url", default="http://localhost:7272")
    parser.add_argument("--collection-id", required=True)
    parser.add_argument("--embedding-label", required=True)
    parser.add_argument("--embedding-server", default="ollama==0.33.2")
    parser.add_argument("--embedding-digest", default="ac6da0dfba84")
    parser.add_argument("--embedding-parameters", default="595.78M")
    parser.add_argument("--embedding-quantization", default="Q8_0")
    parser.add_argument("--queries", default="data/seq_lit_dag_function_heldout_2k/queries.jsonl")
    parser.add_argument(
        "--bundle-manifest",
        default="outputs/r2r/seq_lit_dag_function_heldout_2k_text_control/manifest.json",
    )
    parser.add_argument(
        "--test-ids",
        default="reports/results/agent_graph_selector_fused_full_p20_test_ids.txt",
    )
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--query-limit", type=int, default=0)
    parser.add_argument("--keep-chunks", action="store_true")
    parser.add_argument("--output", default="reports/results/r2r_text_control.json")
    parser.add_argument(
        "--packs-output",
        default="reports/results/agent_application_ablation/r2r_text_only.jsonl",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
