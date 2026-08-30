# DNA Foundation Model Landscape for BioRAG

Date: 2026-08-29

## Objective

Identify DNA foundation models and training ideas that can improve the current
DNA vector candidate layer, whose best completed condition is DNABERT-2 mean
pooling with Bio Hit@10 `0.2500` and Bio MRR `0.2347` on the controlled20k
parent-fragment control. The target is not to replace BLASTN; it is to improve
candidate recall and sequence-conditioned RAG context.

## Completed 32-GB Screen

All newly tested models use the same 100-query controlled20k parent-fragment
protocol, 256/128 windows, mean pooling, and forward-strand inference. The
metric is a cDNA/DNA retrieval control using shared gene labels; it is not a
strict remote-homology benchmark.

| Model | Bio Hit@10 | Bio MRR | Query embedding ms | Lookup ms | Peak GiB |
|---|---:|---:|---:|---:|---:|
| DNABERT-2 mean (reference) | 0.2500 | 0.2347 | 0.6 | 10.38 | 0.67 |
| modernGENA-base mean | 0.2700 | 0.2153 | 0.7 | 7.11 | 0.35 |
| GENA-LM-base mean | 0.2500 | 0.2116 | 0.6 | 7.01 | 0.71 |
| Caduceus-PS mean | 0.0700 | 0.0214 | 1.8 | 11.62 | 0.50 |
| Caduceus-Ph mean | 0.0300 | 0.0116 | 3.7 | 6.80 | 0.29 |
| HyenaDNA-small mean | 0.0300 | 0.0279 | 1.6 | 6.80 | 0.15 |

The screen does not identify a drop-in public replacement for DNABERT-2 on
this cDNA control. modernGENA has the highest Hit@10, but its MRR is lower
than DNABERT-2 and the gain is not stable enough to promote without a larger
held-out evaluation. Caduceus and HyenaDNA are computationally feasible on a
32-GB GPU, but their pretrained representation spaces are poorly aligned with
the current short cDNA retrieval task. The next improvement should therefore
be task/domain adaptation rather than additional model shopping.

## Model Candidates

| Priority | Model | Architecture / inductive bias | Why it may help | Main risk | Planned use |
|---|---|---|---|---|---|
| 1 | modernGENA base/large | ModernBERT encoder, hybrid local/global attention, RoPE, 32k BPE | Recent encoder trained on 443 vertebrate assemblies with coding/regulatory upsampling; directly suitable for mean-pooled embeddings | New checkpoint and tokenizer distribution may not match short cDNA fragments | First public encoder screen |
| 2 | Caduceus-PS | Bi-directional Mamba, reverse-complement equivariance | Directly encodes DNA strand symmetry and long-range context; bidirectional encoder is suitable for retrieval | Custom Mamba dependencies and nonstandard pooling interface | First architecture screen |
| 3 | Caduceus-Ph | Bi-directional Mamba with RC augmentation | Same long-range/bidirectional advantages with a simpler augmentation recipe | RC augmentation may not transfer to transcript-fragment retrieval | Compare against Caduceus-PS |
| 4 | HyenaDNA medium/small | Hyena implicit convolutions, single-nucleotide tokens, long context | Fine nucleotide resolution can preserve mutations and short internal fragments; mature open implementation | Pretrained on hg38, so distribution mismatch for mixed-species/cDNA data; custom inference code | First single-nucleotide baseline |
| 5 | GENA-LM base/large | BERT-style bidirectional DNA LM with long-sequence tokenizer | Stronger long-sequence encoder baseline and easy comparison to modernGENA | Older generation and tokenizer may dilute local sequence signal | Lightweight compatibility control |
| 6 | Evo 2 7B / 1B base | StripedHyena 2 autoregressive model, single-nucleotide resolution, up to million-base context | Current high-end genome model, trained across all domains of life; strongest frontier candidate | Causal model is not designed as a retrieval encoder; custom Vortex stack and high compute cost | Second-stage exploratory comparator |
| 7 | Nucleotide Transformer v2 | Transformer encoder, multi-species pretraining | Already part of the current public baseline family | Existing cDNA result is weak under current pooling | Keep as fixed baseline |
| 8 | DNABERT-2 | Efficient multi-species Transformer with dynamic k-mer tokenization | Current best completed DNA dense baseline in this project | Still far below BLASTN | Primary reference |

### Models not prioritized for the first run

- GPN/GPN-MSA and predictive genomic models such as Enformer/Borzoi are useful
  for variant or regulatory prediction, but they are not drop-in generic
  sequence embedding models.
- DNAChunker, EvoLen, and LDARNet are promising learnable-tokenization ideas,
  but they are recent preprints and should first be treated as method
  inspiration unless stable public checkpoints become available.
- Directly using Evo 2 logits or generated text is not an embedding evaluation;
  any Evo 2 result must specify the hidden-state extraction and pooling rule.

## Relevant Literature

