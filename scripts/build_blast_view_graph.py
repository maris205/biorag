#!/usr/bin/env python3
"""Build a BLAST-edge DRAG view graph over an existing sequence view graph."""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.localdb.graph_builder import _graph_schema


def main() -> None:
    args = parse_args()
    input_graph = Path(args.input_graph)
    output_graph = Path(args.output)
    if not input_graph.exists():
        raise FileNotFoundError(input_graph)
    output_graph.parent.mkdir(parents=True, exist_ok=True)
    if output_graph.exists():
        output_graph.unlink()

    nodes, aliases, source_meta = read_source_graph(input_graph, min_sequence_length=args.min_sequence_length)
    alphabet = args.alphabet or infer_alphabet(nodes)
    if alphabet not in {"dna", "protein"}:
        raise SystemExit(f"Could not infer BLAST alphabet for {input_graph}; pass --alphabet dna|protein")
    executable = shutil.which("blastn" if alphabet == "dna" else "blastp")
    makeblastdb = shutil.which("makeblastdb")
    if not executable or not makeblastdb:
        raise SystemExit("BLAST+ executables are required: makeblastdb and blastn/blastp")

    with tempfile.TemporaryDirectory(prefix="dnarag_blast_view_") as tmp:
        tmp_path = Path(tmp)
        fasta_path = tmp_path / "nodes.fasta"
        query_path = tmp_path / "queries.fasta"
        db_path = tmp_path / "blast_db"
        write_fasta(nodes, fasta_path)
        write_fasta(nodes, query_path)
        make_db(makeblastdb, fasta_path=fasta_path, db_path=db_path, alphabet=alphabet)
        rows = run_blast(
            executable,
            query_path=query_path,
            db_path=db_path,
            alphabet=alphabet,
            max_target_seqs=max(args.neighbors + 1, args.blast_max_targets),
            evalue=args.evalue,
        )

    edge_count = write_output_graph(
        output_graph,
        nodes=nodes,
        aliases=aliases,
        source_meta=source_meta,
        alphabet=alphabet,
        blast_rows=rows,
        neighbors=args.neighbors,
        min_identity=args.min_identity,
        min_alignment_fraction=args.min_alignment_fraction,
        input_graph=input_graph,
    )
    result = {
        "graph_db": str(output_graph),
        "input_graph": str(input_graph),
        "alphabet": alphabet,
        "node_count": len(nodes),
        "edge_count": edge_count,
        "neighbors": args.neighbors,
        "min_identity": args.min_identity,
        "min_alignment_fraction": args.min_alignment_fraction,
        "evalue": args.evalue,
    }
    print(json.dumps(result, indent=2))


def read_source_graph(path: Path, *, min_sequence_length: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        node_rows = conn.execute(
            """
            SELECT entity_id, entity_type, canonical_id, name, source, description, organism, metadata_json
            FROM nodes
            ORDER BY entity_id
            """
        ).fetchall()
        alias_rows = conn.execute(
            """
            SELECT entity_id, alias, alias_type, source
            FROM aliases
            ORDER BY entity_id, alias
            """
        ).fetchall()
        meta_rows = (
            conn.execute("SELECT key, value FROM graph_meta ORDER BY key").fetchall()
            if table_exists(conn, "graph_meta")
            else []
        )
    nodes: list[dict[str, Any]] = []
    for row in node_rows:
        sequence = normalize_sequence(row["description"])
        if len(sequence) < min_sequence_length:
            continue
        nodes.append(
            {
                "entity_id": str(row["entity_id"]),
                "entity_type": str(row["entity_type"]),
                "canonical_id": row["canonical_id"],
                "name": row["name"],
                "source": row["source"],
                "description": sequence,
                "organism": row["organism"],
                "metadata_json": row["metadata_json"],
                "sequence_length": len(sequence),
            }
        )
    valid_ids = {node["entity_id"] for node in nodes}
    aliases = [dict(row) for row in alias_rows if str(row["entity_id"]) in valid_ids]
    source_meta = {str(row["key"]): str(row["value"]) for row in meta_rows}
    return nodes, aliases, source_meta


def write_output_graph(
    path: Path,
    *,
    nodes: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
    source_meta: dict[str, str],
    alphabet: str,
    blast_rows: list[dict[str, Any]],
    neighbors: int,
    min_identity: float,
    min_alignment_fraction: float,
    input_graph: Path,
) -> int:
    node_by_id = {node["entity_id"]: node for node in nodes}
    selected = select_edges(
        blast_rows,
        node_by_id=node_by_id,
        neighbors=neighbors,
        min_identity=min_identity,
        min_alignment_fraction=min_alignment_fraction,
    )
    with sqlite3.connect(path) as conn:
        conn.executescript(_graph_schema())
        conn.execute("CREATE TABLE graph_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.executemany(
            """
            INSERT INTO nodes
            (entity_id, entity_type, canonical_id, name, source, description, organism, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    node["entity_id"],
                    node["entity_type"],
                    node["canonical_id"],
                    node["name"],
                    node["source"],
                    node["description"],
                    node["organism"],
                    node["metadata_json"],
                )
                for node in nodes
            ],
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO aliases (entity_id, alias, alias_type, source)
            VALUES (?, ?, ?, ?)
            """,
            [
                (row["entity_id"], row["alias"], row["alias_type"], row["source"])
                for row in aliases
            ],
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO edges
            (source_entity_id, relation_type, target_entity_id, source, confidence, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    edge["source"],
                    "blast_neighbor",
                    edge["target"],
                    f"BLAST:{alphabet}",
                    edge["confidence"],
                    json.dumps(edge["metadata"], ensure_ascii=False, separators=(",", ":")),
                )
                for edge in selected
            ],
        )
        conn.executemany(
            "INSERT INTO graph_meta(key, value) VALUES (?, ?)",
            [
                ("view_graph", "true"),
                ("recipe", "blast_sequence_neighbors"),
                ("target", source_meta.get("target", "")),
                ("alphabet", alphabet),
                ("source_graph", str(input_graph)),
                ("source_recipe", source_meta.get("recipe", "")),
                ("record_count", str(source_meta.get("record_count", ""))),
                ("node_count", str(len(nodes))),
                ("neighbor_count", str(neighbors)),
                ("min_identity", str(min_identity)),
                ("min_alignment_fraction", str(min_alignment_fraction)),
                ("biological_rules_used", "true"),
            ],
        )
    return len(selected)


