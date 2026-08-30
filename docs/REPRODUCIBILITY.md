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

## DNA DNABERT-2 Vector-to-BLAST Route

Build the 20k-window DNA Chroma collection with DNABERT-2 mean pooling and
256/128 windows:

```bash
HF_HUB_OFFLINE=1 HF_HOME=/root/autodl-tmp/huggingface \
DNARAG_EMBED_MAX_LENGTH=512 CUDA_VISIBLE_DEVICES=0 \
/root/autodl-tmp/dnarag/.venv-dna4/bin/python -m dnarag.cli \
  --config configs/heldout_dna_parent_frag_100_controlled20k_dnabert2_mean256.yaml \
  build-vector --targets dna_sequence_window --backend dnabert2 \
  --model /root/autodl-tmp/huggingface/models--zhihan1996--DNABERT-2-117M/snapshots/7bce263b15377fc15361f52cfab88f8b586abda0 \
  --pooling mean --dtype fp32 --batch-size 64 --limit 20000 --store chroma \
  --sequence-window-size 256 --sequence-stride 128
```

Run vector shortlist plus candidate-subset BLASTN:

```bash
HF_HUB_OFFLINE=1 HF_HOME=/root/autodl-tmp/huggingface \
DNARAG_EMBED_MAX_LENGTH=512 CUDA_VISIBLE_DEVICES=0 \
/root/autodl-tmp/dnarag/.venv-dna4/bin/python \
  scripts/evaluate_vector_blast_rerank.py \
  --config configs/heldout_dna_parent_frag_100_controlled20k_dnabert2_mean256.yaml \
  --benchmark benchmarks/dna_parent_frag_100.jsonl --candidate-limit 50 \
  --final-limit 10 --blast-top-k 50 --append-unaligned --progress \
  --output reports/results/dna_dnabert2_mean256_candidate_blast50.json \
  --markdown reports/results/dna_dnabert2_mean256_candidate_blast50.md
```

The 50/100/200 candidate budget comparison is in
`reports/dna_candidate_blast_budget_sweep.md`. The current Chroma result is a
route and evidence validation, not a vector-serving speed claim. The
controlled20k FAISS resident-index measurements below quantify the lookup
backend direction without making an end-to-end serving claim.

## DNA Vector Backend Lookup Benchmark

The controlled20k DNA collection can also be used to compare the POC Chroma
backend with resident FAISS CPU/GPU lookup. All three commands use 20,000
vectors, 10,000 sampled in-index query vectors, batch size 128, and top-200.
The benchmark excludes query embedding and all downstream BLAST/graph/LLM
work.

Chroma:

```bash
HF_HOME=/root/autodl-tmp/huggingface \
/root/autodl-tmp/dnarag/.venv-dna4/bin/python \
scripts/benchmark_chroma_lookup.py \
  --config configs/heldout_dna_parent_frag_100_controlled20k_dnabert2_mean256.yaml \
  --target dna_sequence_window --limit 20000 --queries 10000 --top-k 200 \
  --batch-size 128 --warmup 128 --seed 13 \
  --output reports/results/dna_dnabert2_mean256_chroma_lookup10000.json
```

FAISS CPU:

```bash
HF_HOME=/root/autodl-tmp/huggingface \
/root/autodl-tmp/dnarag/.venv-dna4/bin/python \
scripts/benchmark_faiss_lookup.py \
  --config configs/heldout_dna_parent_frag_100_controlled20k_dnabert2_mean256.yaml \
  --target dna_sequence_window --limit 20000 --queries 10000 --top-k 200 \
  --batch-size 128 --warmup 128 \
  --output reports/results/dna_dnabert2_mean256_faiss_cpu10000.json
```

FAISS GPU:

```bash
CUDA_VISIBLE_DEVICES=0 HF_HOME=/root/autodl-tmp/huggingface \
/root/autodl-tmp/dnarag/.venv-dna4/bin/python \
scripts/benchmark_faiss_lookup.py \
  --config configs/heldout_dna_parent_frag_100_controlled20k_dnabert2_mean256.yaml \
  --target dna_sequence_window --limit 20000 --queries 10000 --top-k 200 \
  --batch-size 128 --warmup 128 --gpu \
  --output reports/results/dna_dnabert2_mean256_faiss_gpu10000.json
```

The current measurements are Chroma `2.2972 ms/query` (435 q/s), FAISS CPU
`1.9210 ms/query` (521 q/s), and FAISS GPU `0.003868 ms/query` (258,502 q/s)
on an RTX 4080 SUPER. These are lookup-only microbenchmarks, not end-to-end
instant latency or evidence that candidate-BLAST is faster than full BLASTN.
The consolidated interpretation is in
`reports/dna_vector_backend_latency.md`.

## Held-Out Agent Evidence Evaluation

