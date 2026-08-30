from scripts.eval_seq_lit_embeddings import embedding_dataset_name, first_rank, make_windows, rank_pmids, summarize


def test_rank_pmids_preserves_candidate_order_and_deduplicates():
    result = rank_pmids(["P2", "P1"], {"P1": ["1", "2"], "P2": ["2", "3"]}, 3)
    assert result == ["2", "3", "1"]


def test_embedding_summary_and_first_rank():
    rows = [
        {"protein_hit_at_1": True, "protein_hit_at_5": True, "protein_hit_at_10": True, "protein_mrr": 1.0, "paper_hit": True, "paper_recall": 0.5, "path_complete": True},
        {"protein_hit_at_1": False, "protein_hit_at_5": False, "protein_hit_at_10": False, "protein_mrr": 0.0, "paper_hit": False, "paper_recall": 0.0, "path_complete": False},
    ]
    assert first_rank(["P2", "P1"], {"P1"}) == 2
    assert summarize(rows)["protein_hit_at_1"] == 0.5
    assert summarize(rows)["paper_recall"] == 0.25


def test_make_windows_includes_tail_and_parent_mapping():
    accessions, windows = make_windows({"P1": "A" * 200}, size=128, stride=64)
    assert accessions == ["P1", "P1", "P1"]
    assert [len(window) for window in windows] == [128, 128, 128]


def test_heldout_embedding_dataset_is_labeled_separately():
    assert "held-out" in embedding_dataset_name([{"relevant_index_accessions": ["P1"]}])
