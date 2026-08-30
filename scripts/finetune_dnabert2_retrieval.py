#!/usr/bin/env python3
"""Fine-tune DNABERT-2 with gene positives and GC-matched hard negatives."""
from __future__ import annotations

import argparse
import importlib
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.retrieval.vector import _load_dnabert2_classes


def main() -> None:
    args = parse_args()
    seed_everything(args.seed)
    model_path = Path(args.input_model).expanduser().resolve()
    os.environ.setdefault("DNARAG_DNABERT2_MODULE_DIR", str(model_path))
    config_cls, encoder_cls = _load_dnabert2_classes(str(model_path))
    module = importlib.import_module(encoder_cls.__module__)
    mlm_cls = getattr(module, "BertForMaskedLM")
    config = config_cls.from_pretrained(str(model_path), local_files_only=True)

    from transformers import AutoTokenizer, get_cosine_schedule_with_warmup

    tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.sep_token
    groups, excluded = load_gene_groups(
        Path(args.source),
        Path(args.exclude_benchmark),
        max_records=args.max_records,
        min_length=args.min_length,
    )
    genes = [gene for gene, values in groups.items() if len(values) >= 2]
    if len(genes) < 2:
        raise SystemExit("Need at least two genes with at least two windows each")

    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    model = mlm_cls.from_pretrained(str(model_path), config=config, local_files_only=True).to(device)
    # The official DNABERT-2 attention fallback has a BF16 inference limitation
    # when no masked-token subset is supplied, so use FP32 for this contrastive run.
    model.to(dtype=torch.float32)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    scheduler = get_cosine_schedule_with_warmup(optimizer, args.warmup_steps, args.steps)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "training_config.json").write_text(json.dumps(vars(args), indent=2) + "\n", encoding="utf-8")

    gc_bins = build_gc_bins(groups, genes)
    losses: list[float] = []
    started = time.perf_counter()
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    for step in range(1, args.steps + 1):
        selected = random.sample(genes, min(args.batch_size, len(genes)))
        anchors = [random.choice(groups[gene]) for gene in selected]
        positives = [random.choice([item for item in groups[gene] if item != anchor] or groups[gene]) for gene, anchor in zip(selected, anchors)]
        negatives = [sample_hard_negative(groups, gc_bins, gene, anchor) for gene, anchor in zip(selected, anchors)]
        encoded_a = encode_batch(tokenizer, anchors, args.max_length, device)
        encoded_p = encode_batch(tokenizer, positives, args.max_length, device)
        encoded_n = encode_batch(tokenizer, negatives, args.max_length, device)
        optimizer.zero_grad(set_to_none=True)
        z_a = embed(model, encoded_a, tokenizer)
        z_p = embed(model, encoded_p, tokenizer)
        z_n = embed(model, encoded_n, tokenizer)
        logits = z_a @ z_p.T / args.temperature
        labels = torch.arange(logits.shape[0], device=device)
        info_loss = (F.cross_entropy(logits, labels) + F.cross_entropy(logits.T, labels)) / 2.0
        triplet_loss = F.relu(args.margin + (z_a * z_n).sum(dim=-1) - (z_a * z_p).sum(dim=-1)).mean()
        loss = info_loss + args.hard_negative_weight * triplet_loss
        if not torch.isfinite(loss):
            raise RuntimeError(f"Invalid loss at step {step}: {loss}")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
        optimizer.step()
        scheduler.step()
        losses.append(float(loss.detach().cpu()))
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            print(json.dumps({
                "step": step,
                "steps": args.steps,
                "loss": round(losses[-1], 6),
                "info_loss": round(float(info_loss.detach().cpu()), 6),
                "hard_negative_loss": round(float(triplet_loss.detach().cpu()), 6),
                "lr": scheduler.get_last_lr()[0],
                "genes": len(genes),
                "records": sum(len(values) for values in groups.values()),
                "excluded_genes": len(excluded),
                "elapsed_s": round(time.perf_counter() - started, 2),
                "gpu_memory_gib": round(torch.cuda.max_memory_allocated() / 1024**3, 3) if torch.cuda.is_available() else 0.0,
            }), flush=True)

    model.eval()
    model.save_pretrained(output, safe_serialization=False)
    tokenizer.save_pretrained(output)
    summary = {
        "genes": len(genes),
        "records": sum(len(values) for values in groups.values()),
        "excluded_genes": sorted(excluded),
        "steps": args.steps,
        "final_loss": losses[-1],
        "mean_last_10_loss": sum(losses[-10:]) / min(len(losses), 10),
        "device": str(device),
        "dtype": "fp32",
        "peak_memory_gib": torch.cuda.max_memory_allocated() / 1024**3 if torch.cuda.is_available() else 0.0,
        "elapsed_s": time.perf_counter() - started,
    }
    (output / "training_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def load_gene_groups(source: Path, exclude_benchmark: Path, *, max_records: int, min_length: int) -> tuple[dict[str, list[str]], set[str]]:
    excluded: set[str] = set()
    for raw in exclude_benchmark.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        biological = (json.loads(raw).get("expected") or {}).get("biological") or {}
        excluded.update(str(value).strip().upper() for value in biological.get("gene_symbols") or [] if value)
        excluded.update(str(value).strip().upper() for value in biological.get("protein_gene_names") or [] if value)
    groups: dict[str, list[str]] = defaultdict(list)
    count = 0
    with source.open(encoding="utf-8") as handle:
        for raw in handle:
            if max_records and count >= max_records:
                break
            row = json.loads(raw)
            sequence = clean_dna(row.get("text") or "")
            genes = {str(value).strip().upper() for value in (row.get("labels") or {}).get("gene_symbols") or [] if value}
            if len(sequence) < min_length or not genes or genes.intersection(excluded):
                continue
            for gene in genes:
                groups[gene].append(sequence)
            count += 1
    return dict(groups), excluded


def build_gc_bins(groups: dict[str, list[str]], genes: list[str]) -> dict[int, list[str]]:
    bins: dict[int, list[str]] = defaultdict(list)
    for gene in genes:
        sequence = groups[gene][0]
        gc = sum(base in "GC" for base in sequence) / max(len(sequence), 1)
        bins[int(round(gc * 20))].append(gene)
    return dict(bins)


def sample_hard_negative(groups: dict[str, list[str]], gc_bins: dict[int, list[str]], gene: str, anchor: str) -> str:
    gc = sum(base in "GC" for base in anchor) / max(len(anchor), 1)
    target_bin = int(round(gc * 20))
    candidates = [item for item in gc_bins.get(target_bin, []) if item != gene]
    if not candidates:
        candidates = [item for item in groups if item != gene]
    # Restrict to a small GC-matched pool, then choose the most similar
    # different-gene representative by 5-mer Jaccard overlap.
    pool = random.sample(candidates, min(len(candidates), 24))
    selected_gene = max(
        pool,
        key=lambda item: kmer_jaccard(anchor, groups[item][0], k=5),
    )
    return random.choice(groups[selected_gene])


def kmer_jaccard(left: str, right: str, *, k: int) -> float:
    left_kmers = {left[index : index + k] for index in range(max(len(left) - k + 1, 0))}
    right_kmers = {right[index : index + k] for index in range(max(len(right) - k + 1, 0))}
    union = left_kmers | right_kmers
    return len(left_kmers & right_kmers) / max(len(union), 1)


def encode_batch(tokenizer: Any, sequences: list[str], max_length: int, device: torch.device) -> dict[str, torch.Tensor]:
    encoded = tokenizer(sequences, return_tensors="pt", padding=True, truncation=True, max_length=max_length)
    return {key: value.to(device) for key, value in encoded.items()}


def embed(model: Any, encoded: dict[str, torch.Tensor], tokenizer: Any) -> torch.Tensor:
    output = model.bert(**encoded)
    hidden = output[0] if isinstance(output, (tuple, list)) else output.last_hidden_state
    mask = encoded["attention_mask"].clone()
    for token_id in (tokenizer.pad_token_id, tokenizer.cls_token_id, tokenizer.sep_token_id, tokenizer.bos_token_id, tokenizer.eos_token_id):
        if token_id is not None:
            mask = mask.masked_fill(encoded["input_ids"] == int(token_id), 0)
    pooled = (hidden * mask.unsqueeze(-1).to(hidden.dtype)).sum(dim=1) / mask.sum(dim=1).clamp_min(1).unsqueeze(-1)
    return F.normalize(pooled.float(), dim=-1)


def clean_dna(value: Any) -> str:
    return "".join(char for char in str(value).upper().replace("U", "T") if char in "ACGTN")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune DNABERT-2 for DNA retrieval")
    parser.add_argument("--input-model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source", default="data/biorag_standard_v0/corpus/dna_sequence_window.jsonl")
    parser.add_argument("--exclude-benchmark", default="benchmarks/dna_parent_frag_100.jsonl")
    parser.add_argument("--max-records", type=int, default=100000)
    parser.add_argument("--min-length", type=int, default=64)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--warmup-steps", type=int, default=100)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--temperature", type=float, default=0.07)
    parser.add_argument("--margin", type=float, default=0.2)
    parser.add_argument("--hard-negative-weight", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--log-every", type=int, default=100)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
