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
python -m pip install -e ".[test,chroma,vector,analysis]"
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

## Sequence-Token Semantics Audit

Audit whether the added OmniGene DNA/protein BPE entries are activated by the
current raw sequence path and by sampled CPT binary records:

```bash
python scripts/audit_omnigene_bio_tokens.py
```

Build the parent-level exploratory token-to-protein-to-GO extension over the 2k
SeqLit resource. The run compares intended protein BPE units, current runtime
tokens, and overlapping fixed 3-mers using BH-FDR and length-stratified GO-label
permutations:

```bash
python scripts/analyze_sequence_token_semantics.py \
  --permutations 100 \
  --output-report reports/sequence_token_semantics_pilot.md \
  --graph-output data/seq_token_semantics_pilot
```

The graph output is exploratory and generated locally. Its
`statistically_associated_with` edges are not curated motif or causal evidence.
See `docs/SEQUENCE_TOKEN_SEMANTICS_PLAN.md` for the required UniRef50 and
PROSITE/Pfam controls.

Evaluate direct token-to-protein retrieval, token-to-GO-to-protein expansion,
fixed 3-mer controls, reciprocal-rank fusion, and candidate-tail replacement on
the same 33/66 development/test split used by the Agent selector:

```bash
python scripts/eval_seq_token_graph_retrieval.py \
  --prott5-results reports/results/seq_lit_dag_function_heldout_2k_prott5_top100_full_details.json \
  --cpu-results reports/results/seq_lit_dag_function_heldout_2k_cpu_top100.json \
  --test-ids reports/results/agent_graph_selector_fused_full_p20_test_ids.txt \
  --output-report reports/seq_token_graph_retrieval.md
```

The command consumes top-100 ProtT5, BLAST, and k-mer rankings. Generate those
inputs with the same held-out documents and `--protein-k 100 --paper-k 200`
before running the ablation. All token associations are rebuilt from index-side
proteins only; the 99 held-out parents never contribute graph edges. Candidate
tail length is selected on 33 development queries, then frozen for the 66 test
queries.

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

## Cluster-Held-Out SeqLit-DAG Controls

Build the observed UniRef50-cluster holdout from the 2k SeqLit resource and the
local UniProt selected-ID mapping. The builder streams only until all 2,000
accessions are mapped, removes complete observed clusters, writes a leakage
manifest, and creates the index-side BLASTP database:

```bash
python scripts/build_seq_lit_uniref50_heldout.py \
  --source data/seq_lit_dag_swissprot_2k \
  --output data/seq_lit_dag_uniref50_heldout_2k \
  --idmapping /autodl-fs/data/open-rosalind-kb/standard/raw/uniprot/idmapping_selected.tab.gz \
  --queries 100 --seed 20260831
```

Build the identity-30 stress split. It clusters an all-vs-all BLASTP graph at
30% pair identity and 80% coverage of the shorter sequence, selects
non-singleton components, and excludes each selected component in full:

```bash
python scripts/build_seq_lit_identity_heldout.py \
  --source data/seq_lit_dag_swissprot_2k \
  --output data/seq_lit_dag_identity30_heldout_2k \
  --queries 100 --min-identity 30 --min-shorter-coverage 0.8 \
  --prioritize-non-singleton --threads 16 --seed 20260831
```

Run the CPU routes on either split. This UniRef50 command stores full top-50
protein and top-200 paper rankings; replace the split prefix with
`seq_lit_dag_identity30_heldout_2k` for the stress control:

```bash
python scripts/eval_seq_lit_heldout_cpu.py \
  --queries data/seq_lit_dag_uniref50_heldout_2k/queries.jsonl \
  --documents data/seq_lit_dag_uniref50_heldout_2k/index_documents.jsonl \
  --graph-db data/seq_lit_dag_swissprot_2k/graph.sqlite \
  --blast-db data/seq_lit_dag_uniref50_heldout_2k/blast/index \
  --protein-k 50 --paper-k 200 --seed 20260831 \
  --output reports/results/seq_lit_dag_uniref50_cpu_top50.json
```

Run ProtT5 BF16 with 128-residue windows and stride 64. `--no-reuse-index`
reproduces both index-build and warm query latency; subsequent checks can use
`--reuse-index`:

