#!/usr/bin/env python3
"""Merge same-node DRAG view graphs while preserving relation types."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.localdb.graph_builder import _graph_schema


def main() -> None:
    args = parse_args()
    base_graph = Path(args.base_graph)
    overlay_graph = Path(args.overlay_graph)
    output = Path(args.output)
    if not base_graph.exists():
        raise FileNotFoundError(base_graph)
    if not overlay_graph.exists():
        raise FileNotFoundError(overlay_graph)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    base = read_graph(base_graph)
    overlay = read_graph(overlay_graph)
    if set(base["nodes"]) != set(overlay["nodes"]):
        missing_overlay = sorted(set(base["nodes"]) - set(overlay["nodes"]))[:5]
        missing_base = sorted(set(overlay["nodes"]) - set(base["nodes"]))[:5]
        raise SystemExit(
            "Graphs must have the same node set. "
            f"Missing in overlay examples={missing_overlay}; missing in base examples={missing_base}"
        )
    write_merged(output, base=base, overlay=overlay, base_graph=base_graph, overlay_graph=overlay_graph)
    result = {
        "graph_db": str(output),
        "base_graph": str(base_graph),
        "overlay_graph": str(overlay_graph),
        "node_count": len(base["nodes"]),
        "edge_rows": len(base["edges"]) + len(overlay["edges"]),
        "relation_counts": relation_counts([*base["edges"], *overlay["edges"]]),
    }
    print(json.dumps(result, indent=2))


def read_graph(path: Path) -> dict[str, Any]:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        nodes = {
            str(row["entity_id"]): dict(row)
            for row in conn.execute(
                """
                SELECT entity_id, entity_type, canonical_id, name, source, description, organism, metadata_json
                FROM nodes
                ORDER BY entity_id
                """
            )
        }
        aliases = [
            dict(row)
            for row in conn.execute(
                """
                SELECT entity_id, alias, alias_type, source
                FROM aliases
                ORDER BY entity_id, alias
                """
            )
        ]
        edges = [
            dict(row)
            for row in conn.execute(
                """
                SELECT source_entity_id, relation_type, target_entity_id, source, confidence, metadata_json
                FROM edges
                ORDER BY source_entity_id, relation_type, target_entity_id, source
                """
            )
        ]
        meta = {
            str(row["key"]): str(row["value"])
            for row in conn.execute("SELECT key, value FROM graph_meta")
        } if table_exists(conn, "graph_meta") else {}
    return {"nodes": nodes, "aliases": aliases, "edges": edges, "meta": meta}


def write_merged(
    path: Path,
    *,
    base: dict[str, Any],
    overlay: dict[str, Any],
    base_graph: Path,
    overlay_graph: Path,
) -> None:
    edges = [*base["edges"], *overlay["edges"]]
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
                    row["entity_id"],
                    row["entity_type"],
                    row["canonical_id"],
                    row["name"],
                    row["source"],
                    row["description"],
                    row["organism"],
                    row["metadata_json"],
                )
                for row in base["nodes"].values()
            ],
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO aliases (entity_id, alias, alias_type, source)
            VALUES (?, ?, ?, ?)
            """,
            [
                (row["entity_id"], row["alias"], row["alias_type"], row["source"])
                for row in [*base["aliases"], *overlay["aliases"]]
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
                    row["source_entity_id"],
                    row["relation_type"],
                    row["target_entity_id"],
                    row["source"],
                    row["confidence"],
                    row["metadata_json"],
                )
                for row in edges
            ],
        )
        meta = [
            ("view_graph", "true"),
            ("recipe", "hybrid_vector_blast_neighbors"),
            ("target", base["meta"].get("target") or overlay["meta"].get("target") or ""),
            ("base_graph", str(base_graph)),
            ("overlay_graph", str(overlay_graph)),
            ("base_recipe", base["meta"].get("recipe", "")),
            ("overlay_recipe", overlay["meta"].get("recipe", "")),
            ("biological_rules_used", "true"),
            ("node_count", str(len(base["nodes"]))),
            ("edge_rows", str(len(edges))),
            ("relation_counts", json.dumps(relation_counts(edges), sort_keys=True)),
        ]
        conn.executemany("INSERT INTO graph_meta(key, value) VALUES (?, ?)", meta)


def relation_counts(edges: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in edges:
        relation = str(edge.get("relation_type") or "")
        counts[relation] = counts.get(relation, 0) + 1
    return counts


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (name,),
        ).fetchone()
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge same-node DRAG view graphs")
    parser.add_argument("--base-graph", required=True, help="Base graph, typically vector-neighbor graph")
    parser.add_argument("--overlay-graph", required=True, help="Overlay graph, typically BLAST-neighbor graph")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()
