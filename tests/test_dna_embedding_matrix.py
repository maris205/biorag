from scripts.eval_dna_embedding_matrix import make_windows, reverse_complement, software_versions, summarize
from scripts.summarize_dna_embedding_results import query_type_summary


def test_reverse_complement_is_involution():
    assert reverse_complement("ACGTN") == "NACGT"
    assert reverse_complement(reverse_complement("ACGTN")) == "ACGTN"


def test_window_tail_and_parent_mapping():
    class Record:
        def __init__(self):
            self.sequence = "A" * 200

    accessions, windows = make_windows({"P1": Record()}, size=128, stride=64, min_size=24)
    assert accessions == ["P1", "P1", "P1"]
    assert [len(window) for window in windows] == [128, 128, 128]


def test_window_limit_can_define_a_fast_probe():
    class Record:
        def __init__(self, sequence):
            self.sequence = sequence

    accessions, windows = make_windows({"P1": Record("A" * 200), "P2": Record("C" * 200)}, size=128, stride=64, min_size=24)
    assert len(accessions[:2]) == 2
    assert len(windows[:2]) == 2


def test_summary_uses_boolean_metrics():
    rows = [{"exact_hit_at_1": True, "exact_hit_at_5": True, "exact_hit_at_10": True, "exact_mrr": 1.0,
             "bio_hit_at_1": True, "bio_hit_at_5": True, "bio_hit_at_10": True, "bio_mrr": 1.0},
            {"exact_hit_at_1": False, "exact_hit_at_5": False, "exact_hit_at_10": False, "exact_mrr": 0.0,
             "bio_hit_at_1": False, "bio_hit_at_5": False, "bio_hit_at_10": False, "bio_mrr": 0.0}]
    assert summarize(rows)["bio_hit_at_10"] == 0.5


def test_software_versions_is_small_and_serializable():
    versions = software_versions()
    assert "python" in versions
    assert all(isinstance(value, str) for value in versions.values())


def test_query_type_summary_keeps_heterogeneous_tasks_separate():
    summary = query_type_summary([
        {"query_type": "prefix", "bio_hit_at_10": True, "bio_mrr": 1.0},
        {"query_type": "prefix", "bio_hit_at_10": False, "bio_mrr": 0.0},
        {"query_type": "mutated", "bio_hit_at_10": True, "bio_mrr": 0.5},
    ])
    assert summary["prefix"]["bio_hit_at_10"] == 0.5
    assert summary["mutated"]["bio_mrr"] == 0.5
