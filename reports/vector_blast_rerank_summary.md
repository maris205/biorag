# Vector Coarse Retrieval + Candidate BLAST Rerank

This experiment evaluates vector retrieval as a candidate generator, followed by BLAST reranking on the vector-retrieved candidate subset. It should be interpreted as a BioRAG pipeline ablation, not as a claim that vectors replace full-database BLAST.

## Overall

| Method | Tasks | Hit@10 | MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Avg latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| Vector -> candidate BLAST rerank | 100 | 0.5700 | 0.4898 | 0.8687 | 0.8687 | 0.8788 | 823.403 |

## By Modality

| Category | Tasks | Hit@10 | MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Avg latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| dna_sequence | 50 | 0.5400 | 0.4167 | 0.8600 | 0.8600 | 0.8600 | 655.458 |
| protein_sequence | 50 | 0.6000 | 0.5629 | 0.8776 | 0.8776 | 0.8980 | 991.347 |

## Interpretation

- `Candidate Bio Recall@N` measures whether vector coarse retrieval placed a biologically equivalent candidate inside the candidate pool before BLAST reranking.
- The final reranked metrics measure whether candidate-subset BLAST can promote the correct or biologically equivalent candidate into the top results.
- Full-database BLAST remains the verification reference; this pipeline is intended for instant candidate generation plus verified reranking inside BioRAG/DRAG.
