from dnarag.retrieval.hybrid import _sequence_overlap_score, _vector_raw_top_k


def test_sequence_window_raw_top_k_overfetches_before_parent_dedup():
    assert _vector_raw_top_k("protein_sequence_window", 10) == 1000
    assert _vector_raw_top_k("dna_sequence_window", 100) == 5000


def test_non_window_raw_top_k_uses_requested_limit():
    assert _vector_raw_top_k("text", 10) == 10


def test_sequence_overlap_scores_suffix_and_internal_matches():
    assert _sequence_overlap_score("CDEFG", "ABCDEFG") == 1.0
    assert _sequence_overlap_score("CDEFG", "XXCDEFGYY") == 1.0
    assert _sequence_overlap_score("AAAAA", "CCCCC") == 0.0
