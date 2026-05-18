# Vector Candidate Budget Sweep

Each query is vector-searched once at the max budget. Smaller budgets use prefixes of that candidate list, so this isolates candidate-pool and candidate-BLAST effects; it is not a fair per-budget vector lookup latency benchmark.

## Overall

| Budget | Exact Hit@10 | Exact MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Candidate BLAST ms |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.3333 | 0.3333 | 0.6667 | 0.6667 | 0.6667 | 206.430 |
| 25 | 0.3333 | 0.3333 | 0.6667 | 0.6667 | 0.6667 | 138.670 |
| 50 | 0.3333 | 0.3333 | 0.6667 | 0.6667 | 0.6667 | 126.995 |

## By Modality

### protein_sequence

| Budget | Exact Hit@10 | Exact MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Candidate BLAST ms |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.3333 | 0.3333 | 0.6667 | 0.6667 | 0.6667 | 206.430 |
| 25 | 0.3333 | 0.3333 | 0.6667 | 0.6667 | 0.6667 | 138.670 |
| 50 | 0.3333 | 0.3333 | 0.6667 | 0.6667 | 0.6667 | 126.995 |

## Interpretation

- Candidate Bio Recall@N shows whether expanding vector candidates increases the chance that BLAST can verify a biologically equivalent sequence.
- Because this is a prefix sweep from one max-budget vector search, vector lookup latency should be interpreted from `vector_search_summary`, not from each budget row.
- If recall plateaus, the next fix should be graph-expanded candidates or better vector ranking rather than simply increasing BLAST candidate count.
