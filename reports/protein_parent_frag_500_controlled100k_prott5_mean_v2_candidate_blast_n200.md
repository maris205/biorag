# Vector Coarse Retrieval + Candidate BLAST Rerank

This experiment evaluates vector retrieval as a candidate generator, followed by BLAST reranking on the vector-retrieved candidate subset. It should be interpreted as a BioRAG pipeline ablation, not as a claim that vectors replace full-database BLAST.

## Overall

| Method | Tasks | Hit@10 | MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Avg latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| Vector -> candidate BLAST rerank | 500 | 0.0000 | 0.0000 | 0.7260 | 0.6239 | 0.8000 | 700.501 |

## By Modality

| Category | Tasks | Hit@10 | MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Avg latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| protein_sequence | 500 | 0.0000 | 0.0000 | 0.7260 | 0.6239 | 0.8000 | 700.501 |

## Interpretation

- `Candidate Bio Recall@N` measures whether vector coarse retrieval placed a biologically equivalent candidate inside the candidate pool before BLAST reranking.
- The final reranked metrics measure whether candidate-subset BLAST can promote the correct or biologically equivalent candidate into the top results.
- Full-database BLAST remains the verification reference; this pipeline is intended for instant candidate generation plus verified reranking inside BioRAG/DRAG.
