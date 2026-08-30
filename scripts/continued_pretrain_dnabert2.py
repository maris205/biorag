#!/usr/bin/env python3
"""Continue DNABERT-2 pretraining on cDNA windows without benchmark leakage."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dnarag.retrieval.vector import _load_dnabert2_classes


def main() -> None:
    args = parse_args()
    seed_everything(args.seed)
    model_path = Path(args.input_model).expanduser().resolve()
    os.environ.setdefault("DNARAG_DNABERT2_MODULE_DIR", str(model_path))

    from transformers import AutoTokenizer, get_cosine_schedule_with_warmup

    _config_cls, model_cls = _load_dnabert2_classes(str(model_path))
    module = importlib.import_module(model_cls.__module__)
    mlm_cls = getattr(module, "BertForMaskedLM")
    config = _config_cls.from_pretrained(str(model_path), local_files_only=True)
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.sep_token

    samples, excluded = load_samples(
        Path(args.source),
        Path(args.exclude_benchmark),
        max_records=args.max_records,
        min_length=args.min_length,
        window_size=args.window_size,
        window_stride=args.window_stride,
    )
    if not samples:
        raise SystemExit("No usable non-leaking cDNA samples were found")

    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    model = mlm_cls.from_pretrained(
        str(model_path),
        config=config,
        local_files_only=True,
    ).to(device)
    if device.type == "cuda" and args.dtype in {"bf16", "fp16"}:
        model.to(dtype=torch.bfloat16 if args.dtype == "bf16" else torch.float16)
    model.train()

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    scheduler = get_cosine_schedule_with_warmup(optimizer, args.warmup_steps, args.steps)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "training_config.json").write_text(json.dumps(vars(args), indent=2) + "\n", encoding="utf-8")

    autocast_dtype = (
        torch.bfloat16 if device.type == "cuda" and args.dtype == "bf16"
        else torch.float16 if device.type == "cuda" and args.dtype == "fp16"
        else None
    )
    losses: list[float] = []
    started = time.perf_counter()
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    for step in range(1, args.steps + 1):
        batch_sequences = [random.choice(samples) for _ in range(args.batch_size)]
        encoded = tokenizer(
            batch_sequences,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=args.max_length,
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}
        masked_ids, labels = mask_batch(
            encoded["input_ids"],
            encoded["attention_mask"],
            tokenizer,
            probability=args.mask_probability,
        )
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=autocast_dtype, enabled=autocast_dtype is not None):
            result = model(
                input_ids=masked_ids,
                attention_mask=encoded["attention_mask"],
                token_type_ids=encoded.get("token_type_ids"),
                labels=labels,
            )
            loss = result.loss
        if loss is None or not torch.isfinite(loss):
            raise RuntimeError(f"Invalid MLM loss at step {step}: {loss}")
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
                "mean_last_10_loss": round(sum(losses[-10:]) / min(len(losses), 10), 6),
                "lr": scheduler.get_last_lr()[0],
                "samples": len(samples),
                "excluded_genes": len(excluded),
                "elapsed_s": round(time.perf_counter() - started, 2),
                "gpu_memory_gib": round(torch.cuda.max_memory_allocated() / 1024**3, 3) if torch.cuda.is_available() else 0.0,
            }), flush=True)

    model.eval()
    # DNABERT-2 ties the MLM decoder to the input embedding matrix; its legacy
    # checkpoint metadata is not accepted by newer safetensors validation.
    model.save_pretrained(output, safe_serialization=False)
    tokenizer.save_pretrained(output)
    summary = {
        "samples": len(samples),
        "excluded_genes": sorted(excluded),
        "steps": args.steps,
        "final_loss": losses[-1],
        "mean_last_10_loss": sum(losses[-10:]) / min(len(losses), 10),
        "device": str(device),
        "dtype": args.dtype,
        "peak_memory_gib": torch.cuda.max_memory_allocated() / 1024**3 if torch.cuda.is_available() else 0.0,
        "elapsed_s": time.perf_counter() - started,
    }
    (output / "training_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def load_samples(
    source: Path,
    exclude_benchmark: Path,
    *,
    max_records: int,
    min_length: int,
    window_size: int,
    window_stride: int,
) -> tuple[list[str], set[str]]:
    excluded: set[str] = set()
    for raw in exclude_benchmark.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        biological = (row.get("expected") or {}).get("biological") or {}
        excluded.update(str(value).strip().upper() for value in biological.get("gene_symbols") or [] if value)
        excluded.update(str(value).strip().upper() for value in biological.get("protein_gene_names") or [] if value)

    parents: dict[str, list[tuple[int, str, set[str]]]] = defaultdict(list)
    count = 0
    with source.open(encoding="utf-8") as handle:
        for raw in handle:
            if max_records and count >= max_records:
                break
            row = json.loads(raw)
            sequence = clean_dna(row.get("text") or "")
            labels = row.get("labels") or {}
            genes = {str(value).strip().upper() for value in labels.get("gene_symbols") or [] if value}
            if len(sequence) < min_length or not genes or genes.intersection(excluded):
                continue
            metadata = row.get("metadata") or {}
            parent = str(metadata.get("parent_record_id") or row.get("record_id") or row.get("id"))
            start = int(metadata.get("window_start") or 0)
            parents[parent].append((start, sequence, genes))
            count += 1

    samples: list[str] = []
    for windows in parents.values():
        windows.sort(key=lambda item: item[0])
        for _, sequence, _genes in windows:
            samples.append(sequence)
        # Stitch adjacent overlapping windows into approximately 256-base views.
        for index in range(len(windows) - 2):
            start0, seq0, _ = windows[index]
            start1, seq1, _ = windows[index + 1]
            start2, seq2, _ = windows[index + 2]
            if start1 - start0 == window_stride and start2 - start1 == window_stride:
                stitched = seq0 + seq1[window_size - window_stride:] + seq2[window_size - window_stride:]
                if len(stitched) >= min_length:
                    samples.append(stitched)
    return samples, excluded


def clean_dna(value: Any) -> str:
    return "".join(char for char in str(value).upper().replace("U", "T") if char in "ACGTN")


def mask_batch(input_ids: torch.Tensor, attention_mask: torch.Tensor, tokenizer: Any, probability: float) -> tuple[torch.Tensor, torch.Tensor]:
    labels = input_ids.clone()
    special_ids = {
        int(value)
        for value in (
            getattr(tokenizer, "pad_token_id", None),
            getattr(tokenizer, "cls_token_id", None),
            getattr(tokenizer, "sep_token_id", None),
            getattr(tokenizer, "bos_token_id", None),
            getattr(tokenizer, "eos_token_id", None),
        )
        if value is not None
    }
    special = torch.zeros_like(input_ids, dtype=torch.bool)
    for token_id in special_ids:
        special |= input_ids.eq(token_id)
    selected = torch.rand(input_ids.shape, device=input_ids.device) < float(probability)
    selected &= attention_mask.bool() & ~special
    for row in range(selected.shape[0]):
        if not selected[row].any():
            valid = torch.where(attention_mask[row].bool() & ~special[row])[0]
            if len(valid):
                selected[row, valid[0]] = True
    labels[~selected] = -100
    masked = input_ids.clone()
    random_values = torch.rand(input_ids.shape, device=input_ids.device)
    mask_id = getattr(tokenizer, "mask_token_id", None)
    if mask_id is not None:
        masked[selected & (random_values < 0.8)] = int(mask_id)
    vocab_size = int(getattr(tokenizer, "vocab_size", int(input_ids.max().item()) + 1))
    random_tokens = torch.randint(vocab_size, input_ids.shape, device=input_ids.device)
    randomize = selected & (random_values >= 0.8) & (random_values < 0.9)
    masked[randomize] = random_tokens[randomize]
    return masked, labels


def seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Continue DNABERT-2 pretraining on cDNA windows")
    parser.add_argument("--input-model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source", default="data/biorag_standard_v0/corpus/dna_sequence_window.jsonl")
    parser.add_argument("--exclude-benchmark", default="benchmarks/dna_parent_frag_100.jsonl")
    parser.add_argument("--max-records", type=int, default=100000)
    parser.add_argument("--min-length", type=int, default=64)
    parser.add_argument("--window-size", type=int, default=128)
    parser.add_argument("--window-stride", type=int, default=64)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--warmup-steps", type=int, default=100)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--mask-probability", type=float, default=0.15)
    parser.add_argument("--dtype", choices=["fp32", "fp16", "bf16"], default="bf16")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--log-every", type=int, default=25)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
