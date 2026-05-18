# BF16 100k Sequence-Window Bio Evaluation

Date: 2026-05-15

Model: `dnagpt/OmniGene-4-CPT-v2-merged` BF16.

Config: `configs/standard_bf16_merged.yaml`.

Benchmarks:

- `benchmarks/sequence_search_100_bio.jsonl`
- `benchmarks/sequence_search_100_seed20260516_bio.jsonl`

Each seed contains 50 protein and 50 DNA/cDNA sequence-window queries, balanced
across `exact_window`, `prefix_96`, `suffix_96`, `middle_short`, and
`mutated_96`. Biological expected fields cover 97 and 99 tasks respectively.

## Two-Seed Mean

| Condition | Strict Hit@1 | Strict Hit@5 | Strict Hit@10 | Strict MRR | Bio Hit@1 | Bio Hit@5 | Bio Hit@10 | Bio MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `blast` | 0.4900 | 0.6250 | 0.7550 | 0.5654 | 0.9694 | 0.9898 | 0.9898 | 0.9772 |
| `vector` | 0.3850 | 0.5050 | 0.5350 | 0.4383 | 0.6119 | 0.7444 | 0.7751 | 0.6677 |
| `vector_rerank` | 0.5550 | 0.6700 | 0.6950 | 0.6041 | 0.8720 | 0.8822 | 0.8822 | 0.8758 |
| `hybrid_gated` | 0.4900 | 0.6250 | 0.7550 | 0.5735 | 0.9694 | 0.9898 | 0.9898 | 0.9780 |

## Modality Split

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

## Vector Rerank By Query Type

| Query type | Raw strict Hit@10 | Rerank strict Hit@10 | Raw bio Hit@10 | Rerank bio Hit@10 |
| --- | ---: | ---: | ---: | ---: |
| `exact_window` | 0.8500 | 0.8750 | 0.9474 | 1.0000 |
| `prefix_96` | 0.8750 | 0.9250 | 0.9750 | 1.0000 |
| `suffix_96` | 0.2250 | 0.4750 | 0.6500 | 0.7250 |
| `middle_short` | 0.2750 | 0.5250 | 0.6144 | 0.7921 |
| `mutated_96` | 0.4500 | 0.6750 | 0.6908 | 0.8961 |

## Interpretation

- Strict parent-ID retrieval is an engineering regression metric, not the final
  biological-validity metric.
- Biological-equivalence scoring reveals that many strict DNA/cDNA misses are
  same-gene or closely equivalent sequence neighborhoods.
- Raw vector retrieval is below BLAST for exact sequence ranking, but its
  biological Hit@10 is substantially higher than strict Hit@10.
- Lightweight sequence-aware reranking raises vector bio Hit@10 from `0.7751`
  to `0.8822`, with DNA/cDNA bio Hit@10 reaching `0.9500`.
- The result supports the BioRAG/DRAG framing: use vectors as a unified
  candidate-neighborhood layer, keep BLAST as biologically grounded exact
  evidence, and validate biological meaning through graph enrichment and
  annotation-level metrics.

Machine-readable summary:
`reports/sequence_window_bf16_100k_100query_bio_split_summary.json`.
