# Protein Embedding Baseline Comparison

Held-out parent-fragment retrieval on the controlled20k protein index. BLAST is the alignment reference; vector rows use sequence-window Chroma retrieval with top-200 candidate pools. The exact held-out parent accessions are excluded from the index, so the main metric is biological match based on shared gene/family labels rather than exact parent ID.

| Method | Backend | Pooling | Tasks | Bio Hit@10 | Bio MRR | Recall@50 | Recall@100 | Recall@200 | Avg latency ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BLAST local alignment | blast | alignment | 500 | 0.8560 | 0.8289 | 0.8560 | 0.8560 | 0.8560 | 138.6 |
| OmniGene-4-CPT BF16 | omnigene | mean | 500 | 0.3120 | 0.2623 | 0.3980 | 0.4240 | 0.4940 | 538.4 |
| OmniGene-4-CPT BF16 | omnigene | last | 500 | 0.0940 | 0.0725 | 0.1320 | 0.1500 | 0.1840 | 531.5 |
| ESM-2 650M | esm | mean | 500 | 0.6560 | 0.5764 | 0.6940 | 0.7120 | 0.7340 | 329.0 |
| ESM-2 650M | esm | last | 500 | 0.2360 | 0.2025 | 0.2740 | 0.3140 | 0.3560 | 332.2 |
| ProtT5-XL-UniRef50 | prott5 | mean | 500 | 0.7780 | 0.7158 | 0.8080 | 0.8280 | 0.8460 | 329.1 |
| ProtT5-XL-UniRef50 | prott5 | last | 500 | 0.4680 | 0.3668 | 0.5540 | 0.6080 | 0.6400 | 333.1 |

Current interpretation:
- ProtT5 mean pooling is the strongest completed dense protein baseline and narrows the gap to BLAST, but BLAST remains stronger for alignment-grounded verification.
- Mean pooling is consistently stronger than last-token pooling for OmniGene, ESM-2, and ProtT5 on this fragment task.
- OmniGene-4-CPT is useful as a unified sequence/text representation layer for BioRAG agents, but current protein-only retrieval results do not support treating it as the strongest protein embedding model.
- This supports a model-agnostic BioRAG framing: use specialized encoders for sequence partitions when they are stronger, and use OmniGene as an integrated biological-language backbone where unified agent behavior matters.
