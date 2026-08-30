# DNA Retrieval Upgrade Plan

## Decision

Protein embedding is frozen for now: use ProtT5-XL-UniRef50 mean pooling for
protein-only retrieval, ESM-2 mean for the lightweight option, and BLASTP for
alignment verification. The next research effort is DNA representation
learning, because DNA is the largest quality gap in the current BioRAG system.

The objective is not to replace BLASTN. It is to improve the DNA vector route
enough to provide a useful candidate layer and sequence-conditioned context for
the RAG/DRAG pipeline. The candidate model screen is expanded in
`reports/dna_model_landscape_20260829.md`, with modernGENA, Caduceus, and
HyenaDNA as the first priorities and Evo 2 deferred to a high-resource
comparison.

## Current Baseline

On the fixed 100-query, controlled20k DNA parent-fragment control:

| Method | Bio Hit@10 | Bio MRR |
|---|---:|---:|
| BLASTN | 0.9100 | 0.9100 |
| DNABERT-2 mean, 256/128 | **0.2500** | **0.2347** |
| DNABERT-2 mean, 128/64 | 0.1700 | 0.1481 |
| DNA-ESM2-style 117M MLM mean | 0.2300 | 0.1687 |
| OmniGene-4-CPT 4-bit mean | 0.0900 | 0.0688 |

### Adaptation pilots

| Method | Bio Hit@10 | Bio MRR | Interpretation |
|---|---:|---:|---|
| DNABERT-2 + cDNA MLM, 1k steps | 0.2300 | 0.2109 | Regresses; do not promote |
| DNABERT-2 + GC/5-mer hard-negative retrieval, 1k steps | 0.2500 | **0.2465** | Best exploratory checkpoint; ranking improves but recall does not |
| Same hard-negative run continued to 4k steps | 0.2300 | 0.2139 | Over-training/overfitting signal |

The previous gene-level contrastive fine-tuning reached only 0.1900/0.1445.
This is evidence against the current random same-gene contrastive setup, not
against retrieval-oriented DNA training in general.

The first DNABERT-2 adaptation pilots support early stopping: hard-negative
training improved MRR at 1k steps but did not improve Hit@10, while extending
the same run to 4k steps reduced both metrics. These checkpoints remain
exploratory evidence, not a replacement for the public baseline.

## Why the Next Run Must Change

1. The public DNA corpus has sequence text but no reliable biological labels, so
   random same-gene supervision cannot be applied to it directly.
2. The current benchmark excludes query parents but retains related
   same-gene/indexed transcript material. It is useful for a parent-fragment
   control, but not a strict gene- or family-held-out homology benchmark.
3. The current DNA-ESM2 prototype uses a small 3-mer vocabulary and MLM-first
   training. Its 117M result is close to DNABERT-2, so the highest-return change
   is task-aligned fine-tuning and hard-negative construction, not immediate
   parameter scaling.

## Experiment Blocks

### B1. Benchmark and Leakage Audit

- Create three fixed splits: current parent-held-out, strict gene-held-out, and
  family-held-out where reliable family labels exist.
- Report exact sequence overlap, parent overlap, gene overlap, family overlap,
  query length, query type, GC content, and repeat/low-complexity statistics.
- Increase the main query set from 100 to at least 500 when the split is stable.
- Keep BLASTN as the alignment reference, but distinguish labels derived from
  curated annotations from labels derived from BLAST itself.
- Priority: MUST-RUN before interpreting any training gain.

### B2. Public DNA Encoder Screen

- Add modernGENA base, Caduceus-PS/Ph, HyenaDNA small/medium, and GENA-LM to
  the fixed evaluation protocol.
- Keep DNABERT-2 as the primary reference and use the same mean pooling,
  windowing, parent collapse, and query-type breakdown.
- Record custom dependency or model-loading failures separately from negative
  retrieval results.
- Priority: MUST-RUN.

### B3. Domain-Adaptive MLM

