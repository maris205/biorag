#!/usr/bin/env python3
"""Trace graph evidence paths for label-seeded DRAG agent context."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_view_graph import enrich_labels_from_chroma, label_values, read_graph


def main() -> None:
    args = parse_args()
    graph_path = Path(args.graph)
    graph_data = read_graph(graph_path)
    if not args.no_chroma_labels:
        enrich_labels_from_chroma(graph_data, config_path=args.config)
    seed_nodes = find_seed_nodes(graph_data, args.label, limit=args.seed_limit)
    if not seed_nodes:
        raise SystemExit(f"No seed nodes matched label '{args.label}' in {graph_path}")
    adjacency = build_adjacency(graph_data)
    traces = [
        trace_seed(
            seed,
            graph_data=graph_data,
            adjacency=adjacency,
            label=args.label,
            max_edges=args.max_edges,
            depth=args.depth,
        )
        for seed in seed_nodes
    ]
    result = {
        "graph": str(graph_path),
        "recipe": graph_data.get("meta", {}).get("recipe"),
        "target": graph_data.get("meta", {}).get("target"),
        "label": args.label,
        "seed_count": len(seed_nodes),
        "depth": args.depth,
        "max_edges": args.max_edges,
        "summary": summarize_traces(traces),
        "traces": traces,
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"graph": str(graph_path), "label": args.label, "summary": result["summary"]}, indent=2))


def find_seed_nodes(graph_data: dict[str, Any], label: str, *, limit: int) -> list[str]:
    label_upper = str(label).upper()
    hits = []
    for node_id, node in graph_data["nodes"].items():
        labels = node.get("labels") or {}
        values = all_label_values(labels)
        if any(str(value).upper() == label_upper for value in values):
            hits.append(str(node_id))
    return sorted(hits)[: max(int(limit), 1)]


def build_adjacency(graph_data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    adjacency: dict[str, list[dict[str, Any]]] = {str(node_id): [] for node_id in graph_data["nodes"]}
    for edge in graph_data["edges"]:
        source = str(edge["source"])
        target = str(edge["target"])
        adjacency.setdefault(source, []).append(edge)
        adjacency.setdefault(target, []).append({**edge, "source": target, "target": source, "reversed": True})
    for edges in adjacency.values():
        edges.sort(
            key=lambda item: (
                relation_priority(str(item.get("relation_type") or "")),
                float(item.get("confidence") or 0.0),
            ),
            reverse=True,
        )
    return adjacency


def trace_seed(
    seed: str,
    *,
    graph_data: dict[str, Any],
    adjacency: dict[str, list[dict[str, Any]]],
    label: str,
    max_edges: int,
    depth: int,
) -> dict[str, Any]:
    visited_nodes = {seed}
    selected_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    queue: deque[tuple[str, int]] = deque([(seed, 0)])
    while queue and len(selected_edges) < max_edges:
        node_id, level = queue.popleft()
        if level >= depth:
            continue
        for edge in adjacency.get(node_id, []):
            if len(selected_edges) >= max_edges:
                break
            target = str(edge["target"])
            edge_key = canonical_edge_key(str(edge["source"]), target, str(edge.get("relation_type") or ""))
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            selected_edges.append(edge)
            if target not in visited_nodes:
                visited_nodes.add(target)
                queue.append((target, level + 1))
    node_rows = [node_summary(node_id, graph_data, focus_label=label) for node_id in sorted(visited_nodes)]
    edge_rows = [edge_summary(edge, graph_data, focus_label=label) for edge in selected_edges]
    return {
        "seed": node_summary(seed, graph_data, focus_label=label),
        "node_count": len(visited_nodes),
        "edge_count": len(edge_rows),
        "relation_counts": dict(Counter(row["relation_type"] for row in edge_rows)),
        "focus_label_neighbor_hits": sum(1 for row in node_rows if row["has_focus_label"] and row["entity_id"] != seed),
        "nodes": node_rows,
        "edges": edge_rows,
    }


def node_summary(node_id: str, graph_data: dict[str, Any], *, focus_label: str) -> dict[str, Any]:
    node = graph_data["nodes"][node_id]
    labels = node.get("labels") or {}
    values = all_label_values(labels)
    return {
        "entity_id": node_id,
        "name": node.get("name"),
        "entity_type": node.get("entity_type"),
        "labels": labels,
        "display_labels": compact_labels(labels),
        "has_focus_label": any(str(value).upper() == str(focus_label).upper() for value in values),
    }


def edge_summary(edge: dict[str, Any], graph_data: dict[str, Any], *, focus_label: str) -> dict[str, Any]:
    metadata = edge.get("metadata") or {}
    source = str(edge["source"])
    target = str(edge["target"])
    return {
        "source": source,
        "source_name": graph_data["nodes"].get(source, {}).get("name"),
        "target": target,
        "target_name": graph_data["nodes"].get(target, {}).get("name"),
        "target_labels": compact_labels(graph_data["nodes"].get(target, {}).get("labels") or {}),
        "target_has_focus_label": node_has_label(graph_data, target, focus_label),
        "relation_type": str(edge.get("relation_type") or ""),
        "confidence": round(float(edge.get("confidence") or 0.0), 6),
        "pident": metadata.get("pident"),
        "bitscore": metadata.get("bitscore"),
        "rank": metadata.get("rank"),
        "reversed": bool(edge.get("reversed")),
    }


def summarize_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    relation_counts: Counter[str] = Counter()
    node_counts = []
    edge_counts = []
    focus_hits = []
    for trace in traces:
        relation_counts.update(trace.get("relation_counts") or {})
        node_counts.append(int(trace.get("node_count") or 0))
        edge_counts.append(int(trace.get("edge_count") or 0))
        focus_hits.append(int(trace.get("focus_label_neighbor_hits") or 0))
    return {
        "traces": len(traces),
        "avg_context_nodes": round(sum(node_counts) / max(len(node_counts), 1), 4),
        "avg_context_edges": round(sum(edge_counts) / max(len(edge_counts), 1), 4),
        "avg_focus_label_neighbor_hits": round(sum(focus_hits) / max(len(focus_hits), 1), 4),
        "relation_counts": dict(sorted(relation_counts.items())),
    }


def all_label_values(labels: dict[str, list[str]]) -> list[str]:
    values: list[str] = []
    for label_type in ("gene_id", "gene_symbol", "gene_family", "biotype"):
        values.extend(label_values(labels, label_type))
    return values


def compact_labels(labels: dict[str, list[str]]) -> dict[str, list[str]]:
    result = {}
    for key in ("gene_symbols", "protein_gene_names", "gene_families", "gene_ids", "gene_biotypes", "transcript_biotypes"):
        if labels.get(key):
            result[key] = labels[key][:4]
    return result


def node_has_label(graph_data: dict[str, Any], node_id: str, label: str) -> bool:
    node = graph_data["nodes"].get(node_id) or {}
    values = all_label_values(node.get("labels") or {})
    return any(str(value).upper() == str(label).upper() for value in values)


def relation_priority(relation_type: str) -> int:
    if relation_type == "blast_neighbor":
        return 2
    if relation_type == "vector_neighbor":
        return 1
    return 0


def canonical_edge_key(source: str, target: str, relation_type: str) -> tuple[str, str, str]:
    left, right = sorted([source, target])
    return left, right, relation_type


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trace graph context paths for a biological label")
    parser.add_argument("--graph", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--config", default="configs/standard.yaml")
    parser.add_argument("--seed-limit", type=int, default=5)
    parser.add_argument("--max-edges", type=int, default=20)
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--no-chroma-labels", action="store_true")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    main()
