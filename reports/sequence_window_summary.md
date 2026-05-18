# Sequence-Window Vector POC

Date: 2026-05-15

Primary paper-scale model: `dnagpt/OmniGene-4-CPT-v2-merged` BF16 on the RTX
PRO 6000 96 GB machine.

The earlier `dnagpt/OmniGene-4-CPT-v2-4bit` result is kept as a low-memory POC,
not the primary paper result.

## BF16 100k Window Run

Model: `dnagpt/OmniGene-4-CPT-v2-merged` BF16.

GPU: RTX PRO 6000 Blackwell 96 GB.

Collections:

- `protein_sequence_window`: 100,000 windows.
- `dna_sequence_window`: 100,000 windows.
- Window size 128, stride 64, batch size 16.
- Chroma persist dir after build: about 21 GB.

Build timing:

- protein windows: 2,536.6 seconds for 100,000 windows.
- DNA/cDNA windows: 2,240.9 seconds for 100,000 windows.
- observed VRAM during build: about 58.5 GB / 96 GB.
- no CPU offload warning observed.

Evaluation:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DNARAG_EMBED_MAX_LENGTH=512 \
python -m dnarag.cli eval-search \
  --config configs/standard.yaml \
  --benchmark benchmarks/sequence_search.jsonl \
  --conditions blast,vector \
  --limit 10 \
  --output reports/sequence_window_bf16_100k_eval.json \
  --summary-only \
  --progress
```

Result:

| Condition | Hit@1 | Hit@5 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `blast` | 0.7500 | 1.0000 | 1.0000 | 0.8750 | 812.242 |
| `vector` | 0.7500 | 0.7500 | 0.7500 | 0.7500 | 5236.183 |
| `hybrid_gated` | 0.7500 | 1.0000 | 1.0000 | 0.8750 | 5808.516 |

Top-100 vector diagnosis:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DNARAG_EMBED_MAX_LENGTH=512 \
python -m dnarag.cli eval-search \
  --config configs/standard.yaml \
  --benchmark benchmarks/sequence_search.jsonl \
  --conditions vector \
  --limit 100 \
  --output reports/sequence_window_bf16_100k_vector_top100_eval.json \
  --summary-only \
  --progress
```

- `protein_q6gzx4_fragment`, `protein_q6gzx3_fragment`, and
  `dna_enst00632585_fragment` are vector rank 1.
- `dna_enst00622028_fragment` is vector rank 30 in the top-100 run.
- This is an immunoglobulin-heavy cDNA region with many close transcript
  neighborhoods; BLAST keeps the exact transcript at rank 1 while vector search
  surfaces a broader representation neighborhood.

Interpretation:

- Scaling from 10k to 100k makes the sequence-vector task more realistic and
  exposes near-neighbor interference, especially for repetitive or highly
  similar immune-gene regions.
- Vector-only is still useful as the unified sequence view, but it should not be
  presented as a BLAST replacement.
- Route-gated Hybrid BioRAG is the practical condition: it keeps BLAST-level
  Hit@10/MRR for pure sequence queries and still attaches vector neighborhoods
  for RAG/DRAG context.
- Vector latency here is end-to-end and includes cold model load on the first
  vector query. FAISS/Milvus lookup benchmarks should measure precomputed-vector
  search separately from query embedding.

## BF16 100k / 100-Query Generated Benchmark

Benchmark: `benchmarks/sequence_search_100.jsonl`.

Generation recipe:

- sampled from existing 100k Chroma window collections with seed `20260515`.
- 50 protein tasks and 50 DNA/cDNA tasks.
- 20 tasks each for `exact_window`, `prefix_96`, `suffix_96`, `middle_short`,
  and `mutated_96` query types.
- strict expected target is the sampled parent record ID. This is a strict-ID
  sanity benchmark, not a biological-equivalence benchmark; DNA/cDNA repeated
  transcripts can make exact parent recovery harsh even when a close biological
  sequence is retrieved.

Run:

```bash
python scripts/make_sequence_window_benchmark.py \
  --config configs/standard.yaml \
  --output benchmarks/sequence_search_100.jsonl \
  --per-modality 50 \
  --seed 20260515

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DNARAG_EMBED_MAX_LENGTH=512 \
python -m dnarag.cli eval-search \
  --config configs/standard.yaml \
  --benchmark benchmarks/sequence_search_100.jsonl \
  --conditions blast,vector,hybrid_gated \
  --limit 10 \
  --output reports/sequence_window_bf16_100k_100query_eval.json \
  --summary-only \
  --progress
```

Overall result:

