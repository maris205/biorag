#!/usr/bin/env python3
"""Train a small DNA-ESM2-style encoder with MLM and view contrastive loss."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import torch
from transformers import BertConfig, BertForMaskedLM, get_cosine_schedule_with_warmup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.dna_es2 import DNA3merTokenizer, info_nce, reverse_complement


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    records = load_records(Path(args.source), args.max_records, args.min_length)
    if not records:
        raise SystemExit("No usable DNA records were found")
    tokenizer = DNA3merTokenizer(max_length=args.max_length)
    config = BertConfig(
        vocab_size=tokenizer.vocab_size,
        hidden_size=args.hidden_size,
        num_hidden_layers=args.layers,
        num_attention_heads=args.heads,
        intermediate_size=args.intermediate_size or args.hidden_size * 4,
        max_position_embeddings=args.max_length,
        hidden_dropout_prob=args.dropout,
        attention_probs_dropout_prob=args.dropout,
        pad_token_id=tokenizer.pad_token_id,
        type_vocab_size=1,
    )
    model = BertForMaskedLM(config).to(device)
    projection = torch.nn.Sequential(
        torch.nn.Linear(args.hidden_size, args.projection_dim),
        torch.nn.GELU(),
        torch.nn.Linear(args.projection_dim, args.projection_dim),
    ).to(device)
    autocast_dtype = torch.bfloat16 if device.type == "cuda" and args.dtype == "bf16" else torch.float16 if device.type == "cuda" and args.dtype == "fp16" else None
    optimizer = torch.optim.AdamW(
        list(model.parameters()) + list(projection.parameters()),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )
    scheduler = get_cosine_schedule_with_warmup(optimizer, args.warmup_steps, args.steps)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    model.train()
    losses: list[float] = []
    for step in range(1, args.steps + 1):
        sequences = [random.choice(records) for _ in range(args.batch_size)]
        view1, view2 = make_views(sequences, args.max_bases, args.rc_probability)
        ids1, mask1 = tokenizer.batch_encode(view1)
        ids2, mask2 = tokenizer.batch_encode(view2)
        ids1, mask1, ids2, mask2 = ids1.to(device), mask1.to(device), ids2.to(device), mask2.to(device)
        masked1, labels1 = tokenizer.mask_batch(ids1, mask1)
        masked2, labels2 = tokenizer.mask_batch(ids2, mask2)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=autocast_dtype, enabled=autocast_dtype is not None):
            out1 = model(input_ids=masked1, attention_mask=mask1, labels=labels1, output_hidden_states=True)
            mlm_loss = out1.loss
            if args.contrastive_weight > 0:
                out2 = model(input_ids=masked2, attention_mask=mask2, labels=labels2, output_hidden_states=True)
                z1 = projection(pool_hidden(out1.hidden_states[-1], mask1))
                z2 = projection(pool_hidden(out2.hidden_states[-1], mask2))
                mlm_loss = (out1.loss + out2.loss) / 2.0
                contrastive_loss = info_nce(z1, z2, args.temperature)
            else:
                contrastive_loss = torch.zeros((), device=device)
            loss = args.mlm_weight * mlm_loss + args.contrastive_weight * contrastive_loss
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
        optimizer.step()
        scheduler.step()
        losses.append(float(loss.detach().cpu()))
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            elapsed = time.perf_counter() - started
            print(json.dumps({"step": step, "steps": args.steps, "loss": round(float(loss.detach().cpu()), 5), "mlm_loss": round(float(mlm_loss.detach().cpu()), 5), "contrastive_loss": round(float(contrastive_loss.detach().cpu()), 5), "lr": scheduler.get_last_lr()[0], "records": len(records), "elapsed_s": round(elapsed, 2), "gpu_memory_gib": round(torch.cuda.max_memory_allocated() / 1024**3, 3) if torch.cuda.is_available() else 0.0}), flush=True)
    model.eval()
    model.bert.save_pretrained(output / "encoder")
    tokenizer.save_pretrained(output / "encoder")
    model.save_pretrained(output / "mlm")
    torch.save(projection.state_dict(), output / "contrastive_projection.pt")
    (output / "training_config.json").write_text(json.dumps(vars(args), indent=2) + "\n", encoding="utf-8")
    (output / "training_summary.json").write_text(json.dumps({"records": len(records), "steps": args.steps, "final_loss": losses[-1] if losses else None, "mean_last_10_loss": sum(losses[-10:]) / min(len(losses), 10) if losses else None, "device": str(device), "hidden_size": args.hidden_size, "layers": args.layers, "max_length": args.max_length}, indent=2) + "\n", encoding="utf-8")


def load_records(path: Path, max_records: int, min_length: int) -> list[str]:
    records: list[str] = []
    with path.open("rt", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            sequence = "".join(raw.strip().upper().split()).replace("U", "T")
            if len(sequence) >= min_length and set(sequence) <= set("ACGTN"):
                records.append(sequence)
            if max_records and len(records) >= max_records:
                break
    return records


def make_views(records: list[str], max_bases: int, rc_probability: float) -> tuple[list[str], list[str]]:
    views1: list[str] = []
    views2: list[str] = []
    for sequence in records:
        # Keep the same crop in both views; independent random crops can have
        # too little overlap to be valid instance positives for InfoNCE.
        crop = random_crop(sequence, max_bases)
        views = [crop, crop]
        if random.random() < rc_probability:
            views[1] = reverse_complement(views[1])
        views1.append(views[0])
        views2.append(views[1])
    return views1, views2


def random_crop(sequence: str, max_bases: int) -> str:
    if len(sequence) <= max_bases:
        return sequence
    start = random.randint(0, len(sequence) - max_bases)
    return sequence[start : start + max_bases]


def pool_hidden(hidden: Any, attention_mask: Any) -> Any:
    mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
    return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train DNA-ESM2-style encoder")
    parser.add_argument("--source", default="/autodl-fs/data/omnigene_v2/data/dna_32g.txt")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-records", type=int, default=100000)
    parser.add_argument("--min-length", type=int, default=128)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--max-bases", type=int, default=512)
    parser.add_argument("--hidden-size", type=int, default=384)
    parser.add_argument("--layers", type=int, default=8)
    parser.add_argument("--heads", type=int, default=6)
    parser.add_argument("--intermediate-size", type=int, default=0)
    parser.add_argument("--projection-dim", type=int, default=128)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--warmup-steps", type=int, default=50)
    parser.add_argument("--learning-rate", type=float, default=5e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--mlm-weight", type=float, default=1.0)
    parser.add_argument("--contrastive-weight", type=float, default=0.25)
    parser.add_argument("--temperature", type=float, default=0.07)
    parser.add_argument("--rc-probability", type=float, default=0.5)
    parser.add_argument("--dtype", choices=["fp32", "fp16", "bf16"], default="bf16")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--log-every", type=int, default=10)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
