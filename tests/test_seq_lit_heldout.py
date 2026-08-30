from scripts.build_seq_lit_heldout import make_ground_truth
from scripts.eval_seq_lit_heldout_cpu import dataset_name, evaluate_one
from dnarag.seq_lit_dag.evaluate import ProteinCandidate


def test_ground_truth_removes_heldout_candidates_and_high_df_papers():
    by_protein = {"Q": {"1", "2"}, "A": {"1"}, "B": {"2"}, "C": {"2"}}
    by_paper = {"1": {"Q", "A"}, "2": {"Q", "B", "C"}}
    truth = make_ground_truth(
        ["Q", "A"], by_protein, by_paper, heldout_set={"Q", "A"}, min_paper_df=2, max_paper_df=2
    )
    assert truth == {}


def test_heldout_eval_uses_curated_labels_not_model_output():
    query = {"id": "q", "relevant_index_accessions": ["A"], "expected_pmids": ["1"]}
    row = evaluate_one(
        query,
        method="test",
        candidates=[ProteinCandidate("A", 1.0)],
        papers_by_accession={"A": ["1"]},
        paper_k=10,
        latency_ms=1.0,
    )
    assert row["candidate_hit_at_1"] is True
    assert row["paper_recall"] == 1.0
    assert row["path_complete"] is True


def test_function_queries_receive_function_dataset_label():
    assert "function" in dataset_name([{"expected_go_ids": ["GO:1"]}])