| Condition | Hit@1 | Hit@5 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `blast` | 0.5100 | 0.6600 | 0.7800 | 0.5882 | 730.180 |
| `vector` | 0.4200 | 0.5300 | 0.5700 | 0.4703 | 434.565 |
| `hybrid_gated` | 0.5100 | 0.6600 | 0.7800 | 0.5954 | 1019.733 |

Retry with seed `20260516`:

| Condition | Hit@1 | Hit@5 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `blast` | 0.4700 | 0.5900 | 0.7300 | 0.5425 | 739.838 |
| `vector` | 0.3500 | 0.4800 | 0.5000 | 0.4063 | 435.237 |
| `hybrid_gated` | 0.4700 | 0.5900 | 0.7300 | 0.5516 | 1028.810 |

Mean over the two 100-query seeds:

| Condition | Hit@1 | Hit@5 | Hit@10 | MRR |
| --- | ---: | ---: | ---: | ---: |
| `blast` | 0.4900 | 0.6250 | 0.7550 | 0.5654 |
| `vector` | 0.3850 | 0.5050 | 0.5350 | 0.4383 |
| `hybrid_gated` | 0.4900 | 0.6250 | 0.7550 | 0.5735 |

Mean over the two seeds, split by modality:

| Condition | Modality | Hit@1 | Hit@5 | Hit@10 | MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| `blast` | protein | 0.8800 | 0.9400 | 0.9600 | 0.9110 |
| `blast` | DNA/cDNA | 0.1000 | 0.3100 | 0.5500 | 0.2197 |
| `vector` | protein | 0.3900 | 0.5200 | 0.5500 | 0.4486 |
| `vector` | DNA/cDNA | 0.3800 | 0.4900 | 0.5200 | 0.4280 |
| `hybrid_gated` | protein | 0.8800 | 0.9400 | 0.9600 | 0.9121 |
| `hybrid_gated` | DNA/cDNA | 0.1000 | 0.3100 | 0.5500 | 0.2349 |

Split outputs:

- `reports/sequence_window_bf16_100k_100query_split_summary.md`
- `reports/sequence_window_bf16_100k_100query_split_summary.json`
- `benchmarks/sequence_search_100_protein_sequence_seed20260515.jsonl`
- `benchmarks/sequence_search_100_dna_sequence_seed20260515.jsonl`
- `benchmarks/sequence_search_100_protein_sequence_seed20260516.jsonl`
- `benchmarks/sequence_search_100_dna_sequence_seed20260516.jsonl`

## Experimental Vector Rerank

The default vector route is raw cosine similarity followed by parent-record
deduplication. An experimental rerank can be enabled with:

```bash
DNARAG_VECTOR_SEQUENCE_RERANK=1 \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DNARAG_EMBED_MAX_LENGTH=512 \
python -m dnarag.cli eval-search \
  --config configs/standard.yaml \
  --benchmark benchmarks/sequence_search_100.jsonl \
  --conditions vector \
  --limit 10 \
  --output reports/sequence_window_bf16_100k_100query_vector_rerank_eval.json \
  --summary-only \
  --progress
```

It reranks sequence-window vector candidates with a lightweight sequence-overlap
score after vector retrieval and parent grouping. This is an engineering
ablation, not a BLAST replacement.

Vector raw vs rerank, mean over the two 100-query seeds:

| Route | Hit@1 | Hit@5 | Hit@10 | MRR |
| --- | ---: | ---: | ---: | ---: |
| raw vector | 0.3850 | 0.5050 | 0.5350 | 0.4383 |
| vector + sequence rerank | 0.5550 | 0.6700 | 0.6950 | 0.6041 |

By modality:

| Modality | Raw Hit@10 | Rerank Hit@10 | Raw MRR | Rerank MRR |
| --- | ---: | ---: | ---: | ---: |
| protein | 0.5500 | 0.6700 | 0.4486 | 0.6235 |
| DNA/cDNA | 0.5200 | 0.7200 | 0.4280 | 0.5847 |

By query type:

| Query type | Raw Hit@10 | Rerank Hit@10 | Raw MRR | Rerank MRR |
| --- | ---: | ---: | ---: | ---: |
| `exact_window` | 0.8500 | 0.8750 | 0.7324 | 0.8088 |
| `prefix_96` | 0.8750 | 0.9250 | 0.7612 | 0.8438 |
| `suffix_96` | 0.2250 | 0.4750 | 0.1688 | 0.3692 |
| `middle_short` | 0.2750 | 0.5250 | 0.1423 | 0.4313 |
| `mutated_96` | 0.4500 | 0.6750 | 0.3869 | 0.5677 |

