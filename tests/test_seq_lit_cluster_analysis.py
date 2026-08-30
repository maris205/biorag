import pytest

from scripts.analyze_seq_lit_cluster_heldout import normalize_rows, validate_query_sets


def test_normalize_rows_accepts_cpu_and_embedding_metric_names():
    rows = normalize_rows(
        [
            {
                "query_id": "q2",
                "protein_hit_at_10": True,
                "protein_mrr": 0.5,
                "paper_hit": False,
                "paper_recall": 0.0,
                "path_complete": False,
            },
            {
                "query_id": "q1",
                "candidate_hit_at_10": False,
                "candidate_mrr": 0.25,
                "paper_hit": True,
                "paper_recall": 0.5,
                "path_complete": True,
            },
        ]
    )
    assert [row["query_id"] for row in rows] == ["q1", "q2"]
    assert rows[0]["mrr"] == 0.25
    assert rows[1]["hit_at_10"] == 1.0


def test_validate_query_sets_rejects_mismatched_routes():
    with pytest.raises(ValueError, match="Query set mismatch"):
        validate_query_sets({"a": [{"query_id": "q1"}], "b": [{"query_id": "q2"}]})
