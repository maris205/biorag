import csv
from pathlib import Path

from scripts.summarize_agent_expert_review import (
    load_ratings,
    load_route_key,
    quadratic_weighted_kappa,
    summarize_ratings,
)


def make_key():
    routes = [
        "no_retrieval",
        "r2r_text_only",
        "sequence_vector",
        "combined_blast_vector",
        "combined_blast_vector_dag",
    ]
    return {
        "cases": [
            {
                "case_id": case_id,
                "variant_key": {
                    chr(ord("A") + index): {"route": route}
                    for index, route in enumerate(routes)
                },
            }
            for case_id in ("BRX-001", "BRX-002")
        ]
    }


def write_ratings(path: Path, reviewer: str, score_offset: int = 0):
    fields = [
        "reviewer_id",
        "case_id",
        "variant_id",
        "functional_correctness_0_4",
        "citation_support_0_4",
        "literature_relevance_0_4",
        "calibration_0_4",
        "actionability_0_4",
        "overclaim_0_1",
        "within_case_rank_1_5",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case_id in ("BRX-001", "BRX-002"):
            for index, variant in enumerate("ABCDE"):
                score = min(4, index + score_offset)
                writer.writerow(
                    {
                        "reviewer_id": reviewer,
                        "case_id": case_id,
                        "variant_id": variant,
                        "functional_correctness_0_4": score,
                        "citation_support_0_4": score,
                        "literature_relevance_0_4": score,
                        "calibration_0_4": score,
                        "actionability_0_4": score,
                        "overclaim_0_1": 0,
                        "within_case_rank_1_5": 5 - index,
                        "notes": "",
                    }
                )


def test_completed_forms_decode_routes_and_pair_cases(tmp_path):
    key, expected = load_route_key(make_key())
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    write_ratings(first, "R1")
    write_ratings(second, "R2")

    ratings = load_ratings([first, second], expected_items=expected)
    result = summarize_ratings(
        ratings,
        route_key=key,
        expected_items=expected,
        bootstrap_replicates=100,
    )

    assert result["reviewer_count"] == 2
    assert result["case_count"] == 2
    assert [row["route"] for row in result["routes"]] == [
        "no_retrieval",
        "r2r_text_only",
        "sequence_vector",
        "combined_blast_vector",
        "combined_blast_vector_dag",
    ]
    assert result["inter_rater_agreement"]["functional_correctness_0_4"] == 1.0
    dag = next(row for row in result["routes"] if row["route"] == "combined_blast_vector_dag")
    assert dag["primary_utility"] == 4.0


def test_quadratic_kappa_handles_exact_and_reversed_scores():
    assert quadratic_weighted_kappa([0, 1, 2, 3, 4], [0, 1, 2, 3, 4], minimum=0, maximum=4) == 1.0
    assert quadratic_weighted_kappa([0, 1, 2, 3, 4], [4, 3, 2, 1, 0], minimum=0, maximum=4) < 0.0
