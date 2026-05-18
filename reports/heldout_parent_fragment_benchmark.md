# Held-Out Parent-Fragment Benchmark

Date: 2026-05-16

This benchmark is the construct-validity upgrade for BioRAG-DRAG. It is not the
same as the earlier in-index sequence-window stress test. Queries are sampled
from held-out Swiss-Prot parent proteins, and the emitted index FASTA excludes
the exact held-out parent accessions.

## Artifacts

| Artifact | Path |
| --- | --- |
| 50-query smoke benchmark | `benchmarks/protein_parent_frag_50_smoke.jsonl` |
| 50-query smoke leakage report | `reports/protein_parent_frag_50_smoke_leakage.md` |
| 500-query benchmark | `benchmarks/protein_parent_frag_500.jsonl` |
| 500 held-out parent list | `benchmarks/protein_parent_frag_500_heldout_accessions.txt` |
| 500-query index FASTA | `data/heldout/protein_parent_frag_500_index.fasta` |
| 500-query leakage report | `reports/protein_parent_frag_500_leakage.md` |
| Held-out retrieval config | `configs/heldout_parent_frag_500.yaml` |

## Split Summary

| Split | Source records | Held-out parents | Indexed parents | Exact parent leakage |
| --- | ---: | ---: | ---: | ---: |
| Smoke | 484,081 | 50 | 484,031 | 0 |
| Main | 484,081 | 500 | 483,581 | 0 |

The 500-query split has 74 query-fragment substring warnings in indexed records.
These are conserved or repeated Swiss-Prot fragments in other proteins, not exact
held-out parent leakage. The warning is useful for interpreting retrieval
results: BLAST and vector retrieval may recover biologically related or duplicated
sequences even when the exact parent is absent.

## Intended Interpretation

- Primary validity check: exact held-out parent accession leakage must be 0.
- Main metric: biological Hit@K/MRR based on shared gene symbols/families when
  annotations are available.
- Exact parent Hit@K is not expected because the exact parents are excluded.
- This benchmark is a first held-out parent-fragment test, not yet a full remote
  homology benchmark with curated family labels.

## Completed and Pending Runs

Completed under the same controlled20k held-out split:

1. OmniGene-CPT BF16 mean and last-token pooling.
2. ESM-2 650M mean and last-token pooling.
3. ProtT5-XL-UniRef50 mean and last-token pooling.
4. BLAST alignment baseline.

Remaining upgrade experiments:

1. Add original Gemma4 MoE base/instruct controls when the checkpoint is
   available locally or downloaded.
2. Add DNA encoders such as DNABERT-2 or Nucleotide Transformer for DNA tasks.
3. Run larger Swiss-Prot scale curves and candidate-BLAST speed crossover tests.

## BLAST Baseline

The held-out BLAST database was built from
`data/heldout/protein_parent_frag_500_index.fasta` using `makeblastdb -dbtype prot`.
Because the exact held-out parent accessions are excluded, exact parent Hit@K is
0 by design. The meaningful baseline is biological match against indexed records
sharing available gene/family annotations.

| Split | Tasks | Exact Hit@10 | Biological Hit@1 | Biological Hit@5 | Biological Hit@10 | Biological MRR | Mean latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Smoke | 50 | 0.000 | 0.740 | 0.740 | 0.760 | 0.7425 | 1083.4 ms |
| Main | 500 | 0.000 | 0.712 | 0.790 | 0.806 | 0.7442 | 1039.3 ms |

The 500-query BLAST result is the current held-out reference line for vector
candidate retrieval and vector-to-BLAST reranking.

## Controlled 20k Subset

For rapid neural-retrieval experiments, we also exported a controlled 20k parent
subset at `data/heldout/protein_parent_frag_500_controlled20k_index.fasta`. This
subset contains 7,987 indexed same-gene positive records and 12,013 random
background records. All 500 held-out queries have at least one same-gene indexed
candidate, and exact held-out parent leakage remains 0.

| Condition | Index | Biological Hit@10 | Biological MRR | Candidate recall@200 | Mean latency |
| --- | --- | ---: | ---: | ---: | ---: |
| BLAST | controlled20k parents | 0.856 | 0.8289 | 0.856 | 138.6 ms |
| OmniGene parent vector | controlled20k parents | 0.008 | 0.0013 | 0.090 | 216.2 ms |
| OmniGene window vector | controlled20k windows | 0.312 | 0.2623 | 0.494 | 538.4 ms |
| OmniGene window vector, last-token | controlled20k windows | 0.094 | 0.0725 | 0.184 | 531.5 ms |
| ESM-2 window vector | controlled20k windows | 0.656 | 0.5764 | 0.734 | 329.0 ms |
| ESM-2 window vector, last-token | controlled20k windows | 0.236 | 0.2025 | 0.356 | 332.2 ms |
| ProtT5 window vector | controlled20k windows | 0.778 | 0.7158 | 0.846 | 329.1 ms |
| ProtT5 window vector, last-token | controlled20k windows | 0.468 | 0.3668 | 0.640 | 333.1 ms |

The parent-vector result is a negative ablation: compressing an entire protein
into one vector loses the local fragment signal needed by 64--128 aa queries.
The multi-vector window index recovers much more biological signal, especially
as a candidate pool, but remains below BLAST on this held-out fragment task.
ProtT5 mean pooling is the strongest completed dense protein baseline and is
closer to BLAST than ESM-2 or OmniGene, while BLAST remains the strongest
alignment-grounded route. Last-token pooling is substantially weaker for
OmniGene, ESM-2, and ProtT5 on this fragment task. This supports a
model-agnostic BioRAG interpretation: specialized protein encoders can be used
for protein partitions, while OmniGene remains a useful unified
biological-language backbone for mixed sequence/text and agent workflows. BLAST
remains the alignment-grounded verification/reranking layer.

## Embedding Pooling

The OmniGene embedding wrapper currently uses the last hidden layer of the causal
LM, not generation logits. With `pooling: mean`, each input sequence is embedded
by attention-mask mean pooling over token hidden states, followed by L2
normalization. In code this is:

`pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1)`

The alternative `pooling: eos` takes the last valid token hidden state:

`pooled = hidden[batch_index, attention_mask.sum(dim=1) - 1]`

OmniGene has now been run with both pooling modes: mean pooling reaches
biological Hit@10/MRR 0.312/0.2623, while last-token pooling falls to
0.094/0.0725. ESM-2 shows the same direction: mean pooling reaches
0.656/0.5764, while last-token pooling falls to 0.236/0.2025. ProtT5 also shows
the same direction: mean pooling reaches 0.778/0.7158, while last-token pooling
falls to 0.468/0.3668. Mean pooling is therefore the safer default for this
sequence-window retrieval task.