| Work | Status | Main idea | Relevance to BioRAG |
|---|---|---|---|
| Zhou et al., “DNABERT-2: Efficient Foundation Model and Benchmark for Multi-Species Genome,” arXiv:2306.15006, 2023 | Published baseline / public model | Efficient multi-species DNA pretraining with dynamic tokenization | Current reference model; establishes the starting point |
| Nguyen et al., “HyenaDNA: Long-Range Genomic Sequence Modeling at Single Nucleotide Resolution,” arXiv:2306.15794, 2023 | Public model / code | Single-nucleotide Hyena model with contexts up to 1M tokens | Tests whether nucleotide resolution and long context help fragment retrieval |
| Schiff et al., “Caduceus: Bi-Directional Equivariant Long-Range DNA Sequence Modeling,” arXiv:2403.03234, 2024 | Public model / code | BiMamba and reverse-complement equivariance | Most direct architectural match for strand-aware DNA retrieval |
| Dalla-Torre et al., “Nucleotide Transformer: Building and Evaluating Robust Foundation Models for Human Genomics,” Nature Methods, 2025, DOI: 10.1038/s41592-024-02523-z | Published baseline / public model | Large multi-species and human genomics models | Strong public comparison, already evaluated in this project |
| Fishman et al., “GENA-LM: a family of open-source foundational DNA language models for long sequences,” Nucleic Acids Research, 2025, DOI: 10.1093/nar/gkae1310 | Published / public model | Open long-sequence BERT-style DNA models | Direct encoder baseline and predecessor to modernGENA |
| Datta et al., “Embedding Is (Almost) All You Need: Retrieval-Augmented Inference for Generalizable Genomic Prediction Tasks,” arXiv:2508.04757, 2025 | Preprint | Fixed embeddings plus lightweight models can generalize better than fine-tuning under distribution shift | Supports evaluating frozen embeddings and measuring generalization separately from MLM loss |
| Ma, “Reverse-Complement Consistency for DNA Language Models,” arXiv:2509.18529, 2025 | Preprint | Explicit RC consistency regularization | Provides a low-cost fine-tuning objective beyond test-time RC averaging |
| Ledneva and Kuznetsov, “LDARNet: DNA Adaptive Representation Network with Learnable Tokenization for Genomic Modeling,” arXiv:2606.04552, 2026 | Emerging preprint | Learnable token boundaries with local/global modeling | Motivates a future tokenization ablation if public code/weights stabilize |
| Kim et al., “DNACHUNKER: Learnable Tokenization for DNA Language Models,” arXiv:2601.03019, 2026 | Emerging preprint | Context-dependent variable-length DNA units | Relevant to the current fixed 3-mer/5-mer limitation |
| Huang et al., “EvoLen: Evolution-Guided Tokenization for DNA Language Model,” arXiv:2604.08698, 2026 | Emerging preprint | Evolution-informed motif-scale tokenization | Supports a future family-aware tokenization direction |
| Brixi et al., “Genome modelling and design across all domains of life with Evo 2,” Nature, 2026, DOI: 10.1038/s41586-026-10176-5 | Published / public model | Large-scale autoregressive genome model trained on OpenGenome2 | High-end comparator, but not a native embedding model |

## Recommended Evaluation Order

### Stage 1: Public encoder screen

Run the following with one identical protocol: 100-query controlled20k DNA
benchmark, 256/128 windows, parent collapse, mean pooling, forward-only and
RC-aware inference where supported:

1. modernGENA base
2. Caduceus-PS
3. Caduceus-Ph
4. HyenaDNA small or medium-160k
5. GENA-LM base
6. DNABERT-2 reference

Report Bio Hit@1/5/10, MRR, Recall@50/100/200, query-type breakdown, query
embedding latency, lookup latency, and peak memory. First run each model on two
queries and 32 index windows to catch custom-code or tokenizer failures.

### Stage 2: Context and strand ablations

For the best two models, compare 128/64, 256/128, and 512/256 windows, together
with forward-only, explicit RC averaging, and learned RC consistency when the
model can be fine-tuned. The main hypothesis is that a bidirectional
RC-aware model should improve middle/mutated fragments without sacrificing
prefix/suffix retrieval.

### Stage 3: Domain adaptation

Continue pretraining the best public encoder on the local Ensembl cDNA window
corpus, excluding all benchmark query genes and exact sequences. Compare MLM-only
continued pretraining against MLM plus retrieval-oriented hard negatives. Hard
negatives should be k-mer-near, GC-matched sequences from different genes or
families, rather than random sequences.

### Stage 4: Frontier comparator

Only if Stage 1 does not produce a useful improvement, evaluate Evo 2 1B/7B
hidden-state embeddings on a 96 GB GPU. Treat this as an exploratory model
comparison, not the main method, and document the custom inference stack and
pooling choice.

## Decision Gates

- `+0.05 Bio Hit@10` over DNABERT-2 on a clean held-out split: continue to two
  seeds and the 500-query evaluation.
- `+0.10 Bio Hit@10` with no collapse on middle/mutated queries: promote the
  model and domain-adaptive training to the paper's main DNA ablation.
- No model reaches `0.30` Bio Hit@10 after Stage 2: stop model shopping and
  focus the paper on modality-specific candidate retrieval plus BLASTN
  verification.
- Any model that improves only on same-parent substring recovery but not on
  gene/family-held-out queries must be reported as a stress-test improvement,
  not biological retrieval competitiveness.

## Implementation Notes

The current `dnarag` backend assumes Hugging Face encoder-style models. modernGENA
and GENA-LM should fit this interface with `AutoModel` and attention-mask mean
pooling. Caduceus, HyenaDNA, and Evo 2 need small dedicated adapters because
their official repositories use custom model classes or inference stacks. The
adapter contract should remain unchanged: `embed(list[str]) -> float32[N,D]`,
L2-normalized, with model loading and pooling recorded in the result manifest.

The first practical target is therefore not the largest model. It is a clean
screen that tells us whether bidirectionality, reverse-complement equivariance,
single-nucleotide resolution, or cDNA-domain matching is responsible for any
gain over DNABERT-2.
