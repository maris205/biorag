from scripts.build_seq_lit_heldout import make_ground_truth
from scripts.eval_seq_lit_heldout_cpu import claim_scope, dataset_name, evaluate_one
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


def test_cluster_heldout_queries_receive_strict_claim_scope():
    uniref = [{"task": "uniref50_cluster_heldout_sequence_to_function_to_literature"}]
    identity = [{"task": "identity_cluster_heldout_sequence_to_function_to_literature"}]
    assert "UniRef50" in dataset_name(uniref)
    assert "same observed UniRef50 cluster" in claim_scope(uniref)
    assert "stress test" in dataset_name(identity)
    assert "cluster-stratified stress test" in claim_scope(identity)
