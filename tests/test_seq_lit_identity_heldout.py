from pathlib import Path

from scripts.build_seq_lit_identity_heldout import cluster_from_blast, middle_fragment, select_query_clusters


def test_cluster_from_blast_uses_identity_and_shorter_coverage(tmp_path: Path):
    pairs = tmp_path / "pairs.tsv"
    pairs.write_text(
        "sp|P1|x\tsp|P2|x\t60\t80\t100\t90\t1e-20\t100\n"
        "sp|P2|x\tsp|P3|x\t70\t20\t100\t100\t1e-10\t50\n"
        "sp|P3|x\tsp|P4|x\t49\t90\t100\t100\t1e-10\t80\n",
        encoding="utf-8",
    )

    clusters, accession_cluster, qualifying, stats = cluster_from_blast(
        pairs,
        ["P1", "P2", "P3", "P4"],
        min_identity=50.0,
        min_shorter_coverage=0.8,
    )

    assert accession_cluster["P1"] == accession_cluster["P2"]
    assert accession_cluster["P2"] != accession_cluster["P3"]
    assert len(clusters) == 3
    assert qualifying == {("P1", "P2")}
    assert stats["qualifying_pairs"] == 1


def test_query_selection_excludes_complete_cluster_and_keeps_reachable_truth():
    clusters = {
        "c1": ("Q1", "Q1_NEAR"),
        "c2": ("P2",),
        "c3": ("P3",),
    }
    evidence = {
        "Q1": {"GO:1": {"101"}},
        "Q1_NEAR": {"GO:1": {"102"}},
        "P2": {"GO:1": {"201"}},
        "P3": {"GO:2": {"301"}},
    }
    proteins_by_go = {"GO:1": {"Q1", "Q1_NEAR", "P2"}, "GO:2": {"P3"}}

    queries, excluded = select_query_clusters(
        clusters,
        evidence,
        proteins_by_go,
        target=1,
        min_go_df=2,
        max_go_df=5,
        seed=0,
    )

    assert queries in (["Q1"], ["Q1_NEAR"])
    assert excluded == {"Q1", "Q1_NEAR"}
    assert "P2" not in excluded


def test_middle_fragment_matches_query_window_contract():
    assert middle_fragment("A" * 10, length=6) == "A" * 6
    assert middle_fragment("ABCDEFGHIJ", length=4) == "DEFG"
