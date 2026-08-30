from __future__ import annotations

import torch

from dnarag.dna_es2 import DNA3merTokenizer, info_nce, reverse_complement


def test_dna_3mer_tokenizer_shapes_and_special_tokens() -> None:
    tokenizer = DNA3merTokenizer(max_length=16)
    input_ids, attention_mask = tokenizer.batch_encode(["ACGTACGT", "NNNN"])
    assert tokenizer.vocab_size == 130
    assert input_ids.shape == (2, 16)
    assert attention_mask.shape == (2, 16)
    assert input_ids[0, 0].item() == tokenizer.cls_token_id
    assert input_ids[0, attention_mask[0].sum() - 1].item() == tokenizer.sep_token_id


def test_reverse_complement_is_involution() -> None:
    sequence = "ACGTNACGTT"
    assert reverse_complement(reverse_complement(sequence)) == sequence


def test_info_nce_is_finite() -> None:
    z1 = torch.randn(4, 8)
    z2 = torch.randn(4, 8)
    loss = info_nce(z1, z2)
    assert torch.isfinite(loss)
