import json

from scripts.fuse_seq_lit_rankings import load_by_query, reciprocal_rank_fusion


def test_rrf_rewards_candidates_present_in_both_rankings():
    result = reciprocal_rank_fusion([["A", "B", "C"], ["C", "B", "D"]], limit=4, rrf_k=60)
    assert result[:2] == ["C", "B"]
    assert set(result) == {"A", "B", "C", "D"}


def test_load_by_query_filters_shared_method_file(tmp_path):
    path = tmp_path / "result.json"
    path.write_text(
        json.dumps(
            {
                "details": [
                    {"query_id": "q1", "method": "random", "top_accessions": ["R"]},
                    {"query_id": "q1", "method": "blast", "top_accessions": ["B"]},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_by_query(path, method="blast")["q1"]["top_accessions"] == ["B"]
