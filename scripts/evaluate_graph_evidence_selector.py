#!/usr/bin/env python3
"""Tune graph-aware SeqLit evidence selection on a development split.

The selector never sees query labels at inference time. GO document frequency,
candidate rank, and typed GO-to-PMID edges determine the ranked claims. Gold
labels are used only to select hyperparameters on the development partition and
to report the frozen configuration on the test partition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_agent_evidence import (
    compute_go_document_frequency,
    load_documents,
    rank_graph_claims,
    read_jsonl,
)


def main() -> None:
    args = parse_args()
    queries = {str(row["id"]): row for row in read_jsonl(Path(args.queries))}
    pack_rows = read_jsonl(Path(args.packs))
    packs = {str(row["pack"]["query_id"]): row for row in pack_rows}
    query_ids = sorted(set(queries) & set(packs))
    dev_ids, test_ids = make_split(query_ids, dev_fraction=args.dev_fraction, seed=args.seed)
    documents = load_documents(Path(args.documents))
    go_df = compute_go_document_frequency(documents)

    function_config = tune(
        dev_ids,
        queries,
        packs,
        go_df=go_df,
        document_count=len(documents),
        task="function",
    )
    literature_config = tune(
        dev_ids,
        queries,
        packs,
        go_df=go_df,
        document_count=len(documents),
        task="literature",
    )
    evaluations = {}
    details = {}
    for split, ids in (("dev", dev_ids), ("test", test_ids)):
        baseline_rows = evaluate_rank_first(ids, queries, packs)
        budget_matched_rows = evaluate_rank_first(
            ids,
            queries,
            packs,
            function_candidate_k=int(function_config["candidate_k"]),
            literature_candidate_k=int(literature_config["candidate_k"]),
            function_k=int(function_config["output_k"]),
            literature_k=int(literature_config["output_k"]),
        )
        graph_rows = evaluate_graph(
            ids,
            queries,
            packs,
            go_df=go_df,
            document_count=len(documents),
            function_config=function_config,
            literature_config=literature_config,
        )
        oracle_rows = evaluate_oracle(
            ids,
            queries,
            packs,
            function_k=int(function_config["output_k"]),
            literature_k=int(literature_config["output_k"]),
        )
        evaluations[split] = {
            "query_count": len(ids),
            "rank_first": summarize(baseline_rows),
            "rank_first_budget_matched": summarize(budget_matched_rows),
            "graph_idf": summarize(graph_rows),
            "retrieval_oracle": summarize(oracle_rows),
            "conditional_on_retrievable": {
                method: summarize_conditional(rows, oracle_rows)
                for method, rows in (
                    ("rank_first", baseline_rows),
                    ("rank_first_budget_matched", budget_matched_rows),
                    ("graph_idf", graph_rows),
                )
            },
            "graph_minus_rank_first_f1": {
                task: bootstrap_delta(
                    [row[task]["f1"] for row in graph_rows],
                    [row[task]["f1"] for row in baseline_rows],
                    seed=args.seed + (0 if task == "function" else 1),
                )
                for task in ("function", "literature")
            },
            "graph_minus_budget_matched_f1": {
                task: bootstrap_delta(
                    [row[task]["f1"] for row in graph_rows],
                    [row[task]["f1"] for row in budget_matched_rows],
                    seed=args.seed + (2 if task == "function" else 3),
                )
                for task in ("function", "literature")
            },
        }
        details[split] = {
            "rank_first": baseline_rows,
            "rank_first_budget_matched": budget_matched_rows,
            "graph_idf": graph_rows,
            "retrieval_oracle": oracle_rows,
        }

    result = {
        "dataset": "BioRAG-SeqLit-DAG graph evidence selector evaluation",
        "claim_scope": (
            "Hyperparameters are selected on a deterministic development split and frozen on the test split. "
            "The selector uses candidate rank, corpus GO frequency, and typed GO-to-PMID edges; it does not use "
            "query labels at inference time."
        ),
        "source_packs": args.packs,
        "seed": args.seed,
        "split": {"dev_query_ids": dev_ids, "test_query_ids": test_ids},
        "selected_config": {"function": function_config, "literature": literature_config},
        "evaluation": evaluations,
        "details": details,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(result), encoding="utf-8")
    export_packs(
        Path(args.export_packs),
        pack_rows,
        go_df=go_df,
        document_count=len(documents),
        function_config=function_config,
        literature_config=literature_config,
    )
    Path(args.test_ids).write_text("\n".join(test_ids) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "markdown": str(markdown),
                "export_packs": args.export_packs,
                "selected_config": result["selected_config"],
                "test": result["evaluation"]["test"],
            },
            indent=2,
        )
    )


def make_split(query_ids: list[str], *, dev_fraction: float, seed: int) -> tuple[list[str], list[str]]:
    ordered = sorted(
        query_ids,
        key=lambda query_id: hashlib.sha256(f"{seed}:{query_id}".encode()).hexdigest(),
    )
    dev_count = max(1, min(len(ordered) - 1, round(len(ordered) * dev_fraction)))
    return sorted(ordered[:dev_count]), sorted(ordered[dev_count:])


def tune(
    query_ids: list[str],
    queries: dict[str, dict[str, Any]],
    packs: dict[str, dict[str, Any]],
    *,
    go_df: dict[str, int],
    document_count: int,
    task: str,
) -> dict[str, float | int]:
    output_values = (1, 3, 5) if task == "function" else (1, 3, 5, 10)
    best: tuple[tuple[float, float, float, int, int], dict[str, float | int]] | None = None
    for candidate_k in (5, 10, 20, 50):
        for rank_offset in (0.0, 1.0, 5.0, 10.0, 20.0, 60.0):
            for idf_power in (0.0, 0.5, 1.0, 1.5, 2.0):
                for output_k in output_values:
                    config: dict[str, float | int] = {
                        "candidate_k": candidate_k,
                        "rank_offset": rank_offset,
                        "idf_power": idf_power,
                        "output_k": output_k,
                    }
                    rows = evaluate_graph_task(
                        query_ids,
                        queries,
                        packs,
                        go_df=go_df,
                        document_count=document_count,
                        task=task,
                        config=config,
                    )
                    summary = summarize_task(rows)
                    objective = (
                        summary["f1"],
                        summary["recall"],
                        summary["precision"],
                        -output_k,
                        -candidate_k,
                    )
                    if best is None or objective > best[0]:
                        best = (objective, {**config, "dev_f1": summary["f1"]})
    if best is None:
        raise RuntimeError(f"No configuration evaluated for task {task}")
    return best[1]


def evaluate_rank_first(
    query_ids: Iterable[str],
    queries: dict[str, dict[str, Any]],
    packs: dict[str, dict[str, Any]],
    *,
    function_candidate_k: int = 10,
    literature_candidate_k: int = 50,
    function_k: int = 5,
    literature_k: int = 10,
) -> list[dict[str, Any]]:
    rows = []
    for query_id in query_ids:
        pack = packs[query_id]["pack"]
        predicted_go: list[str] = []
        for candidate in pack["candidates"][:function_candidate_k]:
            for go_id in candidate["go_ids"]:
                if go_id not in predicted_go:
                    predicted_go.append(go_id)
                if len(predicted_go) >= function_k:
                    break
            if len(predicted_go) >= function_k:
                break
        supported_pmids = {
            str(pmid)
            for candidate in pack["candidates"][:literature_candidate_k]
            for pmid in candidate["paper_ids"]
        }
        predicted_pmids = [str(pmid) for pmid in pack["papers"] if str(pmid) in supported_pmids][:literature_k]
        rows.append(
            score_predictions(
                query_id,
                queries[query_id],
                predicted_go=predicted_go,
                predicted_pmids=predicted_pmids,
            )
        )
    return rows


def evaluate_graph(
    query_ids: Iterable[str],
    queries: dict[str, dict[str, Any]],
    packs: dict[str, dict[str, Any]],
    *,
    go_df: dict[str, int],
    document_count: int,
    function_config: dict[str, float | int],
    literature_config: dict[str, float | int],
) -> list[dict[str, Any]]:
    function = {
        row["query_id"]: row
        for row in evaluate_graph_task(
            query_ids,
            queries,
            packs,
            go_df=go_df,
            document_count=document_count,
            task="function",
            config=function_config,
        )
    }
    literature = {
        row["query_id"]: row
        for row in evaluate_graph_task(
            query_ids,
            queries,
            packs,
            go_df=go_df,
            document_count=document_count,
            task="literature",
            config=literature_config,
        )
    }
    return [
        {
            "query_id": query_id,
            "function": function[query_id]["metrics"],
            "literature": literature[query_id]["metrics"],
        }
        for query_id in function
    ]


def evaluate_graph_task(
    query_ids: Iterable[str],
    queries: dict[str, dict[str, Any]],
    packs: dict[str, dict[str, Any]],
    *,
    go_df: dict[str, int],
    document_count: int,
    task: str,
    config: dict[str, float | int],
) -> list[dict[str, Any]]:
    rows = []
    for query_id in query_ids:
        pack = packs[query_id]["pack"]
        go_claims, paper_claims = rank_graph_claims(
            pack["candidates"][: int(config["candidate_k"])],
            pack["papers"],
            go_df=go_df,
            document_count=document_count,
            rank_offset=float(config["rank_offset"]),
            idf_power=float(config["idf_power"]),
        )
        if task == "function":
            predicted = [str(row["go_id"]) for row in go_claims[: int(config["output_k"])]]
            expected = {str(item) for item in queries[query_id]["expected_go_ids"]}
        else:
            predicted = [str(row["pmid"]) for row in paper_claims[: int(config["output_k"])]]
            expected = {str(item) for item in queries[query_id]["expected_pmids"]}
        rows.append({"query_id": query_id, "metrics": set_metrics(set(predicted), expected)})
    return rows


def evaluate_oracle(
    query_ids: Iterable[str],
    queries: dict[str, dict[str, Any]],
    packs: dict[str, dict[str, Any]],
    *,
    function_k: int,
    literature_k: int,
) -> list[dict[str, Any]]:
    rows = []
    for query_id in query_ids:
        pack = packs[query_id]["pack"]
        expected_go = {str(item) for item in queries[query_id]["expected_go_ids"]}
        expected_pmids = {str(item) for item in queries[query_id]["expected_pmids"]}
        available_go = {str(go) for item in pack["candidates"] for go in item["go_ids"]}
        available_pmids = {
            str(edge["pmid"])
            for item in pack["candidates"]
            for edge in item.get("go_pmid_edges", [])
            if str(edge["pmid"]) in {str(pmid) for pmid in pack["papers"]}
        }
        oracle_go = set(sorted(expected_go & available_go)[:function_k])
        oracle_pmids = set(sorted(expected_pmids & available_pmids)[:literature_k])
        rows.append(
            {
                "query_id": query_id,
                "function": set_metrics(oracle_go, expected_go),
                "literature": set_metrics(oracle_pmids, expected_pmids),
            }
        )
    return rows


def score_predictions(
    query_id: str,
    query: dict[str, Any],
    *,
    predicted_go: list[str],
    predicted_pmids: list[str],
) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "function": set_metrics(set(predicted_go), {str(item) for item in query["expected_go_ids"]}),
        "literature": set_metrics(set(predicted_pmids), {str(item) for item in query["expected_pmids"]}),
    }


def set_metrics(predicted: set[str], expected: set[str]) -> dict[str, float]:
    precision = len(predicted & expected) / len(predicted) if predicted else 0.0
    recall = len(predicted & expected) / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "hit": float(bool(predicted & expected))}


def summarize(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    return {
        task: {
            metric: sum(row[task][metric] for row in rows) / len(rows) if rows else 0.0
            for metric in ("precision", "recall", "f1", "hit")
        }
        for task in ("function", "literature")
    }


def summarize_task(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {
        metric: sum(row["metrics"][metric] for row in rows) / len(rows) if rows else 0.0
        for metric in ("precision", "recall", "f1", "hit")
    }


def summarize_conditional(
    rows: list[dict[str, Any]],
    oracle_rows: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    oracle_by_id = {row["query_id"]: row for row in oracle_rows}
    result = {}
    for task in ("function", "literature"):
        selected = [
            row
            for row in rows
            if oracle_by_id[row["query_id"]][task]["hit"] > 0.0
        ]
        result[task] = {
            "query_count": len(selected),
            **{
                metric: sum(row[task][metric] for row in selected) / len(selected) if selected else 0.0
                for metric in ("precision", "recall", "f1", "hit")
            },
        }
    return result


def bootstrap_delta(graph: list[float], baseline: list[float], *, seed: int, samples: int = 2000) -> dict[str, float]:
    if not graph:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    deltas = [left - right for left, right in zip(graph, baseline)]
    rng = random.Random(seed)
    boot = sorted(
        sum(deltas[rng.randrange(len(deltas))] for _ in deltas) / len(deltas)
        for _ in range(samples)
    )
    return {
        "mean": sum(deltas) / len(deltas),
        "ci_low": boot[int(0.025 * samples)],
        "ci_high": boot[int(0.975 * samples) - 1],
    }


def export_packs(
    path: Path,
    pack_rows: list[dict[str, Any]],
    *,
    go_df: dict[str, int],
    document_count: int,
    function_config: dict[str, float | int],
    literature_config: dict[str, float | int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wt", encoding="utf-8") as handle:
        for row in pack_rows:
            pack = dict(row["pack"])
            go_claims, _ = rank_graph_claims(
                pack["candidates"][: int(function_config["candidate_k"])],
                pack["papers"],
                go_df=go_df,
                document_count=document_count,
                rank_offset=float(function_config["rank_offset"]),
                idf_power=float(function_config["idf_power"]),
            )
            _, paper_claims = rank_graph_claims(
                pack["candidates"][: int(literature_config["candidate_k"])],
                pack["papers"],
                go_df=go_df,
                document_count=document_count,
                rank_offset=float(literature_config["rank_offset"]),
                idf_power=float(literature_config["idf_power"]),
            )
            pack["go_claims"] = go_claims
            pack["paper_claims"] = paper_claims
            pack["selector_config"] = {
                "function": function_config,
                "literature": literature_config,
            }
            handle.write(json.dumps({**row, "pack": pack}, ensure_ascii=False) + "\n")


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Graph Evidence Selector Evaluation",
        "",
        result["claim_scope"],
        "",
        f"Development queries: `{len(result['split']['dev_query_ids'])}`; test queries: `{len(result['split']['test_query_ids'])}`.",
        "",
        "| Split | Method | Function P/R/F1/Hit | Literature P/R/F1/Hit |",
        "|---|---|---:|---:|",
    ]
    for split in ("dev", "test"):
        for method in ("rank_first", "rank_first_budget_matched", "graph_idf", "retrieval_oracle"):
            values = result["evaluation"][split][method]
            function = values["function"]
            literature = values["literature"]
            lines.append(
                f"| {split} | {method} | {function['precision']:.3f}/{function['recall']:.3f}/"
                f"{function['f1']:.3f}/{function['hit']:.3f} | {literature['precision']:.3f}/"
                f"{literature['recall']:.3f}/{literature['f1']:.3f}/{literature['hit']:.3f} |"
            )
    lines.extend(
        [
            "",
            "The retrieval oracle is budget-matched and only measures whether a correct structured identifier is present in the evidence pack. It is not an executable method.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune and test graph-aware SeqLit evidence selection")
    root = "data/seq_lit_dag_function_heldout_2k"
    parser.add_argument("--packs", default="reports/results/agent_qa_prott5_blast_graph_idf_packs.jsonl")
    parser.add_argument("--queries", default=f"{root}/queries.jsonl")
    parser.add_argument("--documents", default=f"{root}/index_documents.jsonl")
    parser.add_argument("--dev-fraction", type=float, default=1.0 / 3.0)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--output", default="reports/results/agent_graph_selector_eval.json")
    parser.add_argument("--markdown", default="reports/agent_graph_selector_eval.md")
    parser.add_argument("--export-packs", default="reports/results/agent_graph_selector_packs.jsonl")
    parser.add_argument("--test-ids", default="reports/results/agent_graph_selector_test_ids.txt")
    return parser.parse_args()


if __name__ == "__main__":
    main()
