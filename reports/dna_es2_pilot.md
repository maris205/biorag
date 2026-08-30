# DNA-ESM2-Style Pilot

This is an initial feasibility experiment for a DNA-specific encoder with an
ESM-2-style bidirectional Transformer architecture. The model is implemented
as a 384-hidden, 8-layer BERT encoder with an overlapping 3-mer vocabulary
over `ACGTN` (about 28M parameters). It is not a claim of a finished
foundation model.

## Runs

| Run | Training data/objective | Evaluation index | Bio Hit@10 | Bio MRR | Peak GPU |
|---|---|---:|---:|---:|---:|
| DNABERT-2 reference | public DNA encoder, mean pooling | 20k windows | 0.2500 | 0.2347 | 0.67 GiB |
| DNA-ESM2 pretraining pilot | 100k unlabeled 1,000bp records, MLM + crop/RC InfoNCE, 2k steps | 20k windows | 0.2200 | 0.1364 | 0.33 GiB |
| DNA-ESM2 gene-aware pilot | 96,754 labeled windows, 649 genes, gene-pair InfoNCE, 1k steps | 20k windows | 0.1900 | 0.1551 | 0.33 GiB |
| DNA-ESM2 117M MLM | 1M unlabeled 1,000bp records, 10k steps | 20k windows | **0.2300** | **0.1687** | 0.73 GiB |
| DNA-ESM2 117M MLM, last | same checkpoint, last-token pooling | 20k windows | 0.2100 | 0.1513 | 0.73 GiB |
| DNA-ESM2 117M MLM, CLS | same checkpoint, CLS pooling | 20k windows | 0.2100 | 0.1513 | 0.73 GiB |
| BLASTN reference | alignment search | controlled20k | 0.9100 | 0.9100 | n/a |

All vector rows use the same 100-query parent-held-out transcript-fragment
benchmark, 256/128 windows, top-200 parent collapse, and shared-gene
biological matching. Exact held-out parent accessions are absent. The
benchmark is not a remote-homology evaluation.

## Interpretation

The prototype proves that a DNA-specific ESM-style encoder can be trained and
plugged into the BioRAG embedding interface on a 32GB GPU. The first pilot did
not yet improve on DNABERT-2. The 117M MLM run improves MRR over the 28M
pilot, but remains slightly below DNABERT-2; the gene-aware pilot also did not
improve, so the current evidence does not justify replacing DNABERT-2 or
BLASTN.

The negative result is useful diagnostically. Random crop/RC consistency is
not a substitute for biological retrieval supervision, while gene-level
contrastive supervision can overfit the observed gene distribution without
learning a transferable sequence metric. A stronger follow-up needs a larger
pretraining budget, family/species-stratified positives and hard negatives,
and a separately held-out gene/family benchmark. Pooling remains a secondary
factor: mean pooling is better than last/CLS for this DNA window task.

## Artifacts

- Training code: `scripts/train_dna_es2.py`
- Gene-aware fine-tuning: `scripts/finetune_dna_es2_retrieval.py`
- Model utilities: `dnarag/dna_es2.py`
- Unsupervised pilot: `runs/dna_es2_small_pilot/encoder`
- Gene-aware pilot: `runs/dna_es2_small_genecontrast`
- 117M MLM pilot: `runs/dna_es2_117m_mlm_1m_10k/encoder`
- 117M gene-aware pilot: `runs/dna_es2_117m_genecontrast`
- Fair unsupervised evaluation: `reports/results/dna_es2_small_pilot_20k_eval.json`
- Fair gene-aware evaluation: `reports/results/dna_es2_small_genecontrast_20k_eval.json`
- 117M mean evaluation: `reports/results/dna_es2_117m_mlm_1m_10k_20k_eval.json`
- 117M last/CLS evaluations: `reports/results/dna_es2_117m_mlm_1m_10k_last_20k_eval.json`, `reports/results/dna_es2_117m_mlm_1m_10k_cls_20k_eval.json`
