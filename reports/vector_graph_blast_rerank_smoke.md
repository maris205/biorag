# Vector + DRAG Graph Candidates + Candidate BLAST Rerank

This experiment expands vector-retrieved sequence candidates through an existing DRAG view graph before candidate-subset BLAST reranking. The current graph is a 10k view graph, so graph coverage is reported explicitly.

## Overall

| Method | Tasks | Exact Hit@10 | Exact MRR | Bio Hit@10 | Bio MRR | Seed Bio Recall | Expanded Bio Recall | Graph added | Graph seeds found | BLAST ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Vector(50) + DRAG(hybrid) -> BLAST | 6 | 0.3333 | 0.3333 | 0.6667 | 0.6667 | 0.6667 | 0.6667 | 90.17 | 4.17 | 187.614 |

## By Modality

| Category | Tasks | Exact Hit@10 | Bio Hit@10 | Bio MRR | Seed Bio Recall | Expanded Bio Recall | Graph added | Graph seeds found |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| protein_sequence | 6 | 0.3333 | 0.6667 | 0.6667 | 0.6667 | 0.6667 | 90.17 | 4.17 |

## Interpretation

- `Seed Bio Recall` is the biological recall of the vector seed pool before graph expansion.
- `Expanded Bio Recall` is the biological recall after adding DRAG graph neighbors.
- Because the current DRAG view graphs cover only a 10k sequence subgraph, low `Graph seeds found` means this is a coverage-limited ablation rather than a full-scale DRAG result.
- A full 100k or complete sequence DRAG graph is the next step before making a strong retrieval-quality claim for graph-expanded candidates.