Interpretation:

- Raw vector ranking was the weak point, not just the embedding space. A simple
  sequence-aware rerank improves Hit@10 by 0.16 and MRR by 0.1658 on average.
- The biggest gains are exactly where raw vector was weak: suffix, short
  internal fragments, and mutated fragments.
- This supports a stronger engineering path: vector retrieval provides candidate
  neighborhoods, then cheap sequence-aware reranking improves exact sequence
  utility without abandoning the unified BioRAG representation.

## Biological-Equivalence Evaluation

The strict parent-ID benchmark is useful for engineering regression, but it is
too harsh for repeated or near-duplicate biological records, especially
DNA/cDNA transcript windows. The `_bio` benchmarks add biological expected
fields extracted from record headers:

- protein: `GN=` gene names where present.
- DNA/cDNA: Ensembl `gene:`, `gene_symbol:`, gene/transcript biotype, and a
  first pass of immune gene-family prefixes.

Benchmarks:

- `benchmarks/sequence_search_100_bio.jsonl`: 100 tasks, 97 with biological
  expected fields.
- `benchmarks/sequence_search_100_seed20260516_bio.jsonl`: 100 tasks, 99 with
  biological expected fields.

Run:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DNARAG_EMBED_MAX_LENGTH=512 \
python -m dnarag.cli eval-search \
  --config configs/standard_bf16_merged.yaml \
  --benchmark benchmarks/sequence_search_100_bio.jsonl \
  --conditions blast,vector,hybrid_gated \
  --limit 10 \
  --output reports/sequence_window_bf16_100k_100query_bio_eval.json \
  --summary-only

DNARAG_VECTOR_SEQUENCE_RERANK=1 \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DNARAG_EMBED_MAX_LENGTH=512 \
python -m dnarag.cli eval-search \
  --config configs/standard_bf16_merged.yaml \
  --benchmark benchmarks/sequence_search_100_bio.jsonl \
  --conditions vector \
  --limit 10 \
  --output reports/sequence_window_bf16_100k_100query_bio_vector_rerank_eval.json \
  --summary-only
