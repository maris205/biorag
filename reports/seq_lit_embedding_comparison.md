# SeqLit-DAG Protein Embedding Comparison

The 50 queries are sequence windows from indexed parent proteins. This table evaluates model integration and evidence-path behavior, not held-out homology competitiveness.

| Model | Protein Hit@1 | Protein Hit@10 | Protein MRR | Paper Recall@50 | Complete path | Embed ms/query | Lookup ms/query | E2E ms/query | Peak GiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ProtT5-XL mean | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 2.62 | 0.262 | 2.88 | 2.59 |
| ESM-2 650M mean | 0.960 | 1.000 | 0.977 | 1.000 | 1.000 | 2.34 | 0.327 | 2.67 | 1.54 |
| OmniGene-4-CPT BF16 mean | 0.900 | 0.940 | 0.914 | 0.947 | 0.940 | 51.75 | 0.523 | 52.28 | 49.29 |

## Findings

1. Window indexing with parent collapse is necessary: a full-protein mean-pooling sanity condition was weak, whereas 128-aa windows with stride 64 recover the parent reliably.
2. ProtT5 is the strongest protein-only entry model in this sample, reaching perfect parent rank and paper-path recovery while using less than 3 GiB peak allocated memory.
3. ESM-2 is nearly as strong and slightly faster end to end. It provides a practical public baseline and deployment option.
4. OmniGene remains viable as the unified biological-language backbone, but it is slower and less accurate than specialized protein encoders on this protein-only route.
5. Paper recall can exceed exact parent recovery because several candidate proteins share curated GOA-supported PMIDs. This is a graph property to analyze, not an excuse to relax protein retrieval metrics.

## Next Experiments

- Build a held-out parent/family split where query proteins are absent from the index and paper relevance is derived independently from the retrieval model.
- Report paper Recall@10/20/50, nDCG, and parent-collapsed controls against random, k-mer-NN, and BLAST candidate graphs.
- Scale ProtT5 and ESM-2 indexes to the curated Swiss-Prot literature subset, then full Swiss-Prot, while retaining the same PMID ground truth.
