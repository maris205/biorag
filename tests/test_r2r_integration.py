import json
from pathlib import Path
from types import SimpleNamespace

from dnarag.integrations.r2r import (
    PROVENANCE_FIELDS,
    build_r2r_bundle,
    build_r2r_text_control_pack,
    import_r2r_bundle,
    search_r2r_text_control,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def make_source(tmp_path: Path) -> Path:
    source = tmp_path / "seq_lit"
    source.mkdir()
    (source / "manifest.json").write_text(
        json.dumps({"version": "0.2.0", "built_at": "2026-08-30T00:00:00Z"}),
        encoding="utf-8",
    )
    write_jsonl(
        source / "nodes.jsonl",
        [
            {
                "entity_id": "protein:P1",
                "entity_type": "protein",
                "canonical_id": "P1",
                "name": "Protein 1",
                "source": "UniProtKB Swiss-Prot",
                "description": "Reviewed protein.",
                "organism": "Homo sapiens",
                "metadata_json": json.dumps({"accession": "P1"}),
            },
            {
                "entity_id": "go_term:GO:0000001",
                "entity_type": "go_term",
                "canonical_id": "GO:0000001",
                "name": "test process",
                "source": "Gene Ontology",
                "description": "Test process.",
                "organism": None,
                "metadata_json": "{}",
            },
        ],
    )
    write_jsonl(
        source / "edges.jsonl",
        [
            {
                "source_entity_id": "protein:P1",
                "relation_type": "annotated_with_go",
                "target_entity_id": "go_term:GO:0000001",
                "source": "GOA",
                "source_record": "evidence:P1:GO_0000001:IDA:1",
                "evidence_level": "curated_experimental_annotation",
                "confidence": 1.0,
                "retrieval_score": None,
                "verification_method": "GOA:IDA",
                "database_version": "GOA@record-date-20260830",
                "metadata_json": json.dumps({"evidence_code": "IDA", "date": "20260830"}),
            }
        ],
    )
    write_jsonl(
        source / "documents.jsonl",
        [
            {
                "id": "seq_lit:protein:P1",
                "record_id": "protein:P1",
                "modality": "protein_sequence",
                "partition": "seq_lit_dag/protein",
                "source": "UniProtKB Swiss-Prot",
                "accession": "P1",
                "name": "Protein 1",
                "text": "[TYPE=protein_sequence]\nSequence:\nMAAA",
            },
            {
                "id": "seq_lit:path:P1:GO1:PMID1",
                "record_id": "evidence:P1:GO1:IDA:1",
                "modality": "mixed",
                "partition": "seq_lit_dag/evidence_path",
                "source": "GOA",
                "accession": "P1",
                "name": "Protein 1 evidence",
                "text": "P1 is annotated with GO:0000001 and supported by PMID:12345678.",
            },
        ],
    )
    return source


def test_r2r_bundle_keeps_authoritative_graph_and_excludes_raw_sequences(tmp_path: Path):
    source = make_source(tmp_path)

    result = build_r2r_bundle(source, tmp_path / "bundle")

    assert result.document_count == 1
    assert result.skipped_sequence_documents == 1
    relationship = json.loads((result.output_dir / "relationships.jsonl").read_text(encoding="utf-8"))
    assert relationship["predicate"] == "annotated_with_go"
    assert all(field in relationship["metadata"] for field in PROVENANCE_FIELDS)
    assert relationship["metadata"]["verification_method"] == "GOA:IDA"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["routing_contract"]["protein_sequence"].startswith("BioRAG")
    assert manifest["r2r_contract"]["graph_ingestion"].startswith("explicit")


def test_r2r_text_control_uses_heldout_index_and_rejects_parent_leakage(tmp_path: Path):
    source = make_source(tmp_path)
    split_documents = tmp_path / "index_documents.jsonl"
    write_jsonl(
        split_documents,
        [
            {
                "id": "seq_lit:protein:P2",
                "record_id": "protein:P2",
                "modality": "protein_sequence",
                "partition": "seq_lit_dag/protein",
                "source": "UniProtKB Swiss-Prot",
                "accession": "P2",
                "name": "Protein 2",
                "text": "[TYPE=protein_sequence]\nSequence:\nMCCC",
                "labels": {"go_ids": ["GO:0000002"], "pmids": ["23456789"]},
            }
        ],
    )
    queries = tmp_path / "queries.jsonl"
    write_jsonl(queries, [{"id": "q1", "heldout_accession": "P1", "query": "MAAA"}])

    result = build_r2r_bundle(
        source,
        tmp_path / "heldout_bundle",
        include_sequence_documents=True,
        documents_file=split_documents,
        heldout_queries_file=queries,
        documents_only=True,
    )

    assert result.document_count == 1
    assert result.entity_count == 0
    assert result.relationship_count == 0
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["leakage_audit"] == {
        "heldout_queries_file": str(queries),
        "heldout_parent_count": 1,
        "indexed_accession_count": 1,
        "exact_accession_overlap": 0,
    }

    write_jsonl(queries, [{"id": "q1", "heldout_accession": "P2", "query": "MCCC"}])
    try:
        build_r2r_bundle(
            source,
            tmp_path / "leaky_bundle",
            include_sequence_documents=True,
            documents_file=split_documents,
            heldout_queries_file=queries,
            documents_only=True,
        )
    except ValueError as exc:
        assert "held-out parent accessions" in str(exc)
    else:
        raise AssertionError("Expected held-out parent leakage to be rejected")


class FakeDocuments:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(results=SimpleNamespace(document_id=kwargs["id"]))


class FakeGraphs:
    def __init__(self):
        self.entities = []
        self.relationships = []

    def create_entity(self, **kwargs):
        self.entities.append(kwargs)
        return SimpleNamespace(results=SimpleNamespace(id=f"entity-{len(self.entities)}"))

    def create_relationship(self, **kwargs):
        self.relationships.append(kwargs)
        return SimpleNamespace(results=SimpleNamespace(id=f"relationship-{len(self.relationships)}"))


class FakeCollections:
    def __init__(self):
        self.calls = []
        self.added_documents = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(results=SimpleNamespace(id="collection-1"))

    def add_document(self, **kwargs):
        self.added_documents.append(kwargs)
        return SimpleNamespace(results=SimpleNamespace(message="added"))


def test_r2r_import_uses_public_v3_shapes_and_is_resumable(tmp_path: Path):
    source = make_source(tmp_path)
    bundle = build_r2r_bundle(source, tmp_path / "bundle")
    client = SimpleNamespace(documents=FakeDocuments(), graphs=FakeGraphs(), collections=FakeCollections())

    first = import_r2r_bundle(client, bundle.output_dir)
    second = import_r2r_bundle(client, bundle.output_dir)

    assert first.collection_id == "collection-1"
    assert first.imported_documents == 1
    assert first.imported_entities == 2
    assert first.imported_relationships == 1
    assert client.documents.calls[0]["ingestion_mode"] == "fast"
    assert client.documents.calls[0]["run_with_orchestration"] is False
    assert client.graphs.relationships[0]["subject_id"] == "entity-1"
    assert client.graphs.relationships[0]["object_id"] == "entity-2"
    assert second.imported_documents == 0
    assert second.skipped_documents == 1
    assert second.skipped_entities == 2
    assert second.skipped_relationships == 1


def test_r2r_import_supports_concurrent_document_requests(tmp_path: Path):
    source = make_source(tmp_path)
    bundle = build_r2r_bundle(source, tmp_path / "bundle", include_sequence_documents=True)
    client = SimpleNamespace(documents=FakeDocuments(), graphs=FakeGraphs(), collections=FakeCollections())

    result = import_r2r_bundle(client, bundle.output_dir, import_graph=False, document_workers=2)

    assert result.imported_documents == 2
    assert len(client.documents.calls) == 2
    assert len({call["id"] for call in client.documents.calls}) == 2


def test_r2r_import_recovers_remote_success_before_local_checkpoint(tmp_path: Path):
    class AlreadyIngestedDocuments(FakeDocuments):
        def create(self, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError(
                f"Document {kwargs['id']} was already ingested and is not in a failed state."
            )

        def retrieve(self, document_id):
            return SimpleNamespace(
                results=SimpleNamespace(
                    id=document_id,
                    collection_ids=["previous-collection"],
                    metadata={"biorag_record_id": "evidence:P1:GO1:IDA:1"},
                )
            )

    source = make_source(tmp_path)
    bundle = build_r2r_bundle(source, tmp_path / "bundle")
    collections = FakeCollections()
    client = SimpleNamespace(
        documents=AlreadyIngestedDocuments(),
        graphs=FakeGraphs(),
        collections=collections,
    )

    result = import_r2r_bundle(
        client,
        bundle.output_dir,
        collection_id="collection-1",
        import_graph=False,
    )

    assert result.imported_documents == 1
    assert collections.added_documents == [
        {"id": "collection-1", "document_id": client.documents.calls[0]["id"]}
    ]


def test_r2r_text_control_disables_graph_and_preserves_metadata():
    class FakeRetrieval:
        def __init__(self):
            self.kwargs = None

        def search(self, **kwargs):
            self.kwargs = kwargs
            return {
                "results": {
                    "chunk_search_results": [
                        {
                            "id": "chunk-1",
                            "document_id": "doc-1",
                            "score": 0.7,
                            "text": "sequence evidence",
                            "metadata": {"accession": "P1", "pmids": ["12345678"]},
                        }
                    ]
                }
            }

    retrieval = FakeRetrieval()
    client = SimpleNamespace(retrieval=retrieval)

    rows = search_r2r_text_control(client, "MAAA", collection_id="collection-1", limit=20)

    assert rows[0]["metadata"]["accession"] == "P1"
    settings = retrieval.kwargs["search_settings"]
    assert settings["graph_settings"]["enabled"] is False
    assert settings["filters"] == {"collection_ids": {"$overlap": ["collection-1"]}}
    assert settings["limit"] == 20


def test_r2r_chunks_are_normalized_to_agent_pack():
    query = {
        "id": "q1",
        "query_type": "heldout_parent_middle_fragment",
        "task": "heldout_sequence_to_function_to_literature",
        "relevant_index_accessions": ["P1"],
        "expected_go_ids": ["GO:0000001"],
        "expected_pmids": ["12345678"],
    }
    chunks = [
        {
            "score": 0.9,
            "metadata": {
                "accession": "P1",
                "symbol": "GENE1",
                "go_ids": ["GO:0000001"],
                "pmids": ["12345678"],
                "retrieval_role": "sequence_payload_only",
            },
        },
        {
            "score": 0.8,
            "metadata": {
                "accession": "P1",
                "go_ids": ["GO:0000002"],
                "pmids": ["23456789"],
            },
        },
    ]

    row = build_r2r_text_control_pack(query, chunks)

    assert row["application_route"] == "r2r_text_only"
    assert len(row["pack"]["candidates"]) == 1
    assert row["pack"]["candidates"][0]["go_ids"] == ["GO:0000001", "GO:0000002"]
    assert row["pack"]["papers"] == ["12345678", "23456789"]
    assert row["retrieval"]["candidate_hit"] is True
    assert row["retrieval"]["function_prompt_gold_recall"] == 1.0
    assert row["retrieval"]["literature_prompt_gold_recall"] == 1.0
