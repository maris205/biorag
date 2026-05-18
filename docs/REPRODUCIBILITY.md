# Reproducibility

Code repository: <https://github.com/maris205/biorag>

This repository contains the BioRAG-DRAG implementation, experiment scripts,
benchmark task definitions, paper source, and compact result summaries. Large
local inputs and generated artifacts are intentionally not versioned:

- Open-Rosalind Standard SQLite/BLAST bundle
- Swiss-Prot and Ensembl cDNA FASTA/BLAST databases
- Hugging Face model checkpoints
- Chroma/FAISS vector indexes
- detailed per-query JSON traces

The tracked Markdown reports under `reports/` provide the reported summary
metrics. The ignored JSON outputs can be regenerated with the commands below.

## Environment

Install the package in editable mode:

```bash
python -m pip install -e ".[test,chroma,vector]"
```

The smoke tests do not require model downloads:

```bash
pytest tests/test_vector_hashing.py tests/test_hybrid_routing.py tests/test_evaluation.py
```

For paper-scale dense retrieval, use a CUDA GPU with enough memory for the
chosen encoder. The reported ProtT5 and OmniGene BF16 runs were executed on an
RTX PRO 6000 96GB machine.

## Local Data Layout

The default configs expect the Open-Rosalind Standard bundle at:

```text
/autodl-fs/data/open-rosalind-kb/standard
```

Held-out benchmark FASTA/BLAST files used for the scale-frontier experiments
are generated under:

```text
data/heldout/
```

Generated vector stores live under:

```text
indexes/
```

These directories are ignored by Git because they are large and machine-local.

## Core Commands

Build a lightweight development vector index without downloading a neural
encoder:

```bash
python -m dnarag.cli build-vector \
  --config configs/standard.yaml \
  --backend hashing \
  --targets text \
  --limit 1000
```

Run the core search tests:

```bash
python -m dnarag.cli eval-search \
  --config configs/standard.yaml \
  --benchmark benchmarks/basic_search.jsonl \
  --conditions classical,vector,drag,hybrid \
  --limit 10 \
  --output reports/basic_search_eval.json
```

Build the controlled300k ProtT5 protein-window index used in the scale-frontier
table:

```bash
env HF_HOME=/root/autodl-tmp/huggingface \
    HUGGINGFACE_HUB_CACHE=/root/autodl-tmp/huggingface \
    HF_HUB_DISABLE_XET=1 \
    DNARAG_USE_LOCAL_TRANSFORMERS_CACHE=1 \
    DNARAG_VECTOR_PROGRESS_EVERY=5000 \
python -m dnarag.cli build-vector \
  --config configs/heldout_parent_frag_500_controlled300k_prott5_mean.yaml \
  --targets protein_sequence_window \
  --backend prott5 \
  --model Rostlab/prot_t5_xl_uniref50 \
  --pooling mean \
  --dtype bf16 \
  --batch-size 16 \
  --limit 0 \
  --store chroma \
  --sequence-window-size 128 \
  --sequence-stride 64
```

Evaluate controlled300k vector-only retrieval:

```bash
env HF_HOME=/root/autodl-tmp/huggingface \
    HUGGINGFACE_HUB_CACHE=/root/autodl-tmp/huggingface \
    HF_HUB_DISABLE_XET=1 \
    DNARAG_USE_LOCAL_TRANSFORMERS_CACHE=1 \
python -m dnarag.cli eval-search \
  --config configs/heldout_parent_frag_500_controlled300k_prott5_mean.yaml \
  --benchmark benchmarks/protein_parent_frag_500_window_target.jsonl \
  --conditions vector \
  --limit 200 \
  --output reports/protein_parent_frag_500_controlled300k_prott5_mean_window_vector_top200_eval.json \
  --summary-only \
  --progress
```

Build the parse-id BLAST database required by candidate-BLAST:

```bash
makeblastdb \
  -in data/heldout/protein_parent_frag_500_controlled300k_index.fasta \
  -dbtype prot \
  -out data/heldout/blast/protein_parent_frag_500_controlled300k_index_parseids \
  -parse_seqids
```

Evaluate controlled300k vector-to-candidate-BLAST reranking:

```bash
env HF_HOME=/root/autodl-tmp/huggingface \
    HUGGINGFACE_HUB_CACHE=/root/autodl-tmp/huggingface \
    HF_HUB_DISABLE_XET=1 \
    DNARAG_USE_LOCAL_TRANSFORMERS_CACHE=1 \
python scripts/evaluate_vector_blast_rerank.py \
  --config configs/heldout_parent_frag_500_controlled300k_prott5_mean_parseids.yaml \
  --benchmark benchmarks/protein_parent_frag_500_window_target.jsonl \
  --candidate-limit 200 \
  --final-limit 10 \
  --blast-top-k 200 \
  --output reports/protein_parent_frag_500_controlled300k_prott5_mean_candidate_blast_n200_parseids_eval.json \
  --markdown reports/protein_parent_frag_500_controlled300k_prott5_mean_candidate_blast_n200_parseids.md \
  --progress
```

Regenerate the compact scale-frontier summary:

```bash
python scripts/summarize_scale_frontier.py
```

## Reported Controlled300k Reference Values

The current scale-frontier summary reports:

| Route | Bio@10 | MRR | Recall@200 | Latency |
| --- | ---: | ---: | ---: | ---: |
| BLAST | 0.8140 | 0.7613 | n/a | 796.5 ms |
| ProtT5 vector | 0.6760 | 0.5788 | 0.7740 | 812.5 ms |
| Vector-to-candidate-BLAST | 0.7320 | 0.6835 | 0.7740 | 1020.6 ms |

Candidate-BLAST improves the dense retrieval ranking, but the current Chroma POC
does not establish a speed advantage over full BLAST. The candidate-BLAST-only
portion is much smaller, so optimized vector serving is the next systems step.