```

Mean over the two 100-query `_bio` seeds:

| Condition | Strict Hit@1 | Strict Hit@10 | Strict MRR | Bio Hit@1 | Bio Hit@10 | Bio MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `blast` | 0.4900 | 0.7550 | 0.5654 | 0.9694 | 0.9898 | 0.9772 |
| `vector` | 0.3850 | 0.5350 | 0.4383 | 0.6119 | 0.7751 | 0.6677 |
| `vector_rerank` | 0.5550 | 0.6950 | 0.6041 | 0.8720 | 0.8822 | 0.8758 |
| `hybrid_gated` | 0.4900 | 0.7550 | 0.5735 | 0.9694 | 0.9898 | 0.9780 |

Mean over the two seeds, split by modality:

| Condition | Modality | Strict Hit@10 | Strict MRR | Bio Hit@10 | Bio MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| `blast` | protein | 0.9600 | 0.9110 | 0.9898 | 0.9845 |
| `blast` | DNA/cDNA | 0.5500 | 0.2197 | 0.9900 | 0.9704 |
| `vector` | protein | 0.5500 | 0.4486 | 0.7273 | 0.6565 |
| `vector` | DNA/cDNA | 0.5200 | 0.4280 | 0.8200 | 0.6782 |
| `vector_rerank` | protein | 0.6700 | 0.6235 | 0.8102 | 0.8026 |
| `vector_rerank` | DNA/cDNA | 0.7200 | 0.5847 | 0.9500 | 0.9450 |
| `hybrid_gated` | protein | 0.9600 | 0.9121 | 0.9898 | 0.9852 |
| `hybrid_gated` | DNA/cDNA | 0.5500 | 0.2349 | 0.9900 | 0.9711 |

Vector raw vs rerank by query type:

| Query type | Raw strict Hit@10 | Rerank strict Hit@10 | Raw bio Hit@10 | Rerank bio Hit@10 |
| --- | ---: | ---: | ---: | ---: |
| `exact_window` | 0.8500 | 0.8750 | 0.9474 | 1.0000 |
| `prefix_96` | 0.8750 | 0.9250 | 0.9750 | 1.0000 |
| `suffix_96` | 0.2250 | 0.4750 | 0.6500 | 0.7250 |
| `middle_short` | 0.2750 | 0.5250 | 0.6144 | 0.7921 |
| `mutated_96` | 0.4500 | 0.6750 | 0.6908 | 0.8961 |

Interpretation:

- Biological-equivalence scoring changes the story substantially. BLAST and
  `hybrid_gated` recover almost all biologically equivalent targets even when
  the strict parent transcript ID is not rank 1.
- Raw vector retrieval is weaker than BLAST on strict sequence search, but its
  biological-equivalence Hit@10 is much higher than strict Hit@10. This
  supports using vectors as a representation-neighborhood layer.
- The lightweight sequence rerank improves both exact-ID and biological metrics:
  vector bio Hit@10 rises from `0.7751` to `0.8822`, and DNA/cDNA bio Hit@10
  reaches `0.9500`.
- These are not yet GO/pathway/function-enrichment claims. They are the first
  evidence that sequence-vector neighborhoods carry biological signal beyond
  exact transcript identity. The next step is DRAG graph enrichment and
  annotation-level validation.

## DRAG Neighborhood Enrichment

The first DRAG-facing enrichment check evaluates pure vector neighbors before
adding BLAST/domain/pathway biological-rule edges. Same-parent windows are
excluded and parent records are deduplicated, so adjacent windows from the same
source record do not inflate the score.

Output:

- `reports/vector_neighborhood_enrichment_100anchors.json`
- `reports/vector_neighborhood_enrichment_summary.md`
- `indexes/standard/graph/views/protein_sequence_window_1k.sqlite`
- `indexes/standard/graph/views/dna_sequence_window_1k.sqlite`

100-anchor summary:

| Target | Match | Vector Hit@10 | Random Hit@10 | Vector P@10 | Random P@10 |
| --- | --- | ---: | ---: | ---: | ---: |
| protein windows | `GN=` / gene symbol | 0.4300 | 0.0200 | 0.1710 | 0.0020 |
| DNA/cDNA windows | gene ID | 0.6900 | 0.0600 | 0.2460 | 0.0060 |
| DNA/cDNA windows | gene symbol | 0.7188 | 0.0625 | 0.2563 | 0.0063 |
| DNA/cDNA windows | any identity | 0.7100 | 0.0600 | 0.2570 | 0.0060 |

Interpretation: this is the first evidence that a method-agnostic vector graph
contains biological-label enrichment before adding explicit biological rules. It
should be framed as neighborhood enrichment, not as proof of biological
mechanism. Follow-up layers now include graph community analysis, community
purity, and GO/Reactome functional enrichment; Pfam/domain, literature
enrichment, and stronger BLAST/domain-rule ablations remain open.

Visualization and community analysis:

- `reports/drag_view_graph_visualization.md`
- `reports/figures/dna_sequence_window_1k_graph.html`
- `reports/figures/dna_sequence_window_1k_graph.svg`
- `reports/figures/protein_sequence_window_1k_graph.html`
- `reports/figures/protein_sequence_window_1k_graph.svg`

The DNA/cDNA 1k graph forms three communities with modularity `0.3052`; the
dominant labels separate `IGLV` and `IGHV` neighborhoods. The protein 1k graph
forms seven communities with modularity `0.3621`, including a `YWHAB`-enriched
community.

By modality:

| Condition | Modality | Hit@1 | Hit@5 | Hit@10 | MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| `blast` | protein | 0.9000 | 0.9800 | 1.0000 | 0.9395 |
| `blast` | DNA/cDNA | 0.1200 | 0.3400 | 0.5600 | 0.2368 |
| `vector` | protein | 0.4600 | 0.5600 | 0.5800 | 0.5045 |
| `vector` | DNA/cDNA | 0.3800 | 0.5000 | 0.5600 | 0.4361 |
| `hybrid_gated` | protein | 0.9000 | 0.9800 | 1.0000 | 0.9395 |
| `hybrid_gated` | DNA/cDNA | 0.1200 | 0.3400 | 0.5600 | 0.2512 |

Vector by query type:

| Query type | Hit@1 | Hit@5 | Hit@10 | MRR |
| --- | ---: | ---: | ---: | ---: |
| `exact_window` | 0.7500 | 0.8500 | 0.9000 | 0.7931 |
| `prefix_96` | 0.8000 | 0.9500 | 0.9500 | 0.8600 |
| `mutated_96` | 0.3000 | 0.4000 | 0.4500 | 0.3488 |
| `middle_short` | 0.1500 | 0.2500 | 0.3500 | 0.1996 |
| `suffix_96` | 0.1000 | 0.2000 | 0.2000 | 0.1500 |

Interpretation:

- The original 4-task `0.75` aggregate hides the real structure. Protein exact
  BLAST is strong; DNA strict-parent recovery is hard for both BLAST and vectors
  because many transcript windows are repeated or near-duplicates.
- Vector retrieval is strongest when the query overlaps the stored window start
  (`prefix_96`) or uses the full sampled window (`exact_window`). It is weak for
  suffix and short internal fragments, which means query-windowing and/or
  denser sequence-window indexing should be improved before making broad
  sequence-search claims.
- The strict-ID generated benchmark is useful for engineering regression tests,
  but the paper benchmark should add biological-equivalence scoring: same gene,
  same transcript family, BLAST-equivalent hits, GO/Reactome/domain/literature
  enrichment, and DRAG path quality.
- Retrying with a second random seed gives the same qualitative conclusion:
  vector-only is below BLAST on strict-ID sequence retrieval, while
  `hybrid_gated` preserves BLAST-level strict-ID recall and leaves vector
  neighborhoods available for BioRAG/DRAG.
- Protein and DNA/cDNA should be reported separately. The combined headline is
  useful only as a smoke summary because strict transcript-level DNA recovery is
  much harder and has different failure modes from protein retrieval.

## BF16 10k Window Run

Model: `dnagpt/OmniGene-4-CPT-v2-merged` BF16.

GPU: RTX PRO 6000 Blackwell 96 GB.

Status: locked as the first paper-facing sequence-vector baseline.

Collections:

- `protein_sequence_window`: 10,000 windows.
- `dna_sequence_window`: 10,000 windows.
- Window size 128, stride 64, batch size 16.

Build timing:

- protein windows: about 245 seconds for 10,000 windows.
- DNA/cDNA windows: about 221 seconds for 10,000 windows.
- observed VRAM during build: about 57 GB / 96 GB.
- no CPU offload warning observed.

Evaluation:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DNARAG_EMBED_MAX_LENGTH=512 \
python -m dnarag.cli eval-search \
  --config configs/standard.yaml \
  --benchmark benchmarks/sequence_search.jsonl \
  --conditions blast,vector \
  --limit 10 \
  --output reports/sequence_window_bf16_10k_eval.json \
  --summary-only \
  --progress
```

