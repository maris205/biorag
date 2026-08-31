from dnarag.agent_review import (
    audit_freeform_answer,
    build_freeform_prompt,
    evidence_pmids,
    identifier_scores,
    query_stratum,
    select_review_queries,
)


def make_query(query_id="q1", go_count=1, pmid_count=2):
    return {
        "id": query_id,
        "query": "MPEPTIDE",
        "expected_go_ids": [f"GO:{index:07d}" for index in range(1, go_count + 1)],
        "expected_pmids": [str(100 + index) for index in range(pmid_count)],
    }


def make_pack():
    return {
        "query_id": "q1",
        "candidates": [
            {
                "rank": 1,
                "accession": "P12345",
                "symbol": "GENE1",
                "go_ids": ["GO:0000001"],
                "paper_ids": ["100"],
                "go_pmid_edges": [
                    {"go_id": "GO:0000001", "pmid": "100", "evidence_codes": ["IDA"]}
                ],
            }
        ],
        "papers": ["100"],
        "go_claims": [
            {
                "go_id": "GO:0000001",
                "evidence_ids": ["E1"],
                "accessions": ["P12345"],
            }
        ],
        "paper_claims": [
            {
                "pmid": "100",
                "go_ids": ["GO:0000001"],
                "accessions": ["P12345"],
            }
        ],
    }


def test_review_strata_and_selection_are_balanced_and_deterministic():
    queries = {}
    for index in range(6):
        queries[f"s{index}"] = make_query(f"s{index}", go_count=1, pmid_count=2)
        queries[f"d{index}"] = make_query(f"d{index}", go_count=1, pmid_count=5)
        queries[f"m{index}"] = make_query(f"m{index}", go_count=2, pmid_count=2)

    first = select_review_queries(queries, queries, per_stratum=3, seed=7)
    second = select_review_queries(queries, queries, per_stratum=3, seed=7)

    assert first == second
    assert len(first) == 9
    assert {row["stratum"] for row in first} == {
        "single_go_sparse_literature",
        "single_go_dense_literature",
        "multi_go",
    }
    assert query_stratum(queries["s0"]) == "single_go_sparse_literature"


def test_freeform_context_preserves_typed_go_paper_path():
    context = build_freeform_prompt(
        make_query(),
        make_pack(),
        evidence_mode="graph_idf",
        go_names={"GO:0000001": "test activity"},
        pubmed_metadata={"100": {"title": "Test paper", "year": "2024", "abstract": "Evidence."}},
    )

    assert "[C1] candidate accession=P12345" in context["prompt"]
    assert "[G1] candidates=C1 -> GO:0000001 (test activity)" in context["prompt"]
    assert "[P1] PMID:100; title=Test paper" in context["prompt"]
    assert context["available_go_ids"] == ["GO:0000001"]
    assert context["available_function_go_ids"] == ["GO:0000001"]
    assert context["available_pmids"] == ["100"]
    assert evidence_pmids(make_pack(), evidence_mode="graph_idf") == ["100"]


def test_freeform_audit_separates_valid_citations_and_out_of_pack_ids():
    context = build_freeform_prompt(make_query(), make_pack(), evidence_mode="raw")
    answer = (
        "FUNCTION HYPOTHESIS: GO:0000001 [G1]\n"
        "EVIDENCE: candidate [C1] and invalid [G9]\n"
        "LITERATURE: PMID:999 [P1]\n"
        "UNCERTAINTY: This is an indirect candidate hypothesis."
    )

    audit = audit_freeform_answer(answer, context)

    assert audit["invalid_citations"] == ["G9"]
    assert audit["out_of_pack_pmids"] == ["999"]
    assert audit["format_compliance"] is True
    assert audit["calibration_language"] is True
    assert audit["overclaim_flag"] is False
    assert audit["citation_syntax_compliance"] is True


def test_freeform_audit_checks_identifier_to_citation_entailment():
    context = build_freeform_prompt(make_query(), make_pack(), evidence_mode="raw")
    answer = (
        "FUNCTION HYPOTHESIS: GO:0000001 [G1]\n"
        "EVIDENCE: candidate [C1]\n"
        "LITERATURE: PMID:999 [P1]\n"
        "UNCERTAINTY: indirect hypothesis"
    )

    audit = audit_freeform_answer(answer, context)

    assert audit["go_citation_entailment"] == 1.0
    assert audit["pmid_citation_entailment"] == 0.0


def test_freeform_audit_detects_malformed_grouped_citations_and_abstention():
    context = build_freeform_prompt(make_query(), make_pack(), evidence_mode="raw")
    answer = (
        "FUNCTION HYPOTHESIS: No functional hypotheses can be proposed.\n"
        "EVIDENCE: candidates [C1-C5]\n"
        "LITERATURE: none\n"
        "UNCERTAINTY: no retrieved evidence"
    )

    audit = audit_freeform_answer(answer, context)

    assert audit["citation_syntax_compliance"] is False
    assert audit["abstention"] is True


def test_identifier_scores_are_diagnostic_not_evidence_scores():
    scores = identifier_scores("GO:0000001 and PMID:100", make_query())

    assert scores["go_f1"] == 1.0
    assert scores["pmid_precision"] == 1.0
    assert scores["pmid_recall"] == 0.5