The deterministic evidence evaluation converts held-out sequence retrieval
results into budget-matched `sequence -> GO/GOA -> paper` packs. It measures
candidate coverage, GO bridging, PMID support, and strict typed paths. CPU
methods are selected from the shared result file with a `#method` suffix; all
dense inputs below store the full top-50 candidate and top-200 paper rankings:

```bash
python scripts/evaluate_agent_evidence.py \
  --methods \
  'Random=reports/results/seq_lit_dag_function_heldout_2k_cpu_top50.json#random' \
  'k-mer=reports/results/seq_lit_dag_function_heldout_2k_cpu_top50.json#kmer_jaccard' \
  'BLAST=reports/results/seq_lit_dag_function_heldout_2k_cpu_top50.json#blast' \
  'ESM-2=reports/results/seq_lit_dag_function_heldout_2k_esm2_top50_full_details.json' \
  'ProtT5=reports/results/seq_lit_dag_function_heldout_2k_prott5_top50_full_details.json' \
  'ProtT5+BLAST=reports/results/seq_lit_dag_function_heldout_2k_prott5_blast_rrf_top50_full_details.json' \
  --candidate-k 50 --paper-k 20 \
  --output reports/results/agent_evidence_eval_final.json \
  --markdown reports/agent_evidence_eval_final.md
```

Materialize the ProtT5 top-50/top-20 typed packs, then tune Graph-IDF only on a
deterministic 33-query development split. The second command exports the frozen
66-query test packs and records the exact test IDs:

```bash
python scripts/evaluate_agent_qa.py \
  --input reports/results/seq_lit_dag_function_heldout_2k_prott5_top50_full_details.json \
  --method all --candidate-k 50 --paper-k 20 --selector rank_first --limit 0 \
  --output reports/results/agent_qa_prott5_full_p20.json \
  --markdown reports/agent_qa_prott5_full_p20.md \
  --dump-packs reports/results/agent_qa_prott5_full_p20_packs.jsonl

python scripts/evaluate_graph_evidence_selector.py \
  --packs reports/results/agent_qa_prott5_full_p20_packs.jsonl \
  --queries data/seq_lit_dag_function_heldout_2k/queries.jsonl \
  --documents data/seq_lit_dag_function_heldout_2k/index_documents.jsonl \
  --dev-fraction 0.3333333333 --seed 20260830 \
  --output reports/results/agent_graph_selector_prott5_full_p20.json \
  --markdown reports/agent_graph_selector_prott5_full_p20.md \
  --export-packs reports/results/agent_graph_selector_prott5_full_p20_packs.jsonl \
  --test-ids reports/results/agent_graph_selector_prott5_full_p20_test_ids.txt
```

The selector uses candidate rank, corpus GO document frequency, and typed
GO-to-PMID edges. Query gold labels are used for development scoring but are not
available to the frozen selector at inference time.

## Generated Agent QA Evaluation

Run Qwen2.5-7B-Instruct BF16 on only the frozen test IDs. The prompt masks each
held-out accession and requires literal typed citations. Set `QWEN_MODEL` to a
local model snapshot:

```bash
QWEN_MODEL=/path/to/Qwen2.5-7B-Instruct
CUDA_VISIBLE_DEVICES=0 TRANSFORMERS_OFFLINE=1 \
python scripts/generate_agent_qa.py \
  --model "$QWEN_MODEL" \
  --packs reports/results/agent_graph_selector_prott5_full_p20_packs.jsonl \
  --queries data/seq_lit_dag_function_heldout_2k/queries.jsonl \
  --query-ids-file reports/results/agent_graph_selector_prott5_full_p20_test_ids.txt \
  --limit 0 --max-new-tokens 96 --evidence-mode graph_idf \
  --quantization none --dtype bfloat16 \
  --output reports/results/agent_qa_generated_qwen25_7b_graph_masked_test66.json

python scripts/score_generated_agent_qa.py \
  --input reports/results/agent_qa_generated_qwen25_7b_graph_masked_test66.json \
  --packs reports/results/agent_graph_selector_prott5_full_p20_packs.jsonl \
  --queries data/seq_lit_dag_function_heldout_2k/queries.jsonl \
  --output reports/results/agent_qa_generated_qwen25_7b_graph_masked_test66_score.json \
  --markdown reports/agent_qa_generated_qwen25_7b_graph_masked_test66_score.md
```

The scorer separately reports gold-label F1, evidence-selection F1, citation
validity, typed-edge entailment, out-of-pack identifier hallucination, strict
format compliance, and mechanism abstention. The full BF16 run peaks at
14.35 GiB, so a 32 GB GPU is sufficient. Automatic correctness is limited to
structured GO/PMID identifiers; narrative biomedical claims still require
expert evaluation.