def select_edges(
    rows: list[dict[str, Any]],
    *,
    node_by_id: dict[str, dict[str, Any]],
    neighbors: int,
    min_identity: float,
    min_alignment_fraction: float,
) -> list[dict[str, Any]]:
    by_query: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        query = row["query"]
        subject = row["subject"]
        if query == subject:
            continue
        query_node = node_by_id.get(query)
        subject_node = node_by_id.get(subject)
        if not query_node or not subject_node:
            continue
        identity = float(row["pident"])
        coverage = float(row["length"]) / max(min(query_node["sequence_length"], subject_node["sequence_length"]), 1)
        if identity < min_identity or coverage < min_alignment_fraction:
            continue
        row = {**row, "coverage": round(min(coverage, 1.0), 6)}
        by_query.setdefault(query, []).append(row)
    selected: list[dict[str, Any]] = []
    for query, query_rows in by_query.items():
        ranked = sorted(
            query_rows,
            key=lambda item: (float(item["bitscore"]), float(item["pident"]), int(item["length"])),
            reverse=True,
        )
        for rank, row in enumerate(ranked[: max(int(neighbors), 1)], start=1):
            selected.append(
                {
                    "source": query,
                    "target": row["subject"],
                    "confidence": float(row["pident"]) / 100.0,
                    "metadata": {
                        "rank": rank,
                        "pident": row["pident"],
                        "alignment_length": row["length"],
                        "coverage": row["coverage"],
                        "evalue": row["evalue"],
                        "bitscore": row["bitscore"],
                        "graph_recipe": "blast_sequence_neighbors",
                        "biological_rules_used": True,
                    },
                }
            )
    return selected


def run_blast(
    executable: str,
    *,
    query_path: Path,
    db_path: Path,
    alphabet: str,
    max_target_seqs: int,
    evalue: float,
) -> list[dict[str, Any]]:
    task = "blastn-short" if alphabet == "dna" else "blastp-short"
    if alphabet == "protein":
        task = "blastp-short"
    cmd = [
        executable,
        "-task",
        task,
        "-query",
        str(query_path),
        "-db",
        str(db_path),
        "-outfmt",
        "6 qseqid sseqid pident length evalue bitscore",
        "-max_target_seqs",
        str(max(int(max_target_seqs), 1)),
        "-evalue",
        str(evalue),
    ]
    completed = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr[-2000:])
    rows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        query, subject, pident, length, evalue_text, bitscore = line.split("\t")[:6]
        rows.append(
            {
                "query": decode_fasta_id(query),
                "subject": decode_fasta_id(subject),
                "pident": float(pident),
                "length": int(length),
                "evalue": float(evalue_text),
                "bitscore": float(bitscore),
            }
        )
    return rows


def make_db(makeblastdb: str, *, fasta_path: Path, db_path: Path, alphabet: str) -> None:
    dbtype = "nucl" if alphabet == "dna" else "prot"
    completed = subprocess.run(
        [makeblastdb, "-in", str(fasta_path), "-dbtype", dbtype, "-out", str(db_path), "-parse_seqids"],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr[-2000:])


def write_fasta(nodes: list[dict[str, Any]], path: Path) -> None:
    with path.open("wt", encoding="utf-8") as handle:
        for node in nodes:
            handle.write(f">{encode_fasta_id(node['entity_id'])}\n")
            handle.write(wrap_sequence(node["description"]) + "\n")


def infer_alphabet(nodes: list[dict[str, Any]]) -> str | None:
    entity_types = {str(node["entity_type"]).lower() for node in nodes}
    if any("dna" in value for value in entity_types):
        return "dna"
    if any("protein" in value for value in entity_types):
        return "protein"
    return None


def normalize_sequence(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalpha() or ch == "*")


def encode_fasta_id(value: str) -> str:
    return str(value).replace(":", "__COLON__").replace("|", "__PIPE__").replace(" ", "__SPACE__")


def decode_fasta_id(value: str) -> str:
    return str(value).replace("__SPACE__", " ").replace("__PIPE__", "|").replace("__COLON__", ":")


def wrap_sequence(sequence: str, width: int = 80) -> str:
    return "\n".join(sequence[start : start + width] for start in range(0, len(sequence), width))


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (name,),
        ).fetchone()
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a BLAST-edge view graph from sequence nodes")
    parser.add_argument("--input-graph", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--alphabet", choices=["dna", "protein"], default=None)
    parser.add_argument("--neighbors", type=int, default=5)
    parser.add_argument("--blast-max-targets", type=int, default=25)
    parser.add_argument("--min-identity", type=float, default=30.0)
    parser.add_argument("--min-alignment-fraction", type=float, default=0.5)
    parser.add_argument("--min-sequence-length", type=int, default=20)
    parser.add_argument("--evalue", type=float, default=10.0)
    return parser.parse_args()


if __name__ == "__main__":
    main()
