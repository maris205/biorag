from dnarag.evaluation import (
    _summarize_by_category,
    first_biological_match_rank,
    first_match_rank,
    load_benchmark,
    matches_biological_expected,
    matches_expected,
)


def test_matches_expected_by_entity_source_symbol_and_title():
    item = {
        "entity_id": "hgnc_gene:HGNC:1100",
        "source_id": "HGNC:1100",
        "symbol": "BRCA1",
        "title": "BRCA1 DNA repair associated",
        "metadata": {},
    }

    assert matches_expected(item, {"entity_ids": ["hgnc_gene:HGNC:1100"]})
    assert matches_expected(item, {"source_ids": ["HGNC:1100"]})
    assert matches_expected(item, {"symbols": ["brca1"]})
    assert matches_expected(item, {"title_contains": ["DNA repair"]})


def test_first_match_rank():
    evidence = [
        {"entity_id": "gene:A", "metadata": {}},
        {"entity_id": "gene:B", "metadata": {}},
    ]

    assert first_match_rank(evidence, {"entity_ids": ["gene:B"]}) == 2
    assert first_match_rank(evidence, {"entity_ids": ["gene:C"]}) is None


def test_biological_match_rank_by_gene_symbol_and_gene_id():
    evidence = [
        {
            "entity_id": "dna_sequence:ENST_A",
            "title": "cdna gene:ENSG1 gene_symbol:IGHV1-1 transcript_biotype:IG_V_gene",
            "metadata": {},
        },
        {
            "entity_id": "dna_sequence:ENST_B",
            "title": "cdna gene:ENSG2 gene_symbol:BRCA1",
            "metadata": {},
        },
    ]

    assert matches_biological_expected(evidence[0], {"biological": {"gene_symbols": ["ighv1-1"]}})
    assert first_biological_match_rank(evidence, {"biological": {"gene_ids": ["ENSG2"]}}) == 2


def test_load_benchmark(tmp_path):
    path = tmp_path / "basic.jsonl"
    path.write_text(
        '{"id":"x","query":"BRCA1","category":"gene","query_type":"exact_symbol","expected":{"symbols":["BRCA1"]}}\n',
        encoding="utf-8",
    )

    tasks = load_benchmark(path)

    assert tasks[0].task_id == "x"
    assert tasks[0].query_type == "exact_symbol"
    assert tasks[0].expected["symbols"] == ["BRCA1"]


def test_summarize_by_category_splits_conditions_and_modalities():
    rows = [
        {"condition": "vector", "category": "protein_sequence", "hit_at_1": True, "hit_at_5": True, "hit_at_10": True, "mrr": 1.0, "latency_ms": 10, "local_coverage": 1.0},
        {"condition": "vector", "category": "dna_sequence", "hit_at_1": False, "hit_at_5": False, "hit_at_10": True, "mrr": 0.1, "latency_ms": 20, "local_coverage": 1.0},
        {"condition": "blast", "category": "dna_sequence", "hit_at_1": True, "hit_at_5": True, "hit_at_10": True, "mrr": 1.0, "latency_ms": 5, "local_coverage": 1.0},
    ]

    summary = _summarize_by_category(rows)

    assert summary["vector"]["protein_sequence"]["hit_at_10"] == 1.0
    assert summary["vector"]["dna_sequence"]["mrr"] == 0.1
    assert summary["blast"]["dna_sequence"]["avg_latency_ms"] == 5.0
