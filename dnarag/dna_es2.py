"""DNA-ESM2-style tokenizer and embedding model utilities."""
from __future__ import annotations

import itertools
import json
import re
from pathlib import Path
from typing import Any

import numpy as np


DNA_ALPHABET = "ACGTN"
DNA_RE = re.compile("[^ACGTN]")
KMER_SIZE = 3
SPECIAL_TOKENS = {
    "pad_token": "[PAD]",
    "cls_token": "[CLS]",
    "sep_token": "[SEP]",
    "mask_token": "[MASK]",
    "unk_token": "[UNK]",
}


class DNA3merTokenizer:
    """Deterministic overlapping 3-mer tokenizer for DNA sequences."""

    def __init__(self, max_length: int = 512):
        self.max_length = int(max_length)
        self.special_to_id = {token: index for index, token in enumerate(SPECIAL_TOKENS.values())}
        kmers = ["".join(chars) for chars in itertools.product(DNA_ALPHABET, repeat=KMER_SIZE)]
        self.kmer_to_id = {kmer: index + len(self.special_to_id) for index, kmer in enumerate(kmers)}
        self.id_to_token = {index: token for token, index in self.special_to_id.items()}
        self.id_to_token.update({index: kmer for kmer, index in self.kmer_to_id.items()})
        self.vocab_size = len(self.id_to_token)
        self.pad_token_id = self.special_to_id[SPECIAL_TOKENS["pad_token"]]
        self.cls_token_id = self.special_to_id[SPECIAL_TOKENS["cls_token"]]
        self.sep_token_id = self.special_to_id[SPECIAL_TOKENS["sep_token"]]
        self.mask_token_id = self.special_to_id[SPECIAL_TOKENS["mask_token"]]
        self.unk_token_id = self.special_to_id[SPECIAL_TOKENS["unk_token"]]

    def clean(self, sequence: str) -> str:
        return DNA_RE.sub("N", str(sequence).upper().replace("U", "T"))

    def encode(self, sequence: str, *, max_length: int | None = None) -> list[int]:
        limit = int(max_length or self.max_length)
        sequence = self.clean(sequence)
        max_bases = max(limit - 2 + KMER_SIZE - 1, KMER_SIZE)
        sequence = sequence[:max_bases]
        ids = [self.cls_token_id]
        ids.extend(
            self.kmer_to_id.get(sequence[index : index + KMER_SIZE], self.unk_token_id)
            for index in range(max(len(sequence) - KMER_SIZE + 1, 0))
        )
        ids.append(self.sep_token_id)
        return ids[:limit]

    def batch_encode(self, sequences: list[str], *, max_length: int | None = None) -> tuple[Any, Any]:
        import torch

        limit = int(max_length or self.max_length)
        rows = [self.encode(sequence, max_length=limit) for sequence in sequences]
        input_ids = torch.full((len(rows), limit), self.pad_token_id, dtype=torch.long)
        attention_mask = torch.zeros((len(rows), limit), dtype=torch.long)
        for row_index, row in enumerate(rows):
            length = min(len(row), limit)
            input_ids[row_index, :length] = torch.tensor(row[:length], dtype=torch.long)
            attention_mask[row_index, :length] = 1
        return input_ids, attention_mask

    def mask_batch(self, input_ids: Any, attention_mask: Any, *, probability: float = 0.15, generator: Any = None) -> tuple[Any, Any]:
        import torch

        labels = input_ids.clone()
        probability_matrix = torch.full(labels.shape, float(probability), device=labels.device)
        special = (input_ids == self.pad_token_id) | (input_ids == self.cls_token_id) | (input_ids == self.sep_token_id)
        probability_matrix.masked_fill_(special | (attention_mask == 0), 0.0)
        selected = torch.bernoulli(probability_matrix, generator=generator).bool()
        labels[~selected] = -100
        input_ids = input_ids.clone()
        masked = selected & (torch.rand(labels.shape, device=labels.device, generator=generator) < 0.8)
        input_ids[masked] = self.mask_token_id
        randomize = selected & ~masked & (torch.rand(labels.shape, device=labels.device, generator=generator) < 0.5)
        random_tokens = torch.randint(self.kmer_start_id, self.vocab_size, labels.shape, device=labels.device, generator=generator)
        input_ids[randomize] = random_tokens[randomize]
        return input_ids, labels

    @property
    def kmer_start_id(self) -> int:
        return len(self.special_to_id)

    def save_pretrained(self, path: str | Path) -> None:
        output = Path(path)
        output.mkdir(parents=True, exist_ok=True)
        payload = {
            "max_length": self.max_length,
            "alphabet": DNA_ALPHABET,
            "kmer_size": KMER_SIZE,
            "special_tokens": SPECIAL_TOKENS,
            "kmer_to_id": self.kmer_to_id,
        }
        (output / "dna_tokenizer.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def from_pretrained(cls, path: str | Path) -> "DNA3merTokenizer":
        payload = json.loads((Path(path) / "dna_tokenizer.json").read_text(encoding="utf-8"))
        tokenizer = cls(max_length=int(payload.get("max_length", 512)))
        if payload.get("kmer_to_id"):
            tokenizer.kmer_to_id = {str(key): int(value) for key, value in payload["kmer_to_id"].items()}
            tokenizer.id_to_token = {index: token for token, index in tokenizer.special_to_id.items()}
            tokenizer.id_to_token.update({index: kmer for kmer, index in tokenizer.kmer_to_id.items()})
            tokenizer.vocab_size = len(tokenizer.id_to_token)
        return tokenizer


def reverse_complement(sequence: str) -> str:
    table = str.maketrans("ACGTNacgtn", "TGCANtgcan")
    return str(sequence).translate(table)[::-1]


def mean_pool(hidden: Any, attention_mask: Any) -> Any:
    mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
    return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)