- Start from DNABERT-2 rather than the scratch-trained DNA-ESM2 prototype.
- Continue MLM on Ensembl cDNA/transcript windows matching the target
  distribution, while excluding all benchmark parent genes and exact windows.
- Use 256/128 windows as the primary setting, with 128/64 as an ablation.
- Compare 5k, 20k, and 50k update budgets with one fixed seed initially.
- Priority: MUST-RUN.

### B4. Retrieval-Oriented Fine-Tuning

- Build positive pairs from non-identical views of the same transcript or gene
  only in the training split; never use query genes.
- Generate hard negatives using k-mer nearest neighbors and same-GC sequences
  from different genes/families.
- Use symmetric contrastive or margin-ranking loss with in-batch negatives;
  retain MLM as a regularizer to avoid destroying nucleotide syntax.
- Compare: MLM only, MLM + random contrastive, and MLM + hard-negative
  contrastive. Reverse-complement augmentation is an ablation, not an assumed
  improvement because the previous RC average did not help.
- Priority: MUST-RUN if B1/B2 pass leakage checks.

### B5. Evaluation and Route Decision

- Evaluate mean, last, and CLS/BOS pooling only for the selected checkpoint.
- Report Bio Hit@1/5/10, MRR, Recall@50/100/200, exact parent metrics, and
  query-type breakdown.
- Report query embedding, lookup, and warm end-to-end latency separately.
- Success gate: at least +0.05 Bio Hit@10 over DNABERT-2 mean on a clean held-out
  split, with no material collapse on mutated or middle fragments.
- Strong gate: at least +0.10 Bio Hit@10 and stable improvement across two seeds.
- Failure gate: less than +0.05 after B2/B3. Freeze DNA dense modeling and use
  DNABERT-2 mean as the vector shortlist followed by BLASTN verification.

## Execution Order

| Stage | Action | GPU need | Decision |
|---|---|---:|---|
| 0 | Freeze protein route and archive current baselines | none | ProtT5 mean remains default |
| 1 | Build split/leakage audit and 500-query evaluation set | none/low | Do not train if overlap is unclear |
| 2 | Public DNA encoder screen | 32/96 GB | Continue with the best model only |
| 3 | DNABERT-2 or selected-model cDNA domain-adaptive MLM pilot | 32 GB | Continue only if validation loss and retrieval do not regress |
| 4 | Hard-negative retrieval fine-tuning | 32 GB | Keep only if Bio Hit@10 improves by at least 0.05 |
| 5 | Two-seed confirmation and query-type analysis | 32 GB | Select final DNA encoder or stop |
| 6 | DNA vector shortlist + BLASTN | 32 GB or CPU | Freeze route before review |

## Resource Estimate

- B1 audit and split generation: CPU, minutes to a few hours depending on
  annotation joins.
- B2 one 117M DNABERT-2 continued-MLM pilot: approximately 1--4 GPU hours on
  a 32 GB card, depending on corpus size and sequence length.
- B3 hard-negative fine-tuning: approximately 1--3 GPU hours per condition.
- B4 two-seed confirmation: approximately 2--6 GPU hours.

The 32 GB card is sufficient for modernGENA base, Caduceus, HyenaDNA pilot
models, and all fine-tuning stages. A 96 GB card should be used for
modernGENA-large, HyenaDNA long-context variants, and the Evo 2 1B/7B
exploratory comparison. The next high-quality screen should therefore use the
96 GB card when available, but does not require multi-GPU training.

## Research Position

If the upgrade succeeds, the paper can claim a retrieval-oriented DNA candidate
layer that is better aligned with cDNA search while still using BLASTN for
verification. If it fails, the negative result remains useful: protein and DNA
partitions require different encoders, and the robust BioRAG design is
modality-specific vector retrieval plus classical sequence verification. In
both cases, the next major paper value should come from the sequence-to-
function-to-literature DAG and agent evidence evaluation, not indefinite DNA
model scaling.
