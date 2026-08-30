from scripts.build_seq_lit_function_heldout import make_function_ground_truth


def test_function_ground_truth_uses_index_side_papers_and_excludes_heldout():
    evidence = {
        "Q": {"GO:1": {"100"}},
        "A": {"GO:1": {"200"}},
        "B": {"GO:1": {"300"}},
    }
    proteins_by_go = {"GO:1": {"Q", "A", "B"}}
    truth = make_function_ground_truth(
        ["Q", "A"],
        evidence,
        proteins_by_go,
        heldout_set={"Q", "A"},
        min_go_df=2,
        max_go_df=5,
    )
    assert truth["Q"]["candidate_accessions"] == ["B"]
    assert truth["Q"]["pmids"] == ["300"]
    assert "100" not in truth["Q"]["pmids"]