def info_nce(z1: Any, z2: Any, temperature: float = 0.07) -> Any:
    import torch.nn.functional as F

    z1 = F.normalize(z1.float(), dim=-1)
    z2 = F.normalize(z2.float(), dim=-1)
    logits = z1 @ z2.T / float(temperature)
    labels = __import__("torch").arange(logits.shape[0], device=logits.device)
    return (F.cross_entropy(logits, labels) + F.cross_entropy(logits.T, labels)) / 2.0


class DNAESMEmbedder:
    """Load a trained DNA-ESM2-style encoder for BioRAG vector extraction."""

    def __init__(self, model_name: str, pooling: str = "mean", dtype: str = "fp32"):
        try:
            import torch
            from transformers import BertModel
        except Exception as exc:
            raise RuntimeError("Install torch and transformers for the DNA-ESM backend") from exc
        self.torch = torch
        self.pooling = str(pooling or "mean").lower()
        self.tokenizer = DNA3merTokenizer.from_pretrained(model_name)
        self.device = torch.device("cpu" if not torch.cuda.is_available() else "cuda")
        self.model = BertModel.from_pretrained(model_name, add_pooling_layer=False).to(self.device)
        if self.device.type == "cuda" and dtype in {"fp16", "bf16"}:
            self.model.to(dtype=torch.float16 if dtype == "fp16" else torch.bfloat16)
        else:
            self.model.to(dtype=torch.float32)
        self.model.eval()
        self.dim = int(self.model.config.hidden_size)

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        input_ids, attention_mask = self.tokenizer.batch_encode(texts)
        input_ids, attention_mask = input_ids.to(self.device), attention_mask.to(self.device)
        with self.torch.inference_mode():
            hidden = self.model(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            if self.pooling == "cls":
                pooled = hidden[:, 0, :]
            elif self.pooling == "last":
                positions = attention_mask.sum(dim=1).clamp_min(1) - 1
                pooled = hidden[self.torch.arange(hidden.shape[0], device=self.device), positions]
            else:
                pooled = mean_pool(hidden, attention_mask)
            pooled = self.torch.nn.functional.normalize(pooled.float(), p=2, dim=1)
        return pooled.cpu().numpy().astype(np.float32)
