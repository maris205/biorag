"""Command line entry point for dnarag."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dnarag.config import as_jsonable, load_config
from dnarag.evaluation import DEFAULT_CONDITIONS, SearchEvaluator, load_benchmark
from dnarag.localdb.graph import GraphStore
from dnarag.localdb.graph_builder import GraphIndexBuilder
from dnarag.localdb.schema import initialize_schema
from dnarag.localdb.standard import StandardKB
from dnarag.localdb.view_graph import VectorViewGraphBuilder
from dnarag.retrieval.drag import DragBioAnswer
from dnarag.retrieval.hybrid import HybridBioSearch
from dnarag.retrieval.sequence import BlastUnavailable, LocalBlastSearch
from dnarag.retrieval.vector import VectorIndexBuilder
from dnarag.retrieval.vector_db import ChromaVectorDB, SimpleVectorDB


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.command == "status":
        cmd_status(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "answer":
        cmd_answer(args)
    elif args.command == "sequence-search":
        cmd_sequence_search(args)
    elif args.command == "build-graph":
        cmd_build_graph(args)
    elif args.command == "build-view-graph":
        cmd_build_view_graph(args)
    elif args.command == "build-vector":
        cmd_build_vector(args)
    elif args.command == "vector-db":
        cmd_vector_db(args)
    elif args.command == "eval-search":
        cmd_eval_search(args)
    elif args.command == "init-schema":
        cmd_init_schema(args)
    else:
        raise SystemExit(f"Unknown command: {args.command}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open-Rosalind Local Bio-KB / Hybrid BioRAG utilities")
    parser.add_argument("--config", default="configs/standard.yaml", help="Path to YAML config")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Show configured Standard KB status")
    _add_config_arg(status)

    search = subparsers.add_parser("search", help="Run local hybrid retrieval")
    _add_config_arg(search)
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--modes", default=None, help="Comma-separated modes: auto,fts,blast,graph,vector")
    search.add_argument("--use-graph", action="store_true", help="Force graph expansion")
    search.add_argument(
        "--vector-target",
        default=None,
        help="Vector target collection: text, protein_sequence_window, dna_sequence_window, mixed",
    )

    answer = subparsers.add_parser("answer", help="Build a DRAG answer scaffold with citations")
    _add_config_arg(answer)
    answer.add_argument("query")
    answer.add_argument("--limit", type=int, default=10)
    answer.add_argument("--context-limit", type=int, default=8)
    answer.add_argument("--max-evidence-chars", type=int, default=900)
    answer.add_argument("--modes", default=None, help="Comma-separated modes: auto,fts,blast,graph,vector")
    answer.add_argument("--use-graph", action="store_true", help="Force graph expansion")
    answer.add_argument(
        "--vector-target",
        default=None,
        help="Vector target collection: text, protein_sequence_window, dna_sequence_window, mixed",
    )

    seq = subparsers.add_parser("sequence-search", help="Run BLAST against the local Swiss-Prot DB")
    _add_config_arg(seq)
    seq.add_argument("sequence")
    seq.add_argument("--max-targets", type=int, default=5)

    graph = subparsers.add_parser("build-graph", help="Build the DRAG graph index")
    _add_config_arg(graph)
    graph.add_argument("--limit", type=int, default=0, help="Limit Standard documents, 0 means all")
    graph.add_argument("--reactome-edge-limit", type=int, default=200000)
    graph.add_argument("--skip-sidecars", action="store_true", help="Only write graph.sqlite and manifest")

    view_graph = subparsers.add_parser(
        "build-view-graph",
        help="Build a text-style DRAG view graph from a Chroma vector collection",
    )
    _add_config_arg(view_graph)
    view_graph.add_argument(
        "--target",
        default="mixed",
        help="Chroma target: text, protein_sequence_window, dna_sequence_window, mixed",
    )
    view_graph.add_argument("--limit", type=int, default=1000, help="Number of vector records to sample")
    view_graph.add_argument("--neighbors", type=int, default=5, help="Nearest-neighbor edges per record")
    view_graph.add_argument("--min-score", type=float, default=None, help="Optional cosine-score threshold")
    view_graph.add_argument("--output", default=None, help="Optional output graph SQLite path")

    vector = subparsers.add_parser("build-vector", help="Build vector artifacts")
    _add_config_arg(vector)
    vector.add_argument(
        "--targets",
        default="text",
        help="Comma-separated targets: text,entity,protein_sequence,dna_sequence,protein_sequence_window,dna_sequence_window,mixed,sequence",
    )
    vector.add_argument(
        "--backend",
        choices=[
            "hashing",
            "omnigene",
            "transformers4bit",
            "omnigene4bit",
            "gguf",
            "hf_encoder",
            "esm",
            "esm2",
            "prott5",
            "dnabert",
            "nucleotide",
        ],
        default="hashing",
    )
    vector.add_argument("--model", default=None)
    vector.add_argument("--pooling", choices=["mean", "last", "eos", "cls"], default=None)
    vector.add_argument("--dtype", choices=["auto", "bf16", "fp16", "fp32"], default=None)
    vector.add_argument("--batch-size", type=int, default=None)
    vector.add_argument("--limit", type=int, default=1000)
    vector.add_argument("--store", choices=["files", "chroma"], default="files")
    vector.add_argument("--append", action="store_true", help="Append/resume Chroma target instead of replacing it")
    vector.add_argument("--sequence-window-size", type=int, default=None, help="Window length for *_sequence_window targets")
    vector.add_argument("--sequence-stride", type=int, default=None, help="Window stride for *_sequence_window targets")
    vector.add_argument(
        "--sequence-source-limit",
        type=int,
        default=None,
        help="Maximum source FASTA records to window; 0 means all",
    )

    vector_db = subparsers.add_parser("vector-db", help="Manage local vector databases")
    _add_config_arg(vector_db)
    vector_db.add_argument("action", choices=["status", "import", "get", "add", "upsert", "update", "delete"])
    vector_db.add_argument("--engine", choices=["chroma", "simple"], default="chroma")
    vector_db.add_argument("--target", default="text")
    vector_db.add_argument("--targets", default="text", help="Comma-separated targets to import from .npz/.jsonl")
    vector_db.add_argument("--batch-size", type=int, default=1000)
    vector_db.add_argument("--records-jsonl", default=None, help="JSONL records with embeddings for add/upsert/update")
    vector_db.add_argument("--ids", default=None, help="Comma-separated Chroma ids for get/delete")
    vector_db.add_argument("--record-ids", default=None, help="Comma-separated original record ids for get/delete")
    vector_db.add_argument("--limit", type=int, default=10)

    eval_search = subparsers.add_parser("eval-search", help="Evaluate basic local search conditions")
    _add_config_arg(eval_search)
    eval_search.add_argument("--benchmark", default="benchmarks/basic_search.jsonl")
    eval_search.add_argument(
        "--conditions",
        default="classical,vector,drag,hybrid",
        help=f"Comma-separated conditions: {','.join(DEFAULT_CONDITIONS)}",
    )
    eval_search.add_argument("--limit", type=int, default=10)
    eval_search.add_argument("--output", default=None, help="Optional JSON output path")
    eval_search.add_argument("--progress", action="store_true", help="Print task progress to stdout")
    eval_search.add_argument("--summary-only", action="store_true", help="Print only summary metrics")

    schema = subparsers.add_parser("init-schema", help="Create an empty canonical Local Bio-KB SQLite DB")
    _add_config_arg(schema)
    schema.add_argument("db_path")

    return parser.parse_args(argv)


def _add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=argparse.SUPPRESS, help=argparse.SUPPRESS)


def cmd_status(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    standard = StandardKB(config.sqlite_path, config.manifest_path)
    graph = GraphStore(config.graph_db)
    result = {
        "config": as_jsonable(config),
        "standard": standard.status(),
        "graph": graph.status(),
        "vector_db": SimpleVectorDB(config.vector_dir).status(),
        "chroma": ChromaVectorDB(config.vector_dir).status(),
    }
    print_json(result)


def cmd_search(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    modes = _modes(args.modes)
    result = HybridBioSearch(config).search(
        args.query,
        modes=modes,
        limit=args.limit,
        use_graph=args.use_graph or None,
        vector_target=args.vector_target,
    )
    print_json(result)


def cmd_answer(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    modes = _modes(args.modes)
    result = DragBioAnswer(config).build(
        args.query,
        modes=modes,
        limit=args.limit,
        context_limit=args.context_limit,
        max_evidence_chars=args.max_evidence_chars,
        use_graph=args.use_graph or None,
        vector_target=args.vector_target,
    )
    print_json(result)


def cmd_sequence_search(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    try:
        result = LocalBlastSearch(config.blast_db, nucleotide_db=config.blastn_db).search(
            args.sequence,
            max_targets=args.max_targets,
        )
    except BlastUnavailable as exc:
        result = {"route": "blast", "status": "unavailable", "error": str(exc), "hits": []}
    print_json(result)


def cmd_build_graph(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    result = GraphIndexBuilder(config).build(
        limit=args.limit,
        reactome_edge_limit=args.reactome_edge_limit,
        write_sidecars=not args.skip_sidecars,
    )
    print_json(result.to_dict())


def cmd_build_view_graph(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    result = VectorViewGraphBuilder(config).build(
        target=args.target,
        limit=args.limit,
        neighbors=args.neighbors,
        min_score=args.min_score,
        output=args.output,
    )
    print_json(result.to_dict())


def cmd_build_vector(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    result = VectorIndexBuilder(config).build(
        targets=_split_csv(args.targets),
        backend=args.backend,
        model_name=args.model,
        pooling=args.pooling,
        dtype=args.dtype,
        batch_size=args.batch_size,
        limit=args.limit,
        store=args.store,
        append=args.append,
        sequence_window_size=args.sequence_window_size,
        sequence_stride=args.sequence_stride,
        sequence_source_limit=args.sequence_source_limit,
    )
    print_json(result.to_dict())


def cmd_vector_db(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    vector_db = ChromaVectorDB(config.vector_dir) if args.engine == "chroma" else SimpleVectorDB(config.vector_dir)
    if args.action == "status":
        print_json(vector_db.status())
        return
    if args.action == "import":
        if args.engine == "chroma":
            results = {
                target: vector_db.import_legacy(target, batch_size=args.batch_size)
                for target in _split_csv(args.targets)
            }
            print_json({"engine": "chroma", "persist_dir": str(vector_db.persist_dir), "imported": results})
        else:
            results = {target: vector_db.import_legacy(target) for target in _split_csv(args.targets)}
            print_json({"engine": "simple", "db_path": str(vector_db.db_path), "imported": results})
        return
    if args.engine != "chroma":
        raise SystemExit(f"Action '{args.action}' is only supported for --engine chroma")
    if args.action == "get":
        print_json(
            {
                "engine": "chroma",
                "target": args.target,
                "records": vector_db.get_records(
                    args.target,
                    ids=_split_csv(args.ids) if args.ids else None,
                    record_ids=_split_csv(args.record_ids) if args.record_ids else None,
                    limit=args.limit,
                ),
            }
        )
        return
    if args.action == "delete":
        print_json(
            {
                "engine": "chroma",
                **vector_db.delete_records(
                    args.target,
                    ids=_split_csv(args.ids) if args.ids else None,
                    record_ids=_split_csv(args.record_ids) if args.record_ids else None,
                ),
            }
        )
        return
    records, embeddings, documents = _read_vector_records_jsonl(args.records_jsonl)
    if args.action == "add":
        result = vector_db.add_records(args.target, records, embeddings, documents=documents)
    elif args.action == "upsert":
        result = vector_db.upsert_records(args.target, records, embeddings, documents=documents)
    elif args.action == "update":
        result = vector_db.update_records(args.target, records, embeddings=embeddings, documents=documents)
    else:
        raise SystemExit(f"Unknown vector-db action: {args.action}")
    print_json({"engine": "chroma", "target": args.target, "result": result})


def cmd_eval_search(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    tasks = load_benchmark(args.benchmark)
    result = SearchEvaluator(config).run(
        tasks,
        conditions=_split_csv(args.conditions),
        limit=args.limit,
        progress=bool(args.progress),
    )
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.summary_only:
        print_json(
            {
                "dataset": result["dataset"],
                "task_count": result["task_count"],
                "limit": result["limit"],
                "summary": result["summary"],
                "category_summary": result.get("category_summary", {}),
                "query_type_summary": result.get("query_type_summary", {}),
                "elapsed_s": result["elapsed_s"],
                "output": args.output,
            }
        )
    else:
        print_json(result)


def cmd_init_schema(args: argparse.Namespace) -> None:
    path = initialize_schema(Path(args.db_path))
    print_json({"db_path": str(path), "status": "created"})


def _modes(value: str | None) -> list[str] | None:
    if not value:
        return None
    return _split_csv(value)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _read_vector_records_jsonl(path: str | None):
    if not path:
        raise SystemExit("--records-jsonl is required for add/upsert/update")
    records: list[dict[str, Any]] = []
    embeddings: list[list[float]] = []
    documents: list[str] = []
    has_document = False
    with Path(path).open("rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            embedding = row.pop("embedding", None)
            if embedding is None:
                raise SystemExit(f"Missing embedding in {path}")
            document = row.pop("document", None)
            if document is not None:
                has_document = True
            records.append(row)
            embeddings.append([float(value) for value in embedding])
            documents.append(str(document or ""))
    import numpy as np

    return records, np.asarray(embeddings, dtype=np.float32), documents if has_document else None


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
