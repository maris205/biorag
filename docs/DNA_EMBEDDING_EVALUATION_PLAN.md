# DNA Embedding Evaluation Plan

## Objective

The existing DNA result is substantially weaker than the protein result. This
is treated as a representation and protocol question, not as evidence that
dense DNA retrieval is intrinsically unsuitable. The next experiment compares
DNA-specific encoders, pooling rules, sequence windows, and strand handling on
one fixed held-out parent-fragment benchmark.

The benchmark is `benchmarks/dna_parent_frag_100.jsonl` with the controlled
20k index at
`data/heldout/dna_parent_frag_100_controlled20k_index.fasta`. Exact held-out
transcript accessions are excluded; same-gene indexed transcripts are retained
for the biological-match metric. BLASTN remains the alignment reference and is
not expected to be replaced by an embedding route.

## Primary Matrix

| Factor | Values | Purpose |
|---|---|---|
| Encoder | DNABERT-S, DNABERT-2, Nucleotide Transformer v2 500M, OmniGene-4-CPT 4-bit | Separate DNA-specialized and unified backbones |
| Pooling | mean, last, CLS/BOS where supported | Test whether token pooling is the bottleneck |
| Window | 128/64 and 256/128 | Check short-transcript and context-length effects |
| Strand | forward only, forward + reverse-complement mean | Remove orientation sensitivity for cDNA/genomic inputs |
| Scale | controlled20k first, then 100k/full if useful | Avoid expensive runs before the protocol is validated |

The first GPU job should run the following stop/go subset:

1. DNABERT-S mean, 128/64, forward only
2. DNABERT-S mean, 128/64, reverse-complement mean
3. DNABERT-2 mean and last, 128/64
4. Nucleotide Transformer v2 mean and last, 128/64, reproducing the current baseline
5. Quantized OmniGene-4-CPT mean and last, 128/64, as the deployable unified-backbone control

If a model fails to load, record the exact package versions and failure in the
run manifest. Do not interpret custom-code compatibility failures as negative
scientific results.

## Runner

The unified runner is:

```bash
python scripts/eval_dna_embedding_matrix.py \
  --backend dnabert_s \
  --model zhihan1996/DNABERT-S \
  --pooling mean \
  --dtype bf16 \
  --orientation rc_mean \
  --output reports/results/dna_dnabert_s_mean_rc128.json
```

For a model-loading smoke test, add `--limit 2 --index-record-limit 1
--index-window-limit 32 --top-k 20`. The index limits are only for smoke tests
or speed probes and must be left at zero for a full evaluation.

Replace `--backend`, `--model`, `--pooling`, and `--orientation` for each
condition. The runner reports exact parent Hit@1/5/10, gene-level biological
Hit@1/5/10, MRR, query embedding latency, lookup latency, end-to-end warm
latency, GPU name, and peak allocated memory. Query embedding is included in
end-to-end latency; lookup-only is reported separately.

For the quantized OmniGene control, use:

```bash
python scripts/eval_dna_embedding_matrix.py \
  --backend transformers4bit \
  --model dnagpt/OmniGene-4-CPT-v2-4bit \
  --pooling mean \
  --dtype bf16 \
  --orientation rc_mean \
  --batch-size 1 \
  --output reports/results/dna_omnigene_4bit_mean_rc128.json
```

## Interpretation Rules

- BLASTN is the alignment-grounded reference, not a competitor that the vector
  route must replace.
- The primary DNA claim is comparative: which representation and pooling rule
  gives the best candidate layer for downstream verification?
- A gain from reverse-complement averaging is a useful engineering result, but
  is not a new biological model.
- A gain only on in-index or substring stress tests must not be described as
  held-out homology competitiveness.
- Results must be reported by query type (`prefix`, `suffix`, `middle`,
  `exact_fragment`, `mutated`) because cDNA boundary and mutation behavior may
  differ.

## Matrix Status

The initial stop/go matrix is complete for DNABERT-S, DNABERT-2, and the
quantized OmniGene control on the fixed 100-query, controlled20k protocol.
DNABERT-2 mean with 256/128 windows is the selected primary DNA dense encoder
(`Bio Hit@10 = 0.25`, `Bio MRR = 0.2347`); 128/64 remains a controlled window
ablation (`0.17/0.1481`), and DNABERT-2 last is retained as a negative pooling
ablation (`0.02`). The
DNABERT-2 runs use FP32 in the compatibility environment because the official
custom MosaicBERT implementation is most reproducible there.

## Stop/Go Criteria

| Outcome | Action |
|---|---|
| DNA dense Bio Hit@10 improves materially over OmniGene and is stable across query types | Add the best DNA encoder/strand setting to the main ablation table |
| Dense retrieval remains far below BLASTN but RC helps | Keep DNA as a limitation plus route-design result; use vector coarse retrieval and BLASTN verification |
| No public encoder improves and pooling is unstable | Stop scaling this matrix; focus on hybrid candidate generation and report the negative result honestly |
| DNABERT-S/2 cannot load under current Transformers | Pin a Transformers 4.x environment before drawing conclusions |

## Reproducibility

Each result JSON should be accompanied by the command, commit, model revision,
Transformers/PyTorch versions, proxy setting used for download, and a leakage
report. The 100-query benchmark is intentionally small for iteration; a later
submission run should add more held-out parents and confidence intervals.