```bash
PROTT5=/path/to/Rostlab/prot_t5_xl_uniref50
CUDA_VISIBLE_DEVICES=0 TRANSFORMERS_OFFLINE=1 \
python scripts/eval_seq_lit_embeddings.py \
  --name prott5_mean --index-name prott5_mean \
  --backend prott5 --model "$PROTT5" --pooling mean --dtype bf16 --batch-size 16 \
  --documents data/seq_lit_dag_uniref50_heldout_2k/index_documents.jsonl \
  --queries data/seq_lit_dag_uniref50_heldout_2k/queries.jsonl \
  --graph-db data/seq_lit_dag_swissprot_2k/graph.sqlite \
  --vector-dir indexes/seq_lit_dag_uniref50_heldout_2k/embedding_eval \
  --protein-k 50 --paper-k 200 --window-size 128 --window-stride 64 \
  --limit 0 --no-reuse-index \
  --output reports/results/seq_lit_dag_uniref50_prott5_top50.json
```

Create the saved ProtT5+BLAST RRF ablation, then calculate paired query
bootstrap intervals:

```bash
python scripts/fuse_seq_lit_rankings.py \
  --left reports/results/seq_lit_dag_uniref50_prott5_top50.json \
  --right reports/results/seq_lit_dag_uniref50_cpu_top50.json \
  --right-method blast \
  --queries data/seq_lit_dag_uniref50_heldout_2k/queries.jsonl \
  --graph-db data/seq_lit_dag_swissprot_2k/graph.sqlite \
  --protein-k 50 --paper-k 200 --rrf-k 60 --name prott5_blast_rrf \
  --output reports/results/seq_lit_dag_uniref50_prott5_blast_rrf_top50.json
```

```bash
python scripts/analyze_seq_lit_cluster_heldout.py \
  --label 'UniRef50-cluster-held-out SeqLit-DAG Evaluation' \
  --claim-scope 'The query and its observed UniRef50 cluster are absent from the index.' \
  --cpu reports/results/seq_lit_dag_uniref50_cpu_top50.json \
  --vector reports/results/seq_lit_dag_uniref50_prott5_top50.json \
  --fusion reports/results/seq_lit_dag_uniref50_prott5_blast_rrf_top50.json \
  --output reports/results/seq_lit_dag_uniref50_cluster_analysis.json
```

Materialize the 20-paper deterministic evidence evaluation and freeze the
Graph-IDF selector on a 33/67 development/test split:

```bash
python scripts/evaluate_agent_evidence.py \
  --queries data/seq_lit_dag_uniref50_heldout_2k/queries.jsonl \
  --documents data/seq_lit_dag_uniref50_heldout_2k/index_documents.jsonl \
  --methods \
  'Random=reports/results/seq_lit_dag_uniref50_cpu_top50.json#random' \
  'k-mer=reports/results/seq_lit_dag_uniref50_cpu_top50.json#kmer_jaccard' \
  'BLAST=reports/results/seq_lit_dag_uniref50_cpu_top50.json#blast' \
  'ProtT5=reports/results/seq_lit_dag_uniref50_prott5_top50.json' \
  'ProtT5+BLAST=reports/results/seq_lit_dag_uniref50_prott5_blast_rrf_top50.json' \
  --candidate-k 50 --paper-k 20 \
  --output reports/results/agent_evidence_uniref50_p20.json \
  --markdown reports/agent_evidence_uniref50_p20.md

python scripts/evaluate_agent_qa.py \
  --input reports/results/seq_lit_dag_uniref50_prott5_top50.json --method all \
  --queries data/seq_lit_dag_uniref50_heldout_2k/queries.jsonl \
  --documents data/seq_lit_dag_uniref50_heldout_2k/index_documents.jsonl \
  --candidate-k 50 --paper-k 20 --selector rank_first --limit 0 \
  --output reports/results/agent_qa_uniref50_prott5_p20.json \
  --markdown reports/agent_qa_uniref50_prott5_p20.md \
  --dump-packs reports/results/agent_qa_uniref50_prott5_p20_packs.jsonl

python scripts/evaluate_graph_evidence_selector.py \
  --packs reports/results/agent_qa_uniref50_prott5_p20_packs.jsonl \
  --queries data/seq_lit_dag_uniref50_heldout_2k/queries.jsonl \
  --documents data/seq_lit_dag_uniref50_heldout_2k/index_documents.jsonl \
  --dev-fraction 0.33 --seed 20260831 \
  --output reports/results/agent_graph_selector_uniref50_prott5_p20.json \
  --markdown reports/agent_graph_selector_uniref50_prott5_p20.md \
  --export-packs reports/results/agent_graph_selector_uniref50_prott5_p20_packs.jsonl \
  --test-ids reports/results/agent_graph_selector_uniref50_prott5_p20_test_ids.txt
```

