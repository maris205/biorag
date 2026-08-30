# Protein Embedding Selection

## Decision

Use **ProtT5-XL-UniRef50 with attention-mask mean pooling** as the default
encoder for the protein sequence partition in BioRAG. Keep **ESM-2 650M mean**
as the lower-memory and slightly faster alternative. Retain **OmniGene-4-CPT
mean** for unified mixed sequence/text and agent-facing paths, rather than
claiming it is the strongest protein-only encoder.

## Evidence

The primary comparison uses the fixed 500-query held-out parent-fragment split
and a controlled20k protein index. Exact held-out parent accessions are absent
from the index; biological retrieval is measured using shared gene/family
labels.

| Method | Pooling | Bio Hit@10 | Bio MRR | Recall@200 | Avg latency |
|---|---|---:|---:|---:|---:|
| BLAST | alignment | 0.8560 | 0.8289 | 0.8560 | 138.6 ms |
| ProtT5-XL-UniRef50 | mean | **0.7780** | **0.7158** | **0.8460** | 329.1 ms |
| ESM-2 650M | mean | 0.6560 | 0.5764 | 0.7340 | 329.0 ms |
| OmniGene-4-CPT BF16 | mean | 0.3120 | 0.2623 | 0.4940 | 538.4 ms |

Mean pooling is also consistently better than last-token pooling:

| Model | Mean Bio Hit@10 / MRR | Last Bio Hit@10 / MRR |
|---|---:|---:|
| ProtT5-XL-UniRef50 | 0.7780 / 0.7158 | 0.4680 / 0.3668 |
| ESM-2 650M | 0.6560 / 0.5764 | 0.2360 / 0.2025 |
| OmniGene-4-CPT BF16 | 0.3120 / 0.2623 | 0.0940 / 0.0725 |

The independent 99-query held-out sequence-to-function-to-paper pilot gives the
same ordering for the dense protein encoders. At protein top-50 and paper
top-200, ProtT5 mean obtains candidate MRR `0.217`, paper Hit `0.465`, and paper
Recall `0.248`; ESM-2 obtains `0.172`, `0.364`, and `0.203`, respectively.
These results are still a pilot and use curated graph labels, so they support
the routing decision but do not establish general homology superiority.

## Scale Check

ProtT5 mean remains the dense leader as the controlled index grows:

| Index | BLAST Bio@10 | ProtT5 Bio@10 | ProtT5 Bio MRR | ProtT5 Recall@200 |
|---|---:|---:|---:|---:|
| controlled20k | 0.8560 | 0.7780 | 0.7158 | 0.8460 |
| controlled100k | 0.8320 | 0.7260 | 0.6268 | 0.8000 |
| controlled300k | 0.8140 | 0.6760 | 0.5788 | 0.7740 |

The full Swiss-Prot dense index has not been completed. Therefore the current
claim is “selected default on the completed held-out controls”, not “best at
full Swiss-Prot scale”. BLAST remains the alignment-grounded verification and
reranking route.

## Operational Policy

- Protein-only dense retrieval: ProtT5 mean.
- Memory-sensitive or latency-sensitive protein retrieval: ESM-2 650M mean.
- Mixed DNA/protein/text or unified agent context: OmniGene mean where a shared
  representation is more important than protein-only retrieval quality.
- Exact sequence verification: BLASTP after vector candidate generation when
  the workflow needs alignment evidence.
- Last-token and CLS variants: pooling ablations, not production defaults.

## Remaining Validation

The next protein experiment is a full Swiss-Prot scale curve using the same
held-out protocol and, if resources permit, an ESM-2 comparison at matched
scale. No new model training is required for the present routing decision.
