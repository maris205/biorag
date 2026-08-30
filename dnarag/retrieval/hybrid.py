"""Hybrid BioRAG retrieval with auditable evidence traces."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dnarag.config import BioKBConfig
from dnarag.localdb.graph import GraphStore
from dnarag.localdb.standard import StandardKB
from dnarag.retrieval.sequence import BlastUnavailable, LocalBlastSearch, detect_sequence
from dnarag.retrieval.vector import HashingEmbedder, cosine_search, make_embedder, sequence_window_texts
from dnarag.retrieval.vector_db import ChromaVectorDB, SimpleVectorDB, VectorDBHit


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    route: str
    status: str
    input: str
    output_count: int
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "status": self.status,
            "input": self.input,
            "output_count": self.output_count,
            "metadata": self.metadata,
        }


class HybridBioSearch:
    def __init__(self, config: BioKBConfig):
        self.config = config
        self.standard = StandardKB(config.sqlite_path, config.manifest_path)
        self.graph = GraphStore(config.graph_db)
        self.blast = LocalBlastSearch(config.blast_db, nucleotide_db=config.blastn_db)
        self._embedder_cache: dict[tuple[str, str, str, str], Any] = {}

    def search(
        self,
        query: str,
        *,
        modes: Iterable[str] | None = None,
        limit: int = 10,
        use_graph: bool | None = None,
        vector_target: str | None = None,
    ) -> dict[str, Any]:
        requested_modes = tuple(modes or self.config.retrieval.default_modes)
        seq = detect_sequence(query)
        auto_routed = "auto" in requested_modes
        selected_modes = set(plan_retrieval_modes(query) if auto_routed else requested_modes)
        if use_graph is True:
            selected_modes.add("graph")
        if use_graph is False:
            selected_modes.discard("graph")

        evidence: list[dict[str, Any]] = []
        traces: list[RetrievalTrace] = []
        if auto_routed:
            traces.append(
                RetrievalTrace(
                    "router",
                    "ok",
                    query[:80],
                    len(selected_modes),
                    {
                        "requested_modes": list(requested_modes),
                        "selected_modes": sorted(selected_modes),
                        "sequence_type": seq.sequence_type if seq else None,
                        "sequence_length": seq.length if seq else None,
                    },
                )
            )

        if "fts" in selected_modes:
            fts_hits = self.standard.search_text(query, limit=limit)
            evidence.extend(hit.to_evidence(route="fts") for hit in fts_hits)
            traces.append(RetrievalTrace("fts", "ok", query, len(fts_hits), {"sqlite": str(self.config.sqlite_path)}))

        if "blast" in selected_modes and seq is not None:
            try:
                blast_result = self.blast.search(query, max_targets=min(limit, 10))
                blast_hits = [
                    _blast_hit_to_evidence(hit, sequence_type=blast_result.get("sequence_type"))
                    for hit in blast_result.get("hits", [])
                ]
                evidence.extend(blast_hits)
                traces.append(
                    RetrievalTrace(
                        "blast",
                        str(blast_result.get("status") or "unknown"),
                        seq.sequence[:80],
                        len(blast_hits),
                        {"sequence_type": seq.sequence_type, "length": seq.length, "blast_db": str(self.config.blast_db)},
                    )
                )
            except BlastUnavailable as exc:
                traces.append(RetrievalTrace("blast", "unavailable", seq.sequence[:80], 0, {"error": str(exc)}))

        if "graph" in selected_modes and self.graph.exists:
            graph_hits, graph_trace = self._graph_search(query, evidence=evidence, limit=limit)
            evidence.extend(graph_hits)
            traces.append(graph_trace)
        elif "graph" in selected_modes:
            traces.append(RetrievalTrace("graph", "missing_index", query, 0, {"graph_db": str(self.config.graph_db)}))

        if "vector" in selected_modes:
            vector_hits, vector_trace = self._vector_search(query, limit=limit, target=vector_target)
            evidence.extend(vector_hits)
            traces.append(vector_trace)

        merged = _dedupe_evidence(evidence)
        return {
            "query": query,
            "answer_context": _answer_context(merged[:limit]),
            "evidence": merged[: max(limit * 2, limit)],
            "retrieval_trace": [trace.to_dict() for trace in traces],
            "local_coverage": _coverage(merged, selected_modes),
            "fallback_used": False,
        }

    def _graph_search(
        self,
        query: str,
        *,
        evidence: list[dict[str, Any]],
        limit: int,
    ) -> tuple[list[dict[str, Any]], RetrievalTrace]:
        seed_entity_ids: list[str] = []
        for item in evidence[:limit]:
            entity_id = item.get("entity_id")
            if entity_id:
                seed_entity_ids.append(str(entity_id))
        for item in evidence[:limit]:
            symbol = item.get("symbol")
            if symbol:
                seed_entity_ids.extend(node.entity_id for node in self.graph.resolve_aliases(str(symbol), limit=2))
        seed_entity_ids.extend(node.entity_id for node in self.graph.resolve_aliases(query, limit=limit))
        for item in evidence[:limit]:
            title = item.get("title")
            if title:
                seed_entity_ids.extend(node.entity_id for node in self.graph.resolve_aliases(str(title), limit=2))
        seen_nodes: set[str] = set()
        graph_hits: list[dict[str, Any]] = []
        for entity_id in seed_entity_ids:
            if entity_id in seen_nodes:
                continue
            seen_nodes.add(entity_id)
            for edge in self.graph.expand(entity_id, limit=limit):
                graph_hits.append(_graph_edge_to_evidence(edge))
                if len(graph_hits) >= limit:
                    break
            if len(graph_hits) >= limit:
                break
        status = "ok" if graph_hits else "no_hits"
        return graph_hits, RetrievalTrace("graph", status, query, len(graph_hits), {"resolved_nodes": len(seen_nodes)})

    def _vector_search(
        self,
        query: str,
        limit: int,
        target: str | None = None,
    ) -> tuple[list[dict[str, Any]], RetrievalTrace]:
        chroma_db = ChromaVectorDB(self.config.vector_dir)
        simple_db = SimpleVectorDB(self.config.vector_dir)
        selected_target = target or _default_vector_target(query, chroma_db, simple_db)
        npz_path = self.config.vector_dir / f"{selected_target}.npz"
        id_map_path = self.config.vector_dir / f"{selected_target}_id_map.jsonl"
        manifest_path = self.config.vector_dir / "manifest.json"
        chroma_collection = chroma_db.collection_info(selected_target)
        simple_collection = simple_db.collection_info(selected_target)
        has_chroma = chroma_db.has_collection(selected_target)
        has_simple = simple_db.has_collection(selected_target)
        if not has_chroma and not has_simple and (not npz_path.exists() or not id_map_path.exists()):
            return [], RetrievalTrace(
                "vector",
                "missing_index",
                query,
                0,
                {"vector_dir": str(self.config.vector_dir), "target": selected_target},
            )
        backend = "hashing"
        model = self.config.embedding.model
        pooling = self.config.embedding.pooling
        manifest: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                backend = str(manifest.get("backend") or "hashing")
                model = str(manifest.get("model") or model)
                pooling = str(manifest.get("pooling") or pooling)
            except json.JSONDecodeError:
                backend = "unknown"
        if simple_collection:
            backend = str(simple_collection.get("backend") or backend)
            model = str(simple_collection.get("model") or model)
            pooling = str(simple_collection.get("pooling") or pooling)
        if chroma_collection:
            chroma_metadata = dict(chroma_collection.get("metadata") or {})
            backend = str(chroma_metadata.get("backend") or backend)
            model = str(chroma_metadata.get("model") or model)
            pooling = str(chroma_metadata.get("pooling") or pooling)
        query_texts = _vector_query_texts(
            query,
            target=selected_target,
            chroma_collection=chroma_collection,
            simple_collection=simple_collection,
        )
        if backend == "hashing":
            embedder = HashingEmbedder()
        elif backend in {
            "omnigene",
            "transformers4bit",
            "omnigene4bit",
            "gguf",
            "hf_encoder",
            "esm",
            "esm2",
            "prott5",
            "dnabert",
            "dnabert2",
            "dnabert-2",
            "nucleotide",
            "dna_es2",
            "dna-es2",
        }:
            try:
                embedder = self._get_embedder(backend=backend, model=model, pooling=pooling)
            except Exception as exc:
                return [], RetrievalTrace(
                    "vector",
                    "query_backend_unavailable",
                    query,
                    0,
                    {"backend": backend, "manifest": str(manifest_path), "error": str(exc)},
                )
        else:
            return [], RetrievalTrace(
                "vector",
                "unknown_backend",
                query,
                0,
                {"backend": backend, "manifest": str(manifest_path)},
            )
        query_vectors = embedder.embed(query_texts)
        raw_top_k = _vector_raw_top_k(selected_target, limit)
        if has_chroma:
            hits: list[VectorDBHit] = []
            for query_vector in query_vectors:
                hits.extend(chroma_db.search(selected_target, query_vector, top_k=raw_top_k))
            rerank_enabled = _env_bool("DNARAG_VECTOR_SEQUENCE_RERANK", False) and _is_sequence_vector_target(selected_target)
            hits = (
                _rerank_sequence_vector_hits(hits, query=query, limit=limit)
                if rerank_enabled
                else _merge_vector_hits(hits, limit=limit)
            )
            evidence = [_vector_db_hit_to_evidence(hit) for hit in hits]
            return evidence, RetrievalTrace(
                "vector",
                "ok",
                query,
                len(evidence),
                {
                    "vector_db": str(chroma_db.persist_dir),
                    "engine": "chroma",
                    "target": selected_target,
                    "backend": backend,
                    "model": model,
                    "pooling": pooling,
                    "query_windows": len(query_texts),
                    "raw_top_k": raw_top_k,
                    "sequence_rerank": rerank_enabled,
                },
            )
        if has_simple:
            hits = []
            for query_vector in query_vectors:
                hits.extend(simple_db.search(selected_target, query_vector, top_k=raw_top_k))
            rerank_enabled = _env_bool("DNARAG_VECTOR_SEQUENCE_RERANK", False) and _is_sequence_vector_target(selected_target)
            hits = (
                _rerank_sequence_vector_hits(hits, query=query, limit=limit)
                if rerank_enabled
                else _merge_vector_hits(hits, limit=limit)
            )
            evidence = [_vector_db_hit_to_evidence(hit) for hit in hits]
            return evidence, RetrievalTrace(
                "vector",
                "ok",
                query,
                len(evidence),
                {
                    "vector_db": str(simple_db.db_path),
                    "engine": "simple",
                    "target": selected_target,
                    "backend": backend,
                    "model": model,
                    "pooling": pooling,
                    "query_windows": len(query_texts),
                    "raw_top_k": raw_top_k,
                    "sequence_rerank": rerank_enabled,
                },
            )
        merged_hits: dict[int, float] = {}
        for query_vector in query_vectors:
            for idx, score in cosine_search(npz_path, query_vector, top_k=raw_top_k):
                merged_hits[idx] = max(score, merged_hits.get(idx, float("-inf")))
        hits = sorted(merged_hits.items(), key=lambda item: item[1], reverse=True)[:limit]
        id_map = _load_id_map(id_map_path)
        evidence = []
        for idx, score in hits:
            if idx >= len(id_map):
                continue
            record = id_map[idx]
            evidence.append(
                {
                    "route": "vector",
                    "entity_id": record.get("record_id"),
                    "kind": record.get("metadata", {}).get("kind"),
                    "source_id": record.get("metadata", {}).get("source_id"),
                    "symbol": record.get("metadata", {}).get("symbol"),
                    "title": record.get("metadata", {}).get("symbol") or record.get("record_id"),
                    "snippet": "Vector neighbor from local text index",
                    "score": score,
                    "source": record.get("metadata", {}).get("source"),
                    "source_url": record.get("metadata", {}).get("source_url"),
                    "metadata": record.get("metadata", {}),
                }
            )
        return evidence, RetrievalTrace(
            "vector",
            "ok",
            query,
            len(evidence),
            {
                "npz": str(npz_path),
                "target": selected_target,
                "backend": backend,
                "model": model,
                "pooling": pooling,
                "query_windows": len(query_texts),
                "raw_top_k": raw_top_k,
            },
        )

    def _get_embedder(self, *, backend: str, model: str, pooling: str) -> Any:
        key = (backend, model, pooling, self.config.embedding.dtype)
        embedder = self._embedder_cache.get(key)
        if embedder is None:
            embedder = make_embedder(
                backend,
                model_name=model,
                pooling=pooling,
                dtype=self.config.embedding.dtype,
            )
            self._embedder_cache[key] = embedder
        return embedder


def plan_retrieval_modes(query: str) -> tuple[str, ...]:
    """Choose practical retrieval routes for the route-gated BioRAG condition."""
    seq = detect_sequence(query)
    if seq is not None:
        return ("blast", "vector")
    return ("fts", "graph", "vector")


def _blast_hit_to_evidence(hit: dict[str, Any], sequence_type: Any = None) -> dict[str, Any]:
    accession = _accession_from_blast_id(hit.get("sseqid"))
    metadata = dict(hit)
    if accession:
        metadata["accession"] = accession
    sequence_kind = "dna_sequence" if str(sequence_type) == "dna" else "protein_sequence"
    source = "Ensembl cDNA BLAST" if sequence_kind == "dna_sequence" else "Swiss-Prot BLAST"
    return {
        "route": "blast",
        "entity_id": f"{sequence_kind}:{accession or hit.get('sseqid')}",
        "kind": "sequence_similarity",
        "source_id": accession or hit.get("sseqid"),
        "symbol": None,
        "title": hit.get("title") or hit.get("sseqid"),
        "snippet": f"pident={hit.get('pident')} length={hit.get('alignment_length')} evalue={hit.get('evalue')}",
        "score": hit.get("bitscore"),
        "source": source,
        "source_url": None,
        "metadata": metadata,
    }


def _graph_edge_to_evidence(edge: dict[str, Any]) -> dict[str, Any]:
    title = f"{edge.get('source_name') or edge.get('source_entity_id')} {edge.get('relation_type')} {edge.get('target_name') or edge.get('target_entity_id')}"
    return {
        "route": "graph",
        "entity_id": edge.get("target_entity_id"),
        "kind": "graph_relation",
        "source_id": edge.get("target_entity_id"),
        "symbol": None,
        "title": title,
        "snippet": json.dumps(
            {
                "source": edge.get("source_entity_id"),
                "relation": edge.get("relation_type"),
                "target": edge.get("target_entity_id"),
            },
            ensure_ascii=False,
        ),
        "score": edge.get("confidence"),
        "source": edge.get("source"),
        "source_url": None,
        "metadata": edge,
    }


def _vector_db_hit_to_evidence(hit: VectorDBHit) -> dict[str, Any]:
    metadata = hit.metadata
    document = str(hit.document or "")
    return {
        "route": "vector",
        "entity_id": metadata.get("parent_record_id") or hit.record_id,
        "kind": metadata.get("kind"),
        "source_id": metadata.get("source_id") or metadata.get("accession"),
        "symbol": metadata.get("symbol"),
        "title": _vector_hit_title(hit),
        "snippet": _compact_text(document, limit=500) if document else "Vector neighbor from local vector database",
        "score": hit.score,
        "source": metadata.get("source"),
        "source_url": metadata.get("source_url"),
        "metadata": metadata,
        "document": document or None,
    }


def _default_vector_target(query: str, chroma_db: ChromaVectorDB, simple_db: SimpleVectorDB) -> str:
    seq = detect_sequence(query)
    if seq and seq.alphabet == "dna":
        for target in ("dna_sequence_window", "dna_sequence"):
            if _target_exists(target, chroma_db, simple_db):
                return target
    if seq and seq.alphabet == "protein":
        for target in ("protein_sequence_window", "protein_sequence"):
            if _target_exists(target, chroma_db, simple_db):
                return target
    return "text"


def _target_exists(target: str, chroma_db: ChromaVectorDB, simple_db: SimpleVectorDB) -> bool:
    chroma_info = chroma_db.collection_info(target)
    if chroma_info and int(chroma_info.get("count") or 0) > 0:
        return True
    simple_info = simple_db.collection_info(target)
    if simple_info and int(simple_info.get("count") or 0) > 0 and simple_db.has_collection(target):
        return True
    return False


def _merge_vector_hits(hits: list[VectorDBHit], *, limit: int) -> list[VectorDBHit]:
    best: dict[str, VectorDBHit] = {}
    for hit in hits:
        key = hit.record_id or f"{hit.target}:{hit.row_idx}"
        existing = best.get(key)
        if existing is None or hit.score > existing.score:
            best[key] = hit
    return sorted(best.values(), key=lambda item: item.score, reverse=True)[: max(int(limit), 1)]


def _rerank_sequence_vector_hits(hits: list[VectorDBHit], *, query: str, limit: int) -> list[VectorDBHit]:
    seq = detect_sequence(query)
    if seq is None:
        return _merge_vector_hits(hits, limit=limit)
    query_sequence = seq.sequence
    groups: dict[str, list[VectorDBHit]] = {}
    for hit in hits:
        metadata = hit.metadata
        key = str(metadata.get("parent_record_id") or hit.record_id or f"{hit.target}:{hit.row_idx}")
        groups.setdefault(key, []).append(hit)
    reranked: list[VectorDBHit] = []
    for parent_hits in groups.values():
        scored_hits = [(_sequence_rerank_score(hit, query_sequence=query_sequence), hit) for hit in parent_hits]
        scored_hits.sort(key=lambda item: item[0], reverse=True)
        score, best_hit = scored_hits[0]
        metadata = dict(best_hit.metadata)
        metadata["vector_score"] = best_hit.score
        metadata["sequence_rerank_score"] = round(score, 6)
        metadata["sequence_window_votes"] = len(parent_hits)
        reranked.append(
            VectorDBHit(
                row_idx=best_hit.row_idx,
                score=score,
                record_id=best_hit.record_id,
                target=best_hit.target,
                metadata=metadata,
                document=best_hit.document,
            )
        )
    return sorted(reranked, key=lambda item: item.score, reverse=True)[: max(int(limit), 1)]


def _sequence_rerank_score(hit: VectorDBHit, *, query_sequence: str) -> float:
    hit_sequence = _sequence_from_hit(hit)
    if not hit_sequence:
        return float(hit.score)
    overlap = _sequence_overlap_score(query_sequence, hit_sequence)
    vector_weight = _env_float("DNARAG_VECTOR_SEQUENCE_RERANK_VECTOR_WEIGHT", 0.25)
    overlap_weight = _env_float("DNARAG_VECTOR_SEQUENCE_RERANK_OVERLAP_WEIGHT", 0.75)
    vote_weight = _env_float("DNARAG_VECTOR_SEQUENCE_RERANK_VOTE_WEIGHT", 0.0)
    return (overlap_weight * overlap) + (vector_weight * float(hit.score)) + vote_weight


def _sequence_overlap_score(query_sequence: str, hit_sequence: str) -> float:
    query_clean = _clean_sequence_text(query_sequence)
    hit_clean = _clean_sequence_text(hit_sequence)
    if not query_clean or not hit_clean:
        return 0.0
    if query_clean in hit_clean or hit_clean in query_clean:
        return 1.0
    exact = _longest_common_substring_len(query_clean, hit_clean) / max(min(len(query_clean), len(hit_clean)), 1)
    k = min(_env_int("DNARAG_VECTOR_SEQUENCE_RERANK_KMER", 5), len(query_clean), len(hit_clean))
    if k <= 0:
        return exact
    query_kmers = _kmers(query_clean, k)
    hit_kmers = _kmers(hit_clean, k)
    if not query_kmers or not hit_kmers:
        return exact
    containment = len(query_kmers & hit_kmers) / max(min(len(query_kmers), len(hit_kmers)), 1)
    return max(exact, containment)


def _sequence_from_hit(hit: VectorDBHit) -> str:
    document = str(hit.document or "")
    if document:
        return document
    metadata = hit.metadata
    return str(metadata.get("sequence") or metadata.get("window_sequence") or "")


def _clean_sequence_text(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalpha() or ch == "*")


def _kmers(sequence: str, k: int) -> set[str]:
    if k <= 0 or len(sequence) < k:
        return set()
    return {sequence[index : index + k] for index in range(len(sequence) - k + 1)}


def _longest_common_substring_len(left: str, right: str) -> int:
    if not left or not right:
        return 0
    if len(left) > len(right):
        left, right = right, left
    previous = [0] * (len(right) + 1)
    best = 0
    for lchar in left:
        current = [0] * (len(right) + 1)
        for index, rchar in enumerate(right, start=1):
            if lchar == rchar:
                current[index] = previous[index - 1] + 1
                if current[index] > best:
                    best = current[index]
        previous = current
    return best


def _vector_query_texts(
    query: str,
    *,
    target: str,
    chroma_collection: dict[str, Any] | None,
    simple_collection: dict[str, Any] | None,
) -> list[str]:
    seq = detect_sequence(query)
    if seq is None or not _is_sequence_vector_target(target):
        return [query]
    if not target.endswith("_window"):
        return [seq.sequence]
    metadata = dict((chroma_collection or {}).get("metadata") or {})
    window_size = int(metadata.get("window_size") or _env_int("DNARAG_SEQUENCE_WINDOW_SIZE", 128))
    stride = int(metadata.get("stride") or _env_int("DNARAG_SEQUENCE_STRIDE", 64))
    max_windows = max(_env_int("DNARAG_VECTOR_QUERY_MAX_WINDOWS", 8), 1)
    include_full = seq.length <= max(window_size * 2, 512)
    texts = sequence_window_texts(
        seq.sequence,
        window_size=window_size,
        stride=stride,
        max_windows=max_windows,
        include_full=include_full,
    )
    return texts or [seq.sequence]


def _vector_raw_top_k(target: str, limit: int) -> int:
    requested = max(int(limit), 1)
    if target.endswith("_window"):
        multiplier = max(_env_int("DNARAG_VECTOR_WINDOW_RAW_MULTIPLIER", 100), 1)
        minimum = max(_env_int("DNARAG_VECTOR_WINDOW_RAW_MIN", 1000), requested)
        maximum = max(_env_int("DNARAG_VECTOR_WINDOW_RAW_MAX", 5000), minimum)
        return min(max(requested * multiplier, minimum), maximum)
    return requested


def _is_sequence_vector_target(target: str) -> bool:
    return target in {"protein_sequence", "dna_sequence", "protein_sequence_window", "dna_sequence_window", "sequence"}


def _vector_hit_title(hit: VectorDBHit) -> str:
    metadata = hit.metadata
    title = metadata.get("symbol") or metadata.get("accession") or hit.record_id
    if metadata.get("window_id"):
        return f"{title} [{metadata.get('window_start')}-{metadata.get('window_end')}]"
    return str(title)


def _dedupe_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    merged: list[dict[str, Any]] = []
    for item in evidence:
        key = (str(item.get("route")), str(item.get("entity_id") or item.get("source_id") or item.get("title")))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _answer_context(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "title": item.get("title"),
            "source": item.get("source"),
            "route": item.get("route"),
            "snippet": item.get("snippet") or _compact_text(item.get("document"), limit=500),
            "source_url": item.get("source_url"),
        }
        for item in evidence
    ]


def _compact_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def _accession_from_blast_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "|" in text:
        parts = [part for part in text.split("|") if part]
        if len(parts) >= 2:
            return parts[1]
    return text


def _coverage(evidence: list[dict[str, Any]], modes: set[str]) -> float:
    if not evidence:
        return 0.0
    hit_routes = {str(item.get("route")) for item in evidence}
    active = {mode for mode in modes if mode in {"fts", "blast", "graph", "vector"}}
    if not active:
        return 1.0
    return round(len(hit_routes & active) / len(active), 3)


def _load_id_map(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value in {None, ""}:
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value in {None, ""}:
        return default
    return float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value in {None, ""}:
        return default
    return value.lower() in {"1", "true", "yes", "on"}
