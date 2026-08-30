import numpy as np

from scripts.analyze_seq_lit_heldout_results import interval, paired_bootstrap


def test_interval_and_paired_bootstrap_are_query_paired():
    assert interval(0.5, np.asarray([0.0, 0.5, 1.0]))["mean"] == 0.5
    left = [{"query_id": "q1", "candidate_hit_at_10": 1, "candidate_mrr": 1, "paper_hit": 1, "paper_recall": 1, "path_complete": 1}]
    right = [{"query_id": "q1", "candidate_hit_at_10": 0, "candidate_mrr": 0, "paper_hit": 0, "paper_recall": 0, "path_complete": 0}]
    result = paired_bootstrap(left, right, samples=100, seed=1)
    assert result["paper_hit"]["mean"] == 1.0
    assert result["paper_hit"]["probability_gt_zero"] == 1.0
