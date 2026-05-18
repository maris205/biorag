"""DRAG evidence packaging and answer scaffolding."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from dnarag.config import BioKBConfig
from dnarag.retrieval.hybrid import HybridBioSearch
from dnarag.retrieval.sequence import detect_sequence


@dataclass(frozen=True, slots=True)
class DragCitation:
    citation_id: str
    route: str
    title: str
    text: str
    kind: str | None
    entity_id: str | None
    source_id: str | None
    source: str | None
    source_url: str | None
    score: float | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.citation_id,
            "route": self.route,
            "title": self.title,
            "text": self.text,
            "kind": self.kind,
            "entity_id": self.entity_id,
            "source_id": self.source_id,
            "source": self.source,
            "source_url": self.source_url,
            "score": self.score,
            "metadata": self.metadata,
        }


class DragBioAnswer:
    """Build a local-first DRAG context pack for a downstream generator.

    This class intentionally does not call an LLM. It produces an extractive
    scaffold plus a prompt-ready evidence pack that can be passed to Gemma,
    Open-Rosalind, or another local answer model.
    """

    def __init__(self, config: BioKBConfig):
        self.config = config
        self.searcher = HybridBioSearch(config)

    def build(
        self,
        query: str,
        *,
        modes: Iterable[str] | None = None,
        limit: int = 10,
        context_limit: int = 8,
        max_evidence_chars: int = 900,
        use_graph: bool | None = None,
        vector_target: str | None = None,
    ) -> dict[str, Any]:
        retrieval = self.searcher.search(
            query,
            modes=modes,
            limit=limit,
            use_graph=use_graph,
            vector_target=vector_target,
        )
        evidence = list(retrieval.get("evidence") or [])
        selected = evidence[: max(int(context_limit), 1)]
        citations = [
            _citation_from_evidence(index + 1, item, max_chars=max_evidence_chars)
            for index, item in enumerate(selected)
        ]
        citation_map = {_evidence_key(item): citation.citation_id for item, citation in zip(selected, citations)}
        graph_paths = _graph_paths(evidence, citation_map)
        modality_views = _modality_views(query, evidence)
        citation_dicts = [citation.to_dict() for citation in citations]
        answer = _extractive_answer(query, citation_dicts, graph_paths, retrieval)
        generation_prompt = _generation_prompt(query, citation_dicts, graph_paths, modality_views)
        return {
            "query": query,
            "answer": answer,
            "citations": citation_dicts,
            "graph_paths": graph_paths,
            "modality_views": modality_views,
            "generation_prompt": generation_prompt,
            "retrieval_trace": retrieval.get("retrieval_trace", []),
            "local_coverage": retrieval.get("local_coverage", 0.0),
            "fallback_used": retrieval.get("fallback_used", False),
            "raw_evidence_count": len(evidence),
        }


def _citation_from_evidence(index: int, item: dict[str, Any], *, max_chars: int) -> DragCitation:
    metadata = dict(item.get("metadata") or {})
    text = _best_text(item)
    return DragCitation(
        citation_id=f"E{index}",
        route=str(item.get("route") or "unknown"),
        title=str(item.get("title") or item.get("entity_id") or item.get("source_id") or f"evidence-{index}"),
        text=_compact_text(text, limit=max(int(max_chars), 80)),
        kind=_optional_str(item.get("kind")),
        entity_id=_optional_str(item.get("entity_id")),
        source_id=_optional_str(item.get("source_id")),
        source=_optional_str(item.get("source")),
        source_url=_optional_str(item.get("source_url")),
        score=_optional_float(item.get("score")),
        metadata=metadata,
    )


def _best_text(item: dict[str, Any]) -> str:
    route = str(item.get("route") or "")
    if route == "graph":
        metadata = dict(item.get("metadata") or {})
        source = metadata.get("source_name") or metadata.get("source_entity_id")
        relation = metadata.get("relation_type")
        target = metadata.get("target_name") or metadata.get("target_entity_id")
        if source and relation and target:
            return f"{source} --{relation}--> {target}"
    return str(item.get("snippet") or item.get("document") or "")


def _graph_paths(evidence: list[dict[str, Any]], citation_map: dict[str, str]) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    for item in evidence:
        if item.get("route") != "graph":
            continue
        metadata = dict(item.get("metadata") or {})
        paths.append(
            {
                "id": f"P{len(paths) + 1}",
                "citation_id": citation_map.get(_evidence_key(item)),
                "source_entity_id": metadata.get("source_entity_id"),
                "source_type": metadata.get("source_type"),
                "source_name": metadata.get("source_name"),
                "relation_type": metadata.get("relation_type"),
                "target_entity_id": metadata.get("target_entity_id"),
                "target_type": metadata.get("target_type"),
                "target_name": metadata.get("target_name"),
                "edge_source": metadata.get("source"),
                "confidence": metadata.get("confidence"),
            }
        )
    return paths


def _modality_views(query: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    seq = detect_sequence(query)
    route_counts = Counter(str(item.get("route") or "unknown") for item in evidence)
    modality_counts = Counter(_evidence_modality(item) for item in evidence)
    views = {
        "query": {
            "is_sequence": seq is not None,
            "sequence_type": seq.sequence_type if seq else None,
            "alphabet": seq.alphabet if seq else None,
            "length": seq.length if seq else None,
        },
        "routes": dict(route_counts),
        "modalities": dict(modality_counts),
        "active_views": sorted(name for name, count in modality_counts.items() if count),
    }
    return views


def _evidence_modality(item: dict[str, Any]) -> str:
    metadata = dict(item.get("metadata") or {})
    kind = str(item.get("kind") or metadata.get("kind") or "").lower()
    alphabet = str(metadata.get("alphabet") or "").lower()
    route = str(item.get("route") or "").lower()
    if alphabet == "dna" or any(token in kind for token in ("dna", "cdna", "transcript", "genomic")):
        return "dna_sequence"
    if route == "blast" or alphabet == "protein" or any(token in kind for token in ("protein", "peptide")):
        return "protein_sequence"
    if route == "graph" or kind == "graph_relation":
        return "graph_relation"
    return "text_knowledge"


def _extractive_answer(
    query: str,
    citations: list[dict[str, Any]],
    graph_paths: list[dict[str, Any]],
    retrieval: dict[str, Any],
) -> str:
    if not citations:
        return (
            "No local DRAG evidence was retrieved. Use the retrieval trace to inspect missing indexes "
            "or run a narrower query."
        )
    routes = sorted({str(item.get("route")) for item in citations})
    lines = [
        f"Local DRAG retrieved {len(citations)} cited evidence items for: {query}",
        f"Routes used in the context: {', '.join(routes)}.",
    ]
    if graph_paths:
        lines.append(f"Graph expansion contributed {len(graph_paths)} relation path(s).")
    coverage = retrieval.get("local_coverage")
    if coverage is not None:
        lines.append(f"Local coverage estimate: {coverage}.")
    lines.append("Top local evidence:")
    for item in citations[: min(len(citations), 4)]:
        title = item.get("title") or item.get("entity_id") or "Untitled evidence"
        source = item.get("source") or item.get("route") or "local"
        text = _compact_text(item.get("text"), limit=220)
        lines.append(f"[{item.get('id')}] {title} ({source}): {text}")
    lines.append("A downstream generator should answer only from these citations and cite every claim.")
    return "\n".join(lines)


def _generation_prompt(
    query: str,
    citations: list[dict[str, Any]],
    graph_paths: list[dict[str, Any]],
    modality_views: dict[str, Any],
) -> str:
    blocks = [
        "You are a local-first biomedical DRAG answerer.",
        "Use only the evidence below. Cite claims with bracket IDs such as [E1].",
        "If evidence is insufficient, say what is missing instead of using model memory.",
        "",
        f"User query: {query}",
        "",
        "Modality views:",
        _format_value(modality_views),
        "",
        "Evidence:",
    ]
    if citations:
        for item in citations:
            blocks.append(
                "\n".join(
                    [
                        f"[{item.get('id')}] {item.get('title')}",
                        f"route={item.get('route')} kind={item.get('kind')} source={item.get('source')}",
                        str(item.get("text") or ""),
                    ]
                )
            )
    else:
        blocks.append("No local evidence.")
    if graph_paths:
        blocks.extend(["", "Graph paths:"])
        for path in graph_paths:
            blocks.append(
                (
                    f"[{path.get('id')}] {path.get('source_name') or path.get('source_entity_id')} "
                    f"--{path.get('relation_type')}--> "
                    f"{path.get('target_name') or path.get('target_entity_id')}"
                )
            )
    return "\n".join(blocks)


def _format_value(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key in sorted(value):
            parts.append(f"- {key}: {value[key]}")
        return "\n".join(parts)
    return str(value)


def _evidence_key(item: dict[str, Any]) -> str:
    return "|".join(
        [
            str(item.get("route") or ""),
            str(item.get("entity_id") or ""),
            str(item.get("source_id") or ""),
            str(item.get("title") or ""),
        ]
    )


def _compact_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def _optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
