#!/usr/bin/env python3
"""Export SeqLit-DAG to R2R v3 and optionally import it into a live server."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.integrations.r2r import build_r2r_bundle, import_r2r_bundle


def main() -> None:
    args = parse_args()
    bundle = build_r2r_bundle(
        args.source,
        args.output,
        include_sequence_documents=args.include_sequence_documents,
        document_limit=args.document_limit,
        entity_limit=args.entity_limit,
        relationship_limit=args.relationship_limit,
    )
    result: dict[str, object] = {"bundle": bundle.to_dict()}
    if args.ingest:
        try:
            from r2r import R2RClient
        except ImportError as exc:
            raise SystemExit("Install the optional R2R SDK with `pip install 'r2r>=3.6,<4'`.") from exc
        client = R2RClient(base_url=args.base_url)
        imported = import_r2r_bundle(
            client,
            args.output,
            collection_id=args.collection_id,
            collection_name=args.collection_name,
            state_path=args.state,
            import_documents=not args.skip_documents,
            import_graph=not args.skip_graph,
            document_limit=args.document_limit,
            entity_limit=args.entity_limit,
            relationship_limit=args.relationship_limit,
        )
        result["import"] = imported.to_dict()
    print(json.dumps(result, indent=2, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an R2R v3 application bundle from SeqLit-DAG")
    parser.add_argument("--source", default="data/seq_lit_dag_swissprot_sample")
    parser.add_argument("--output", default="outputs/r2r/seq_lit_dag_swissprot_sample")
    parser.add_argument("--include-sequence-documents", action="store_true")
    parser.add_argument("--document-limit", type=int, default=0)
    parser.add_argument("--entity-limit", type=int, default=0)
    parser.add_argument("--relationship-limit", type=int, default=0)
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument("--base-url", default="http://localhost:7272")
    parser.add_argument("--collection-id", default=None)
    parser.add_argument("--collection-name", default="BioRAG SeqLit Evidence")
    parser.add_argument("--state", default=None)
    parser.add_argument("--skip-documents", action="store_true")
    parser.add_argument("--skip-graph", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
