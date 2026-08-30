from pathlib import Path

from scripts.evaluate_agent_evidence import (
    build_pack,
    evidence_claim_scope,
    evidence_dataset_name,
    load_documents,
    parse_method_files,
    rank_graph_claims,
    score_pack,
)


def test_agent_pack_scores_typed_complete_path():
    query = {
        "id": "q1",
        "expected_accessions": ["P1"],
        "expected_go_ids": ["GO:1"],
        "expected_pmids": ["123"],
    }
    documents = {
        "P1": {"accession": "P1", "symbol": "gene1", "labels": {"go_ids": ["GO:1"], "pmids": ["123"]}}
    }
    row = {"query_id": "q1", "top_accessions": ["P1"], "top_pmids": ["123"]}
    pack = build_pack(query, row, documents, candidate_k=1, paper_k=1)
    scored = score_pack(pack, query)
    assert scored["candidate_hit"] is True
    assert scored["go_bridge_hit"] is True
    assert scored["citation_precision"] == 1.0
    assert scored["path_complete"] is True


def test_method_file_supports_shared_result_method_selector():
    result = parse_method_files(["BLAST=results.json#blast", "ProtT5=vector.json"])
    assert result["BLAST"] == (Path("results.json"), "blast")
    assert result["ProtT5"][1] is None


def test_cluster_agent_evidence_metadata_preserves_split_boundary():
    queries = [{"task": "uniref50_cluster_heldout_sequence_to_function_to_literature"}]
    assert "UniRef50" in evidence_dataset_name(queries)
    assert "observed UniRef50 cluster" in evidence_claim_scope(queries)


def test_load_documents_merges_protein_and_typed_evidence_rows(tmp_path):
    path = tmp_path / "documents.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"accession":"P1","modality":"protein_sequence","symbol":"GENE1",'
                '"labels":{"go_ids":["GO:0000001","GO:0000002"],"pmids":["111","222"]}}',
                '{"accession":"P1","partition":"seq_lit_dag/evidence_path",'
                '"labels":{"go_ids":["GO:0000001"],"pmids":["111"],"evidence_codes":["IDA"]}}',
                '{"accession":"P1","partition":"seq_lit_dag/evidence_path",'
                '"labels":{"go_ids":["GO:0000002"],"pmids":["222"],"evidence_codes":["IMP"]}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    document = load_documents(path)["P1"]

    assert document["symbol"] == "GENE1"
    assert document["labels"]["go_ids"] == ["GO:0000001", "GO:0000002"]
    assert document["labels"]["pmids"] == ["111", "222"]
    assert document["go_pmid_edges"] == [
        {"go_id": "GO:0000001", "pmid": "111", "evidence_codes": ["IDA"]},
        {"go_id": "GO:0000002", "pmid": "222", "evidence_codes": ["IMP"]},
    ]


def test_graph_claim_ranking_uses_rank_and_go_rarity():
    candidates = [
        {
            "rank": 1,
            "accession": "P1",
            "go_ids": ["GO:COMMON", "GO:RARE"],
            "go_pmid_edges": [
                {"go_id": "GO:COMMON", "pmid": "111", "evidence_codes": ["IDA"]},
                {"go_id": "GO:RARE", "pmid": "222", "evidence_codes": ["IMP"]},
            ],
        }
    ]

    go_claims, paper_claims = rank_graph_claims(
        candidates,
        ["111", "222"],
        go_df={"GO:COMMON": 900, "GO:RARE": 2},
        document_count=1000,
    )

    assert go_claims[0]["go_id"] == "GO:RARE"
    assert paper_claims[0]["pmid"] == "222"
