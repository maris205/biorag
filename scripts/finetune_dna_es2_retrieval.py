#!/usr/bin/env python3
"""Fine-tune DNA-ESM2 embeddings with gene-aware contrastive pairs."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from transformers import BertModel, get_cosine_schedule_with_warmup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.dna_es2 import DNA3merTokenizer, reverse_complement


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    tokenizer = DNA3merTokenizer.from_pretrained(args.input_model)
    groups = load_gene_groups(Path(args.source), Path(args.exclude_benchmark), args.max_records, args.min_length)
    genes = [gene for gene, records in groups.items() if len(records) >= 2]
    if len(genes) < 2:
        raise SystemExit("Need at least two genes with two or more DNA windows each")
    model = BertModel.from_pretrained(args.input_model, add_pooling_layer=False).to(device)
    if device.type == "cuda" and args.dtype in {"fp16", "bf16"}:
        model.to(dtype=torch.float16 if args.dtype == "fp16" else torch.bfloat16)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    scheduler = get_cosine_schedule_with_warmup(optimizer, args.warmup_steps, args.steps)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    losses: list[float] = []
    model.train()
    for step in range(1, args.steps + 1):
        selected_genes = random.sample(genes, min(args.batch_size, len(genes)))
        anchors = [random.choice(groups[gene]) for gene in selected_genes]
        positives = [random.choice(groups[gene]) for gene in selected_genes]
        if args.rc_probability:
            positives = [reverse_complement(seq) if random.random() < args.rc_probability else seq for seq in positives]
        ids1, mask1 = tokenizer.batch_encode([random_crop(seq, args.max_bases) for seq in anchors])
        ids2, mask2 = tokenizer.batch_encode([random_crop(seq, args.max_bases) for seq in positives])
        ids1, mask1, ids2, mask2 = ids1.to(device), mask1.to(device), ids2.to(device), mask2.to(device)
        optimizer.zero_grad(set_to_none=True)
        autocast_dtype = torch.bfloat16 if device.type == "cuda" and args.dtype == "bf16" else torch.float16 if device.type == "cuda" and args.dtype == "fp16" else None
        with torch.autocast(device_type="cuda", dtype=autocast_dtype, enabled=autocast_dtype is not None):
            z1 = pool_hidden(model(input_ids=ids1, attention_mask=mask1).last_hidden_state, mask1)
            z2 = pool_hidden(model(input_ids=ids2, attention_mask=mask2).last_hidden_state, mask2)
            z1, z2 = F.normalize(z1.float(), dim=-1), F.normalize(z2.float(), dim=-1)
            logits = z1 @ z2.T / args.temperature
            labels = torch.arange(logits.shape[0], device=device)
            loss = (F.cross_entropy(logits, labels) + F.cross_entropy(logits.T, labels)) / 2.0
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
        optimizer.step()
        scheduler.step()
        losses.append(float(loss.detach().cpu()))
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            print(json.dumps({"step": step, "steps": args.steps, "loss": round(losses[-1], 5), "lr": scheduler.get_last_lr()[0], "genes": len(genes), "records": sum(len(x) for x in groups.values()), "elapsed_s": round(time.perf_counter() - started, 2), "gpu_memory_gib": round(torch.cuda.max_memory_allocated() / 1024**3, 3) if torch.cuda.is_available() else 0.0}), flush=True)
    model.eval()
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    (output / "fine_tuning_config.json").write_text(json.dumps(vars(args), indent=2) + "\n", encoding="utf-8")
    (output / "fine_tuning_summary.json").write_text(json.dumps({"genes": len(genes), "records": sum(len(x) for x in groups.values()), "steps": args.steps, "final_loss": losses[-1], "mean_last_10_loss": sum(losses[-10:]) / min(10, len(losses)), "device": str(device)}, indent=2) + "\n", encoding="utf-8")


def load_gene_groups(path: Path, exclude_benchmark: Path, max_records: int, min_length: int) -> dict[str, list[str]]:
    excluded: set[str] = set()
    if exclude_benchmark.exists():
        for line in exclude_benchmark.open(encoding="utf-8"):
            row = json.loads(line)
            biological = (row.get("expected") or {}).get("biological") or {}
            excluded.update(str(x).upper() for x in biological.get("gene_symbols") or [])
            excluded.update(str(x).upper() for x in biological.get("protein_gene_names") or [])
    groups: dict[str, list[str]] = defaultdict(list)
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            sequence = "".join(str(row.get("text") or "").upper().split()).replace("U", "T")
            labels = row.get("labels") or {}
            genes = [str(x).upper() for x in labels.get("gene_symbols") or []]
            if len(sequence) < min_length or not genes or any(ch not in "ACGTN" for ch in sequence):
                continue
            if any(gene in excluded for gene in genes):
                continue
            for gene in set(genes):
                groups[gene].append(sequence)
            count += 1
            if max_records and count >= max_records:
                break
    return dict(groups)


def random_crop(sequence: str, max_bases: int) -> str:
    if len(sequence) <= max_bases:
        return sequence
    start = random.randint(0, len(sequence) - max_bases)
    return sequence[start : start + max_bases]


def pool_hidden(hidden: Any, attention_mask: Any) -> Any:
    mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
    return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune DNA-ESM2 embeddings with gene-aware contrastive pairs")
    parser.add_argument("--input-model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source", default="data/biorag_standard_v0/corpus/dna_sequence_window.jsonl")
    parser.add_argument("--exclude-benchmark", default="benchmarks/dna_parent_frag_100.jsonl")
    parser.add_argument("--max-records", type=int, default=100000)
    parser.add_argument("--min-length", type=int, default=64)
    parser.add_argument("--max-bases", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--warmup-steps", type=int, default=50)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--temperature", type=float, default=0.07)
    parser.add_argument("--rc-probability", type=float, default=0.5)
    parser.add_argument("--dtype", choices=["fp32", "fp16", "bf16"], default="bf16")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--log-every", type=int, default=25)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
