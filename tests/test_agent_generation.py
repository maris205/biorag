from scripts.generate_agent_qa import build_prompt, extract_pmids
from scripts.score_generated_agent_qa import score_output


def make_pack():
    return {
        "query_id": "q1",
        "candidates": [
            {
                "rank": 1,
                "accession": "P1",
                "symbol": "GENE1",
                "go_ids": ["GO:0000001"],
                "paper_ids": ["12345678"],
                "go_pmid_edges": [
                    {
                        "go_id": "GO:0000001",
                        "pmid": "12345678",
                        "evidence_codes": ["IDA"],
                    }
                ],
            }
        ],
        "papers": ["12345678"],
        "go_claims": [
            {
                "go_id": "GO:0000001",
                "score": 0.5,
                "document_frequency": 2,
                "evidence_ids": ["E1"],
                "accessions": ["P1"],
            }
        ],
        "paper_claims": [
            {
                "pmid": "12345678",
                "score": 0.4,
                "paper_rank": 1,
                "go_ids": ["GO:0000001"],
                "evidence_ids": ["E1"],
                "accessions": ["P1"],
            }
        ],
    }


def test_graph_prompt_exposes_ranked_typed_claims():
    prompt = build_prompt({"id": "q1"}, make_pack(), qa_type="literature", evidence_mode="graph_idf")

    assert "[L1] PMID=12345678 source=[P1]" in prompt
    assert "GO=GO:0000001" in prompt
    assert "graph_score=0.40000" in prompt


def test_pmid_extraction_requires_explicit_pmid_prefix():
    assert extract_pmids("GO:0005515; accession 12345678") == set()
    assert extract_pmids("PMID:12345678 [P1]") == {"12345678"}


def test_score_output_separates_gold_coverage_and_grounding():
    pack = make_pack()
    prompt = build_prompt({"id": "q1"}, pack, qa_type="function", evidence_mode="graph_idf")
    output = {
        "query_id": "q1",
        "qa_type": "function",
        "prompt": prompt,
        "answer": "ANSWER: GO:0000001 [G1]\nCITATIONS: [G1]",
    }
    query = {"id": "q1", "expected_go_ids": ["GO:0000001"], "expected_pmids": ["12345678"]}

    score = score_output(output, query, pack)

    assert score["answer_f1"] == 1.0
    assert score["prompt_gold_recall"] == 1.0
    assert score["retrievable_answer_f1"] == 1.0
    assert score["evidence_selection_f1"] == 1.0
    assert score["citation_validity"] == 1.0
    assert score["citation_entailment"] == 1.0
    assert score["pack_hallucination_rate"] == 0.0
    assert score["format_compliance"] is True
    assert score["citation_syntax_compliance"] is True


def test_mechanism_abstention_is_strictly_formatted():
    output = {
        "query_id": "q1",
        "qa_type": "mechanism",
        "prompt": "Evidence:\n[E1] GO=GO:0000001",
        "answer": "ANSWER: INSUFFICIENT_EVIDENCE\nCITATIONS: NONE",
    }
    query = {"id": "q1", "expected_go_ids": ["GO:0000001"], "expected_pmids": ["12345678"]}

    score = score_output(output, query, make_pack())

    assert score["abstention_correct"] is True
    assert score["citation_entailment"] == 1.0
    assert score["format_compliance"] is True
