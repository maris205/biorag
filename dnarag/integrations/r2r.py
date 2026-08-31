"""Export and import authoritative SeqLit evidence for an R2R v3 application.

R2R remains responsible for document CRUD, text retrieval, collections, and the
application Agent. BioRAG remains responsible for sequence encoders, BLAST, and
the curated sequence-to-literature evidence graph. The bridge therefore imports
pre-processed text and explicit graph records instead of asking an LLM to
re-extract biological relations from prose.
"""
from __future__ import annotations

import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


SEQUENCE_MODALITIES = {"dna_sequence", "dna_sequence_window", "protein_sequence", "protein_sequence_window"}
PROVENANCE_FIELDS = (
    "source_database",
    "source_record",
    "evidence_level",
    "retrieval_score",
    "verification_method",
    "database_version",
)
R2R_API_VERSION = "v3"
DEFAULT_AGENT_SELECTOR_CONFIG = {
    "function": {"candidate_k": 5, "output_k": 3},
    "literature": {"candidate_k": 5, "output_k": 5},
}


@dataclass(slots=True)
class R2RBundleResult:
    output_dir: Path
    manifest_path: Path
    document_count: int
    entity_count: int
    relationship_count: int
    skipped_sequence_documents: int

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["output_dir"] = str(self.output_dir)
        result["manifest_path"] = str(self.manifest_path)
        return result


@dataclass(slots=True)
class R2RImportResult:
    collection_id: str
    imported_documents: int
    imported_entities: int
    imported_relationships: int
    skipped_documents: int
    skipped_entities: int
    skipped_relationships: int
    state_path: Path

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["state_path"] = str(self.state_path)
        return result


