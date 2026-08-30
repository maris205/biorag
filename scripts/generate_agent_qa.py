#!/usr/bin/env python3
"""Generate citation-constrained answers from saved SeqLit evidence packs.

This script is intentionally separate from retrieval evaluation. It consumes
the same packs used by the deterministic QA baseline, so a generator model can
be swapped without changing the benchmark split or evidence contract.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    args = parse_args()
    queries = {str(row["id"]): row for row in read_jsonl(Path(args.queries))}
    pack_rows = read_jsonl(Path(args.packs))
    selected_query_ids = load_query_ids(args.query_ids_file)
    if selected_query_ids is not None:
        pack_rows = [row for row in pack_rows if str(row["pack"]["query_id"]) in selected_query_ids]
    if args.limit:
        pack_rows = pack_rows[: args.limit]
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    model, tokenizer = load_model(
        args.model,
        quantization=args.quantization,
        dtype=args.dtype,
        local_files_only=not args.allow_download,
        experts_implementation=args.experts_implementation,
    )
    model_load_s = time.perf_counter() - load_started
    outputs: list[dict[str, Any]] = []
    started = time.perf_counter()
    for index, row in enumerate(pack_rows, start=1):
        pack = row["pack"]
        query = queries.get(str(pack["query_id"]))
        if query is None:
            continue
        for qa_type in ("function", "literature", "mechanism"):
            prompt = build_prompt(query, pack, qa_type=qa_type, evidence_mode=args.evidence_mode)
            answer, usage = generate(model, tokenizer, prompt, max_new_tokens=args.max_new_tokens)
            outputs.append(
                {
                    "query_id": pack["query_id"],
                    "qa_type": qa_type,
                    "prompt": prompt,
                    "answer": answer,
                    "go_ids": sorted(set(re.findall(r"GO:\d{7}", answer))),
                    "pmids": sorted(extract_pmids(answer)),
                    "citation_ids": sorted(
                        {f"[{kind}{rank}]" for kind, rank in re.findall(r"\[?([EPGL])(\d+)\]?", answer)}
                    ),
                    **usage,
                }
            )
        print(json.dumps({"generated_queries": index, "total": len(pack_rows)}), flush=True)

    generation_latencies = [float(row["generation_s"]) for row in outputs]
    output_tokens = sum(int(row["output_tokens"]) for row in outputs)
    total_generation_s = sum(generation_latencies)
    result = {
        "dataset": "BioRAG-SeqLit-DAG generated agent QA pilot",
        "claim_scope": (
            "Generated answers must be scored for answer correctness and citation entailment separately. "
            "This artifact records model outputs and does not treat string-matched GO/PMID mentions as proof of correctness."
        ),
        "model": args.model,
        "query_count": len({row["query_id"] for row in outputs}),
        "answer_count": len(outputs),
        "max_new_tokens": args.max_new_tokens,
        "quantization": args.quantization,
        "dtype": args.dtype,
        "evidence_mode": args.evidence_mode,
        "model_load_s": round(model_load_s, 3),
        "elapsed_s": round(time.perf_counter() - started, 3),
        "mean_generation_ms": round(1000.0 * total_generation_s / len(outputs), 3) if outputs else 0.0,
        "p50_generation_ms": round(1000.0 * percentile(generation_latencies, 0.50), 3),
        "p95_generation_ms": round(1000.0 * percentile(generation_latencies, 0.95), 3),
        "generated_tokens_per_s": round(output_tokens / total_generation_s, 3) if total_generation_s else 0.0,
        "peak_gpu_memory_gib": round(torch.cuda.max_memory_allocated() / (1024**3), 3),
        "outputs": outputs,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "answer_count": len(outputs)}, indent=2))


def build_prompt(
    query: dict[str, Any],
    pack: dict[str, Any],
    *,
    qa_type: str,
    evidence_mode: str = "raw",
) -> str:
    selector_config = dict((pack.get("selector_config") or {}).get(qa_type) or {})
    output_k = int(selector_config.get("output_k", 5))
    candidate_k = int(selector_config.get("candidate_k", 10))
    if qa_type == "function":
        question = "Which GO terms are supported by the retrieved sequence evidence?"
        citation_kind = "G" if evidence_mode == "graph_idf" else "E"
        constraint = (
            f"Copy the first {output_k} distinct GO IDs from Evidence in exactly the presented order. "
            f"Only mention GO IDs explicitly present in candidate evidence, and cite each claim with "
            f"[{citation_kind}<rank>]."
        )
        answer_schema = "ANSWER: " + "; ".join(f"<GO_ID> [{citation_kind}#]" for _ in range(output_k))
        citation_schema = "CITATIONS: " + " ".join(f"[{citation_kind}#]" for _ in range(output_k))
    elif qa_type == "literature":
        question = "Which PubMed papers are supported by the retrieved sequence evidence?"
        citation_kind = "L" if evidence_mode == "graph_idf" else "P"
        constraint = (
            f"Copy the first {output_k} distinct PMIDs from Evidence in exactly the presented order. "
            f"Only mention PMIDs explicitly present in evidence, and cite each PMID as [{citation_kind}<rank>]."
        )
        answer_schema = "ANSWER: " + "; ".join(f"PMID:<PMID> [{citation_kind}#]" for _ in range(output_k))
        citation_schema = "CITATIONS: " + " ".join(f"[{citation_kind}#]" for _ in range(output_k))
    else:
        question = "Can this evidence establish a molecular mechanism for the query sequence?"
        constraint = "If mechanism evidence is absent, explicitly abstain and state what additional evidence is needed."
        answer_schema = "ANSWER: INSUFFICIENT_EVIDENCE"
        citation_schema = "CITATIONS: NONE"
    evidence: list[str] = []
    if evidence_mode == "graph_idf" and qa_type == "function":
        candidates_by_rank = {int(item["rank"]): item for item in pack["candidates"]}
        for claim_rank, claim in enumerate(pack.get("go_claims", [])[:10], start=1):
            evidence_id = str(claim["evidence_ids"][0])
            rank = int(evidence_id.removeprefix("E"))
            candidate = candidates_by_rank[rank]
            evidence.append(
                f"[G{claim_rank}] GO={claim['go_id']} source=[{evidence_id}] "
                f"accession={candidate['accession']} symbol={candidate.get('symbol')} "
                f"graph_score={claim['score']:.5f} go_df={claim['document_frequency']}"
            )
    elif evidence_mode == "graph_idf" and qa_type == "literature":
        for claim_rank, claim in enumerate(pack.get("paper_claims", [])[:10], start=1):
            evidence.append(
                f"[L{claim_rank}] PMID={claim['pmid']} source=[P{claim['paper_rank']}] "
                f"supported_by_accession={claim['accessions'][0]} "
                f"GO={','.join(claim['go_ids'])} graph_score={claim['score']:.5f}"
            )
    elif qa_type in {"function", "mechanism"}:
        for item in pack["candidates"][:candidate_k]:
            evidence.append(
                f"[E{item['rank']}] accession={item['accession']} symbol={item.get('symbol')} "
                f"GO={','.join(item['go_ids']) or 'none'}"
            )
    if evidence_mode == "raw" and qa_type in {"literature", "mechanism"}:
        for rank, pmid in enumerate(pack["papers"][:20], start=1):
            support = next(
                (item for item in pack["candidates"][:candidate_k] if str(pmid) in item["paper_ids"]),
                None,
            )
            if support is not None:
                evidence.append(f"[P{rank}] PMID={pmid} supported_by_accession={support['accession']}")
    return "\n".join(
        [
            "Evidence:",
            *evidence,
            "",
            "Query: held-out protein sequence (identifier masked)",
            f"Question: {question}",
            constraint,
            "Use only the evidence above. Do not invent GO IDs, PMIDs, or citation IDs.",
            "Literal square brackets around every evidence ID are mandatory.",
            "Respond in exactly two lines using this placeholder schema:",
            answer_schema,
            citation_schema,
        ]
    )


def load_model(
    model_path: str,
    *,
    quantization: str = "4bit",
    dtype: str = "auto",
    local_files_only: bool = True,
    experts_implementation: str | None = None,
):
    dtype_map = {
        "auto": "auto",
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=True,
        local_files_only=local_files_only,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model_kwargs: dict[str, Any] = {
        "trust_remote_code": True,
        "local_files_only": local_files_only,
        "device_map": "auto",
        "dtype": dtype_map[dtype],
    }
    if quantization == "4bit":
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16 if dtype == "bfloat16" else torch.float16,
        )
    if experts_implementation:
        model_kwargs["experts_implementation"] = experts_implementation
    model = AutoModelForCausalLM.from_pretrained(model_path, **model_kwargs)
    model.eval()
    return model, tokenizer


def generate(model: Any, tokenizer: Any, prompt: str, *, max_new_tokens: int) -> tuple[str, dict[str, Any]]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an auditable biomedical retrieval agent. Follow the requested output format. "
                "Use only supplied evidence and abstain when it is insufficient."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(rendered, return_tensors="pt", truncation=True, max_length=8192, add_special_tokens=False)
    inputs = {key: value.to(model.device) for key, value in inputs.items()}
    stop_ids = [tokenizer.eos_token_id]
    eot_id = tokenizer.convert_tokens_to_ids("<turn|>") if "<turn|>" in tokenizer.get_vocab() else None
    if isinstance(eot_id, int) and eot_id >= 0 and eot_id not in stop_ids:
        stop_ids.append(eot_id)
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    started = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=stop_ids,
        )
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    generation_s = time.perf_counter() - started
    generated = output[0][inputs["input_ids"].shape[1] :]
    answer = tokenizer.decode(generated, skip_special_tokens=True).strip()
    return answer, {
        "input_tokens": int(inputs["input_ids"].shape[1]),
        "output_tokens": int(generated.shape[0]),
        "generation_s": round(generation_s, 6),
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_query_ids(path: str | None) -> set[str] | None:
    if not path:
        return None
    return {line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()}


def extract_pmids(text: str) -> set[str]:
    return set(re.findall(r"(?i)PMID\s*[:=]?\s*(\d{7,8})", text))


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate local model answers from SeqLit evidence packs")
    parser.add_argument("--model", required=True)
    parser.add_argument("--packs", default="reports/results/agent_qa_prott5_blast_packs.jsonl")
    parser.add_argument("--queries", default="data/seq_lit_dag_function_heldout_2k/queries.jsonl")
    parser.add_argument("--query-ids-file", default=None)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--evidence-mode", choices=("raw", "graph_idf"), default="raw")
    parser.add_argument("--quantization", choices=("none", "4bit"), default="4bit")
    parser.add_argument("--dtype", choices=("auto", "bfloat16", "float16", "float32"), default="auto")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--experts-implementation", choices=("eager", "grouped_mm"), default=None)
    parser.add_argument("--output", default="reports/results/agent_qa_generated_omnigene.json")
    return parser.parse_args()


if __name__ == "__main__":
    main()