Repeat the three commands with the identity-30 prefixes for the stress control,
and with the RRF file for the fused selector route.

The two split manifests, retrieval intervals, 20-paper evidence-pack results,
frozen 33/67 selector analysis, and latency boundary are consolidated in
`reports/seq_lit_cluster_heldout_evaluation.md`. The UniRef50 sample is mostly
singleton clusters; identity-30 is a deliberately selected stress test. Neither
is a Pfam-clan, taxonomy, temporal, or remote-homology benchmark.

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

## R2R Application Bridge and Route Ablation

Export the authoritative SeqLit-DAG projection for an R2R v3 application. Raw
sequence documents are excluded from generic R2R text embedding by default:

```bash
python scripts/export_seq_lit_r2r.py \
  --source data/seq_lit_dag_swissprot_sample \
  --output outputs/r2r/seq_lit_dag_swissprot_sample
```

Freeze all locally executable application routes on the same 66 test IDs:

```bash
python scripts/build_agent_application_ablation.py
```

Run the Qwen3.5-9B BF16 executor on one route. Qwen3.5 uses a multimodal
processor even for text-only prompts; the script disables thinking and keeps the
biological evidence pack unchanged:

```bash
QWEN35_MODEL=/path/to/Qwen3.5-9B
CUDA_VISIBLE_DEVICES=0 TRANSFORMERS_OFFLINE=1 \
python scripts/generate_agent_qa.py \
  --model "$QWEN35_MODEL" \
  --packs reports/results/agent_application_ablation/combined_blast_vector_dag.jsonl \
  --queries data/seq_lit_dag_function_heldout_2k/queries.jsonl \
  --limit 0 --max-new-tokens 160 --evidence-mode graph_idf \
  --quantization none --dtype bfloat16 \
  --output reports/results/agent_application_ablation/qwen35_combined_blast_vector_dag_test66.json
```

Repeat with the other three frozen pack files and their matching evidence mode,
score each output with `score_generated_agent_qa.py`, then create the paired
summary:

```bash
python scripts/summarize_agent_application_ablation.py
```

The completed Qwen3.5 ablation peaks at 17.88 GiB on an RTX 4080 32 GB GPU.
The combined DAG route reaches function/literature F1 `0.094/0.088`, typed
selection F1 `1.000/1.000`, citation entailment `1.000`, and zero out-of-pack
identifiers. A same-pack Qwen2.5 run reaches `0.094/0.090`, confirming that the
evidence-route conclusion is not specific to the newer executor. These are
structured identifier tasks, not free-form biological QA.

The generic text-only R2R control requires a live, frozen R2R collection. Record
the server/SDK version, collection UUID, and embedding model label:

```bash
python scripts/eval_r2r_text_control.py \
  --base-url http://localhost:7272 \
  --collection-id <frozen-collection-uuid> \
  --embedding-label <configured-r2r-embedding> \
  --top-k 50 \
  --output reports/results/r2r_text_control.json
```

The evaluator also emits a normalized Agent pack at
`reports/results/agent_application_ablation/r2r_text_only.jsonl`. Execute it
with the same Qwen3.5 command and `--evidence-mode raw`, then score it against
the same 66 test IDs. This makes the live R2R condition an end-to-end Agent
route rather than a retrieval-only latency row.

Do not label a local proxy as an R2R result. The full integration contract is in
`docs/R2R_APPLICATION.md`.