Result:

| Condition | Hit@1 | Hit@5 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `blast` | 0.7500 | 1.0000 | 1.0000 | 0.8750 | 821.263 |
| `vector` | 0.7500 | 0.7500 | 1.0000 | 0.7750 | 4479.744 |

Interpretation:

- BF16 sequence-window vectors now match BLAST at Hit@10 on the smoke sequence benchmark: both reach `1.0000`.
- The remaining gap is rank quality, not coverage at top 10: vector MRR is `0.7750` while BLAST MRR is `0.8750`.
- BLAST remains stronger on exact rank and latency for these exact-fragment tasks.
- The missed vector Hit@1/Hit@5 is `dna_enst00622028_fragment`; the expected transcript is deduplicated rank 10 after raw overfetch because several immunoglobulin-like cDNA windows score slightly higher.
- This is the expected result for the paper: the sequence-vector view is close enough to BLAST to serve as a unified BioRAG representation layer, while BLAST remains the biologically grounded exact-search component.
- Hybrid routing should keep BLAST for exact sequence evidence and use vector neighborhoods for representation-level similarity, mixed text/sequence retrieval, agent context construction, and DRAG graph construction.

## 4-bit POC

Collections:

- `protein_sequence_window`: 36 sequence-only windows, window size 128, stride 64.
- `dna_sequence_window`: 16 sequence-only windows, window size 128, stride 64.

Evaluation:

```bash
HF_HUB_OFFLINE=1 python -m dnarag.cli eval-search \
  --config configs/standard_4bit.yaml \
  --benchmark benchmarks/sequence_search.jsonl \
  --conditions blast,vector \
  --limit 10 \
  --output reports/sequence_window_eval.json \
  --summary-only \
  --progress
```

Result:

| Condition | Hit@1 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: |
| `blast` | 0.7500 | 1.0000 | 0.8750 | 1789.964 |
| `vector` | 1.0000 | 1.0000 | 1.0000 | 10168.009 |

Notes:

- Vector retrieval now ranks all four benchmark fragments at rank 1.
- BLAST ranks three fragments at rank 1 and one DNA fragment at rank 2 because another transcript has the same top bitscore.
- The local RTX 4080 SUPER 32 GB loads the 4-bit model, peaking around 28 GB VRAM, but transformers reports CPU offload. This is usable for small POC and sharded builds, not ideal for full-scale indexing.
- This is not a final paper-scale result because the POC collections intentionally cover the benchmark targets. The next experiment should scale to 10k, 100k, then full windows and evaluate exact fragments plus homology/near-neighbor tasks.