def build_r2r_bundle(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    include_sequence_documents: bool = False,
    documents_file: str | Path | None = None,
    heldout_queries_file: str | Path | None = None,
    documents_only: bool = False,
    document_limit: int = 0,
    entity_limit: int = 0,
    relationship_limit: int = 0,
) -> R2RBundleResult:
    """Build an R2R-ready document and authoritative graph bundle."""
    source = Path(source_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    source_manifest = _read_json(source / "manifest.json", default={})
    snapshot = _snapshot_label(source_manifest)

    nodes = [] if documents_only else list(_read_jsonl(source / "nodes.jsonl", limit=entity_limit))
    node_by_id = {str(row["entity_id"]): row for row in nodes}
    entities = [_to_r2r_entity(row, snapshot=snapshot) for row in nodes]

    relationships: list[dict[str, Any]] = []
    edge_rows = () if documents_only else _read_jsonl(source / "edges.jsonl", limit=relationship_limit)
    for row in edge_rows:
        source_id = str(row["source_entity_id"])
        target_id = str(row["target_entity_id"])
        if source_id not in node_by_id or target_id not in node_by_id:
            raise ValueError(f"Dangling SeqLit-DAG edge: {source_id} -> {target_id}")
        relationships.append(
            _to_r2r_relationship(
                row,
                source_node=node_by_id[source_id],
                target_node=node_by_id[target_id],
                snapshot=snapshot,
            )
        )

    documents: list[dict[str, Any]] = []
    skipped_sequences = 0
    document_source = Path(documents_file) if documents_file else source / "documents.jsonl"
    heldout_query_source = Path(heldout_queries_file) if heldout_queries_file else None
    heldout_accessions = (
        {
            str(row.get("heldout_accession") or "").strip()
            for row in _read_jsonl(heldout_query_source)
            if str(row.get("heldout_accession") or "").strip()
        }
        if heldout_query_source
        else set()
    )
    indexed_accessions: set[str] = set()
    for row in _read_jsonl(document_source):
        accession = str(row.get("accession") or "").strip()
        if accession:
            indexed_accessions.add(accession)
        modality = str(row.get("modality") or "")
        if modality in SEQUENCE_MODALITIES and not include_sequence_documents:
            skipped_sequences += 1
            continue
        documents.append(_to_r2r_document(row, snapshot=snapshot))
        if document_limit and len(documents) >= document_limit:
            break

    heldout_overlap = sorted(indexed_accessions & heldout_accessions)
    if heldout_overlap:
        preview = ", ".join(heldout_overlap[:10])
        raise ValueError(
            f"R2R document collection contains {len(heldout_overlap)} held-out parent accessions: {preview}"
        )

    _write_jsonl(output / "documents.jsonl", documents)
    _write_jsonl(output / "entities.jsonl", entities)
    _write_jsonl(output / "relationships.jsonl", relationships)
    manifest = {
        "dataset": "BioRAG-SeqLit-DAG R2R application bundle",
        "version": "0.1.0",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_dir": str(source),
        "documents_source": str(document_source),
        "source_dataset_version": source_manifest.get("version"),
        "source_snapshot": snapshot,
        "r2r_contract": {
            "api_version": R2R_API_VERSION,
            "minimum_tested_sdk": "3.6.6",
            "document_ingestion": "preprocessed chunks with metadata",
            "graph_ingestion": "explicit entities and relationships; no LLM relation extraction",
        },
        "routing_contract": {
            "natural_language": "R2R hybrid text retrieval",
            "protein_sequence": "BioRAG protein encoder shortlist -> BLASTP verification -> SeqLit-DAG",
            "dna_sequence": "BioRAG DNA encoder shortlist -> BLASTN verification",
            "agent_context": "normalized typed evidence pack",
        },
        "claim_boundary": (
            "R2R is the application and text-RAG substrate. Raw biological sequences are excluded from generic "
            "text embedding by default; BioRAG performs sequence retrieval and biological verification."
        ),
        "provenance_fields": list(PROVENANCE_FIELDS),
        "include_sequence_documents": include_sequence_documents,
        "documents_only": documents_only,
        "leakage_audit": {
            "heldout_queries_file": str(heldout_query_source) if heldout_query_source else None,
            "heldout_parent_count": len(heldout_accessions),
            "indexed_accession_count": len(indexed_accessions),
            "exact_accession_overlap": len(heldout_overlap),
        },
        "counts": {
            "documents": len(documents),
            "entities": len(entities),
            "relationships": len(relationships),
            "skipped_sequence_documents": skipped_sequences,
        },
        "files": {
            "documents": str(output / "documents.jsonl"),
            "entities": str(output / "entities.jsonl"),
            "relationships": str(output / "relationships.jsonl"),
        },
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return R2RBundleResult(
        output_dir=output,
        manifest_path=manifest_path,
        document_count=len(documents),
        entity_count=len(entities),
        relationship_count=len(relationships),
        skipped_sequence_documents=skipped_sequences,
    )


def import_r2r_bundle(
    client: Any,
    bundle_dir: str | Path,
    *,
    collection_id: str | None = None,
    collection_name: str = "BioRAG SeqLit Evidence",
    state_path: str | Path | None = None,
    import_documents: bool = True,
    import_graph: bool = True,
    document_limit: int = 0,
    entity_limit: int = 0,
    relationship_limit: int = 0,
    document_workers: int = 1,
) -> R2RImportResult:
    """Import a bundle through the public R2R v3 SDK with resumable state."""
    bundle = Path(bundle_dir)
    state_file = Path(state_path) if state_path else bundle / "r2r_import_state.json"
    state = _read_json(state_file, default={})
    collection_id = collection_id or str(state.get("collection_id") or "") or _create_collection(
        client, collection_name
    )
    state["collection_id"] = collection_id
    state.setdefault("documents", {})
    state.setdefault("entities", {})
    state.setdefault("relationships", {})
    counts = {
        "imported_documents": 0,
        "imported_entities": 0,
        "imported_relationships": 0,
        "skipped_documents": 0,
        "skipped_entities": 0,
        "skipped_relationships": 0,
    }

    if import_documents:
        pending_documents = []
        for row in _read_jsonl(bundle / "documents.jsonl", limit=document_limit):
            local_id = str(row["local_id"])
            if local_id in state["documents"]:
                counts["skipped_documents"] += 1
                continue
            pending_documents.append(row)
        workers = max(1, int(document_workers))
        if workers == 1:
            for row in pending_documents:
                local_id, remote_id = _import_r2r_document(client, collection_id, row)
                state["documents"][local_id] = remote_id
                counts["imported_documents"] += 1
                _checkpoint(state_file, state, counts["imported_documents"])
        else:
            failures: list[tuple[str, Exception]] = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(_import_r2r_document, client, collection_id, row): str(row["local_id"])
                    for row in pending_documents
                }
                for future in as_completed(futures):
                    local_id = futures[future]
                    try:
                        _, remote_id = future.result()
                    except Exception as exc:  # Preserve all successful IDs before failing the run.
                        failures.append((local_id, exc))
                        continue
                    state["documents"][local_id] = remote_id
                    counts["imported_documents"] += 1
                    _checkpoint(state_file, state, counts["imported_documents"])
            _write_state(state_file, state)
            if failures:
                local_id, exc = failures[0]
                raise RuntimeError(
                    f"R2R document import failed for {len(failures)} records; first failure: {local_id}: {exc}"
                ) from exc

    if import_graph:
        for row in _read_jsonl(bundle / "entities.jsonl", limit=entity_limit):
            local_id = str(row["local_id"])
            if local_id in state["entities"]:
                counts["skipped_entities"] += 1
                continue
            response = client.graphs.create_entity(
                collection_id=collection_id,
                name=str(row["name"]),
                description=str(row["description"]),
                category=str(row["category"]),
                metadata=dict(row["metadata"]),
            )
            remote_id = _response_id(response)
            if not remote_id:
                raise RuntimeError(f"R2R did not return an entity ID for {local_id}")
            state["entities"][local_id] = remote_id
            counts["imported_entities"] += 1
            _checkpoint(state_file, state, counts["imported_entities"])

        for row in _read_jsonl(bundle / "relationships.jsonl", limit=relationship_limit):
            local_id = str(row["local_id"])
            if local_id in state["relationships"]:
                counts["skipped_relationships"] += 1
                continue
            subject_local_id = str(row["subject_local_id"])
            object_local_id = str(row["object_local_id"])
            if subject_local_id not in state["entities"] or object_local_id not in state["entities"]:
                raise RuntimeError(f"R2R entity mapping missing for relationship {local_id}")
            response = client.graphs.create_relationship(
                collection_id=collection_id,
                subject=str(row["subject"]),
                subject_id=state["entities"][subject_local_id],
                predicate=str(row["predicate"]),
                object=str(row["object"]),
                object_id=state["entities"][object_local_id],
                description=str(row["description"]),
                weight=float(row["weight"]) if row.get("weight") is not None else None,
                metadata=dict(row["metadata"]),
            )
            state["relationships"][local_id] = _response_id(response) or "created"
            counts["imported_relationships"] += 1
            _checkpoint(state_file, state, counts["imported_relationships"])

    _write_state(state_file, state)
    return R2RImportResult(collection_id=collection_id, state_path=state_file, **counts)


def _import_r2r_document(
    client: Any,
    collection_id: str,
    row: dict[str, Any],
) -> tuple[str, str]:
    local_id = str(row["local_id"])
    deterministic_id = str(_document_uuid(local_id))
    try:
        response = client.documents.create(
            chunks=list(row["chunks"]),
            id=deterministic_id,
            ingestion_mode="fast",
            collection_ids=[collection_id],
            metadata=dict(row["metadata"]),
            run_with_orchestration=False,
        )
    except Exception as exc:
        if "already ingested and is not in a failed state" not in str(exc):
            raise
        existing = client.documents.retrieve(deterministic_id)
        remote = _value(existing, "results") or existing
        remote_metadata = dict(_value(remote, "metadata") or {})
        expected_record_id = str(dict(row["metadata"]).get("biorag_record_id") or "")
        remote_record_id = str(remote_metadata.get("biorag_record_id") or "")
        if expected_record_id and remote_record_id != expected_record_id:
            raise RuntimeError(
                f"R2R deterministic document ID collision for {local_id}: "
                f"expected {expected_record_id}, found {remote_record_id or 'missing metadata'}"
            ) from exc
        remote_collections = {str(item) for item in (_value(remote, "collection_ids") or [])}
        if collection_id not in remote_collections:
            client.collections.add_document(id=collection_id, document_id=deterministic_id)
        return local_id, deterministic_id
    return local_id, _response_id(response) or deterministic_id


def search_r2r_text_control(
    client: Any,
    query: str,
    *,
    collection_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Run the generic R2R semantic route used only as a text-RAG control."""
    response = client.retrieval.search(
        query=query,
        search_mode="custom",
        search_settings={
            "use_semantic_search": True,
            "use_fulltext_search": False,
            "use_hybrid_search": False,
            "filters": {"collection_ids": {"$overlap": [collection_id]}},
            "limit": limit,
            "include_metadatas": True,
            "include_scores": True,
            "graph_settings": {"enabled": False},
        },
    )
    chunks = _search_chunks(response)
    return [
        {
            "id": str(_value(chunk, "id") or ""),
            "document_id": str(_value(chunk, "document_id") or ""),
            "score": float(_value(chunk, "score") or 0.0),
            "text": str(_value(chunk, "text") or ""),
            "metadata": dict(_value(chunk, "metadata") or {}),
        }
        for chunk in chunks
    ]


def build_r2r_text_control_pack(
    query: dict[str, Any],
    chunks: Iterable[dict[str, Any]],
    *,
    selector_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize R2R chunks into the evidence-pack contract used by Agent ablations."""
    chunk_rows = list(chunks)
    candidate_rows: list[dict[str, Any]] = []
    candidate_by_accession: dict[str, dict[str, Any]] = {}
    ordered_pmids: list[str] = []
    for chunk in chunk_rows:
        metadata = dict(chunk.get("metadata") or {})
        pmids = _string_list(metadata.get("pmids"))
        ordered_pmids.extend(pmids)
        accession = str(metadata.get("accession") or "").strip()
        if not accession:
            continue
        if accession not in candidate_by_accession:
            candidate = {
                "rank": len(candidate_rows) + 1,
                "accession": accession,
                "symbol": str(metadata.get("symbol") or ""),
                "go_ids": _string_list(metadata.get("go_ids")),
                "paper_ids": pmids,
                "go_pmid_edges": [],
                "sequence_evidence": metadata.get("retrieval_role") == "sequence_payload_only",
                "retrieval_score": float(chunk.get("score") or 0.0),
                "go_bridge": [],
                "paper_bridge": [],
            }
            candidate_by_accession[accession] = candidate
            candidate_rows.append(candidate)
            continue
        candidate = candidate_by_accession[accession]
        candidate["go_ids"] = _ordered_unique(candidate["go_ids"] + _string_list(metadata.get("go_ids")))
        candidate["paper_ids"] = _ordered_unique(candidate["paper_ids"] + pmids)

    config = selector_config or DEFAULT_AGENT_SELECTOR_CONFIG
    papers = _ordered_unique(ordered_pmids)
    candidate_k = int(dict(config.get("function") or {}).get("candidate_k", 5))
    prompt_candidates = candidate_rows[:candidate_k]
    expected_accessions = {str(item) for item in query.get("relevant_index_accessions", [])}
    retrieved_accessions = {str(item["accession"]) for item in candidate_rows}
    prompt_go = {str(go) for item in prompt_candidates for go in item["go_ids"]}
    prompt_pmids = {str(pmid) for item in prompt_candidates for pmid in item["paper_ids"]}
    expected_go = {str(item) for item in query.get("expected_go_ids", [])}
    expected_pmids = {str(item) for item in query.get("expected_pmids", [])}
    pack = {
        "query_id": str(query["id"]),
        "query_type": str(query.get("query_type") or ""),
        "task": str(query.get("task") or "heldout_sequence_to_function_to_literature"),
        "candidates": candidate_rows,
        "papers": papers,
        "go_claims": [],
        "paper_claims": [],
        "graph_paths": [],
        "selector_config": config,
    }
    retrieval = {
        "query_id": str(query["id"]),
        "candidate_count": len(candidate_rows),
        "paper_count": len(papers),
        "candidate_hit": bool(expected_accessions & retrieved_accessions),
        "candidate_recall": _recall(retrieved_accessions, expected_accessions),
        "function_prompt_gold_recall": _recall(prompt_go, expected_go),
        "literature_prompt_gold_recall": _recall(prompt_pmids, expected_pmids),
        "r2r_chunk_count": len(chunk_rows),
    }
    return {"retrieval": retrieval, "pack": pack, "application_route": "r2r_text_only"}


def _to_r2r_document(row: dict[str, Any], *, snapshot: str) -> dict[str, Any]:
    text = str(row.get("text") or "").strip()
    metadata = dict(row.get("metadata") or {})
    metadata.update(
        {
            "title": str(row.get("name") or row.get("id") or "BioRAG evidence"),
            "biorag_record_id": str(row.get("record_id") or row.get("id") or ""),
            "modality": str(row.get("modality") or ""),
            "partition": str(row.get("partition") or ""),
            "source_database": str(row.get("source") or "BioRAG-SeqLit-DAG"),
            "database_version": snapshot,
            "accession": str(row.get("accession") or ""),
            "symbol": str(row.get("symbol") or ""),
            "retrieval_role": (
                "sequence_payload_only"
                if str(row.get("modality") or "") in SEQUENCE_MODALITIES
                else "text_evidence"
            ),
            "scientific_sequence_retrieval": False,
        }
    )
    labels = dict(row.get("labels") or {})
    metadata.update(
        {
            "go_ids": [str(item) for item in labels.get("go_ids", [])],
            "pmids": [str(item) for item in labels.get("pmids", [])],
            "evidence_codes": [str(item) for item in labels.get("evidence_codes", [])],
        }
    )
    return {"local_id": str(row["id"]), "chunks": [text], "metadata": metadata}


def _to_r2r_entity(row: dict[str, Any], *, snapshot: str) -> dict[str, Any]:
    local_id = str(row["entity_id"])
    nested = _parse_json_object(row.get("metadata_json"))
    metadata = {
        **nested,
        "biorag_entity_id": local_id,
        "canonical_id": str(row.get("canonical_id") or ""),
        "organism": str(row.get("organism") or ""),
        "source_database": str(row.get("source") or "BioRAG-SeqLit-DAG"),
        "database_version": snapshot,
    }
    return {
        "local_id": local_id,
        "name": str(row.get("name") or row.get("canonical_id") or local_id),
        "description": str(row.get("description") or row.get("name") or local_id),
        "category": str(row.get("entity_type") or "biological_entity"),
        "metadata": metadata,
    }


def _to_r2r_relationship(
    row: dict[str, Any],
    *,
    source_node: dict[str, Any],
    target_node: dict[str, Any],
    snapshot: str,
) -> dict[str, Any]:
    source_id = str(row["source_entity_id"])
    target_id = str(row["target_entity_id"])
    predicate = str(row["relation_type"])
    nested = _parse_json_object(row.get("metadata_json"))
    source_database = str(row.get("source") or source_node.get("source") or "BioRAG-SeqLit-DAG")
    source_record = str(row.get("source_record") or nested.get("references") or source_id)
    evidence_level = str(row.get("evidence_level") or _infer_evidence_level(source_database, nested))
    retrieval_score = row.get("retrieval_score", nested.get("retrieval_score"))
    verification_method = str(
        row.get("verification_method") or _infer_verification_method(source_database, nested)
    )
    database_version = str(row.get("database_version") or _record_snapshot(source_database, nested, snapshot))
    metadata = {
        **nested,
        "biorag_source_entity_id": source_id,
        "biorag_target_entity_id": target_id,
        "source_database": source_database,
        "source_record": source_record,
        "evidence_level": evidence_level,
        "retrieval_score": retrieval_score,
        "verification_method": verification_method,
        "database_version": database_version,
    }
    local_id = f"{source_id}|{predicate}|{target_id}|{source_database}"
    subject = str(source_node.get("name") or source_node.get("canonical_id") or source_id)
    object_name = str(target_node.get("name") or target_node.get("canonical_id") or target_id)
    return {
        "local_id": local_id,
        "subject_local_id": source_id,
        "object_local_id": target_id,
        "subject": subject,
        "predicate": predicate,
        "object": object_name,
        "description": f"{subject} {predicate} {object_name}",
        "weight": row.get("confidence"),
        "metadata": metadata,
    }


def _infer_evidence_level(source: str, metadata: dict[str, Any]) -> str:
    normalized = source.lower()
    if "blast" in normalized:
        return "alignment_verified"
    if "vector" in normalized or "dense" in normalized:
        return "retrieved_unverified"
    if metadata.get("evidence_code"):
        return "curated_experimental_annotation"
    return "curated_database_assertion"


def _infer_verification_method(source: str, metadata: dict[str, Any]) -> str:
    normalized = source.lower()
    if "blast" in normalized:
        return "sequence_alignment"
    if "vector" in normalized or "dense" in normalized:
        return "dense_similarity_only"
    evidence_code = str(metadata.get("evidence_code") or "").strip()
    return f"GOA:{evidence_code}" if evidence_code else "curated_record"


def _record_snapshot(source: str, metadata: dict[str, Any], fallback: str) -> str:
    record_date = str(metadata.get("date") or "").strip()
    return f"{source.replace(' ', '_')}@record-date-{record_date}" if record_date else fallback


def _snapshot_label(manifest: dict[str, Any]) -> str:
    built_at = str(manifest.get("built_at") or "unknown")
    version = str(manifest.get("version") or "unknown")
    return f"BioRAG-SeqLit-DAG-{version}@local-snapshot-{built_at}"


def _create_collection(client: Any, name: str) -> str:
    response = client.collections.create(
        name=name,
        description=(
            "Local-first biological evidence collection. Text retrieval is served by R2R; "
            "sequence candidates and verification are supplied by BioRAG."
        ),
    )
    collection_id = _response_id(response)
    if not collection_id:
        raise RuntimeError("R2R did not return a collection ID")
    return collection_id


def _response_id(response: Any) -> str | None:
    current = response
    if isinstance(current, dict):
        current = current.get("results", current)
        value = current.get("id") or current.get("document_id") if isinstance(current, dict) else None
        return str(value) if value else None
    current = getattr(current, "results", current)
    value = getattr(current, "id", None) or getattr(current, "document_id", None)
    return str(value) if value else None


def _search_chunks(response: Any) -> list[Any]:
    results = _value(response, "results") or response
    chunks = _value(results, "chunk_search_results") or []
    return list(chunks)


def _value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _document_uuid(local_id: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"https://github.com/maris205/biorag/r2r/{local_id}")


def _checkpoint(path: Path, state: dict[str, Any], count: int) -> None:
    if count % 50 == 0:
        _write_state(path, state)


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path, *, limit: int = 0) -> Iterable[dict[str, Any]]:
    with path.open("rt", encoding="utf-8") as handle:
        count = 0
        for line in handle:
            if not line.strip():
                continue
            yield json.loads(line)
            count += 1
            if limit and count >= limit:
                return


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    parsed = json.loads(str(value))
    return dict(parsed) if isinstance(parsed, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return _ordered_unique(str(item) for item in value if str(item))
    return [str(value)] if str(value) else []


def _ordered_unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _recall(retrieved: set[str], expected: set[str]) -> float:
    return len(retrieved & expected) / len(expected) if expected else 0.0
