# DNA Vector Backend Lookup Latency

This report measures the indexed vector-search stage for the controlled DNA
collection used by the DNABERT-2 mean-pooling route. It compares the Chroma
POC backend with resident FAISS CPU and FAISS GPU indexes under the same
20,000 vectors, 768 dimensions, 10,000 sampled in-index query vectors, batch
size 128, and top-200 setting.

## Results

| Backend | Indexed vectors | Top-k | Queries | Lookup ms/query | Queries/s | Query embedding | GPU |
|---|---:|---:|---:|---:|---:|---|---|
| Chroma persistent collection | 20,000 | 200 | 10,000 | 2.2972 | 435 | excluded | no |
| FAISS `IndexFlatIP` CPU | 20,000 | 200 | 10,000 | 1.9210 | 521 | excluded | no |
| FAISS `IndexFlatIP` GPU | 20,000 | 200 | 10,000 | **0.003868** | **258,502** | excluded | RTX 4080 SUPER |

The resident FAISS GPU lookup is approximately 496x faster than the measured
FAISS CPU lookup and approximately 594x faster than the Chroma lookup in this
small in-memory benchmark. The absolute values should be treated as backend
microbenchmarks rather than service-level latency guarantees: host-device
transfer, RPC overhead, batching policy, index construction, and concurrent
load are not included.

## Interpretation

The result supports a practical two-stage DNA route: DNABERT-2 mean pooling
generates a dense shortlist, and BLASTN verifies the selected candidates. The
current Chroma implementation is suitable for the CRUD-oriented POC and
reproducible local experiments. A resident FAISS index is the appropriate
performance backend for an instant candidate layer once query embedding is
available.

This benchmark does not show that the complete vector-plus-BLASTN route is
faster than full-database BLASTN. It measures only vector lookup and uses
queries sampled from resident vectors, so it is not a biological retrieval
evaluation. Query embedding, candidate extraction, BLASTN, graph expansion,
and answer generation must be measured separately for an end-to-end claim.

## Reproduction

Build the measurement from the controlled20k DNABERT-2 Chroma collection:

```bash
HF_HOME=/root/autodl-tmp/huggingface \
/root/autodl-tmp/dnarag/.venv-dna4/bin/python \
scripts/benchmark_chroma_lookup.py \
  --config configs/heldout_dna_parent_frag_100_controlled20k_dnabert2_mean256.yaml \
  --target dna_sequence_window --limit 20000 --queries 10000 --top-k 200 \
  --batch-size 128 --warmup 128 --seed 13 \
  --output reports/results/dna_dnabert2_mean256_chroma_lookup10000.json
```

Use the same arguments with `scripts/benchmark_faiss_lookup.py`, adding
`--gpu` for the GPU condition and selecting separate JSON output paths.

## Artifacts

- `reports/results/dna_dnabert2_mean256_chroma_lookup10000.json`
- `reports/results/dna_dnabert2_mean256_faiss_cpu10000.json`
- `reports/results/dna_dnabert2_mean256_faiss_gpu10000.json`
- `scripts/benchmark_chroma_lookup.py`
- `scripts/benchmark_faiss_lookup.py`
