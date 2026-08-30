from collections import Counter

import numpy as np

from dnarag.token_semantics import (
    AnnotatedSequence,
    SparseTokenIndex,
    benjamini_hochberg,
    extract_sequence,
    fixed_kmers,
    length_stratified_permutation,
    stable_token_id,
)
from scripts.analyze_sequence_token_semantics import enrichment_analysis
from scripts.eval_seq_token_graph_retrieval import append_ranking


def test_extract_sequence_and_fixed_kmers():
    text = "[TYPE=protein_sequence]\nAccession: P1\nSequence:\nMABC DEF\n"

    assert extract_sequence(text) == "MABCDEF"
    assert fixed_kmers("ABCDE", 3) == ["ABC", "BCD", "CDE"]


def test_bh_adjustment_is_monotonic_in_ranked_order():
    values = np.array([0.01, 0.04, 0.03, 0.2])
    adjusted = benjamini_hochberg(values)

    assert np.allclose(adjusted, [0.04, 0.0533333333, 0.0533333333, 0.2])


def test_length_stratified_permutation_stays_inside_strata():
    lengths = [1, 2, 3, 100, 101, 102]
    permutation = length_stratified_permutation(lengths, np.random.default_rng(7), bins=2)

    assert set(permutation[:3]) == {0, 1, 2}
    assert set(permutation[3:]) == {3, 4, 5}


def test_stable_token_id_is_namespace_sensitive():
    assert stable_token_id("protein", "ABC") == stable_token_id("protein", "ABC")
    assert stable_token_id("protein", "ABC") != stable_token_id("dna", "ABC")


def test_sparse_token_index_prefers_rare_matching_document():
    index = SparseTokenIndex.build(
        ["P1", "P2", "P3"],
        [
            Counter({"shared": 1, "rare": 2}),
            Counter({"shared": 1}),
            Counter({"other": 1}),
        ],
    )

    assert index.rank(["rare", "shared"], limit=2)[0][0] == "P1"


def test_append_ranking_preserves_primary_prefix_and_deduplicates():
    ranking = append_ranking(
        ["P1", "P2", "P3", "P4"],
        ["P2", "P5", "P6"],
        primary_prefix=2,
        limit=5,
    )

    assert ranking == ["P1", "P2", "P5", "P6", "P3"]


def test_enrichment_analysis_recovers_synthetic_association():
    records = [
        AnnotatedSequence(f"P{index}", "A" * (20 + index), ("GO:1",) if index < 10 else ("GO:2",))
        for index in range(20)
    ]
    token_lists = [["signal", "shared"] if index < 10 else ["other", "shared"] for index in range(20)]

    summary, rows = enrichment_analysis(
        records,
        token_lists,
        min_token_df=2,
        min_label_df=2,
        max_df_fraction=0.9,
        min_overlap=2,
        fdr=0.05,
        permutations=0,
        seed=42,
    )

    assert summary["significant_associations"] >= 2
    assert any(row["token"] == "signal" and row["go_id"] == "GO:1" for row in rows)
