# Vector Candidate Budget Sweep

Each query is vector-searched once at the max budget. Smaller budgets use prefixes of that candidate list, so this isolates candidate-pool and candidate-BLAST effects; it is not a fair per-budget vector lookup latency benchmark.

## Overall

| Budget | Exact Hit@10 | Exact MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Candidate BLAST ms |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.5000 | 0.3945 | 0.8283 | 0.8196 | 0.8283 | 171.963 |
| 25 | 0.5400 | 0.4517 | 0.8485 | 0.8394 | 0.8485 | 133.136 |
| 50 | 0.5700 | 0.4898 | 0.8687 | 0.8687 | 0.8788 | 131.583 |
| 100 | 0.6100 | 0.5151 | 0.8990 | 0.8990 | 0.9293 | 138.110 |
| 200 | 0.6500 | 0.5377 | 0.9293 | 0.9293 | 0.9596 | 146.236 |

## By Modality

### dna_sequence

| Budget | Exact Hit@10 | Exact MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Candidate BLAST ms |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.4800 | 0.3304 | 0.8200 | 0.8200 | 0.8200 | 178.508 |
| 25 | 0.5400 | 0.4006 | 0.8400 | 0.8400 | 0.8400 | 138.308 |
| 50 | 0.5400 | 0.4167 | 0.8600 | 0.8600 | 0.8600 | 136.229 |
| 100 | 0.6000 | 0.4473 | 0.9000 | 0.9000 | 0.9400 | 141.061 |
| 200 | 0.6400 | 0.4625 | 0.9600 | 0.9600 | 1.0000 | 155.603 |

### protein_sequence

| Budget | Exact Hit@10 | Exact MRR | Bio Hit@10 | Bio MRR | Candidate Bio Recall@N | Candidate BLAST ms |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.5200 | 0.4587 | 0.8367 | 0.8192 | 0.8367 | 165.417 |
| 25 | 0.5400 | 0.5029 | 0.8571 | 0.8388 | 0.8571 | 127.965 |
| 50 | 0.6000 | 0.5629 | 0.8776 | 0.8776 | 0.8980 | 126.937 |
| 100 | 0.6200 | 0.5829 | 0.8980 | 0.8980 | 0.9184 | 135.160 |
| 200 | 0.6600 | 0.6129 | 0.8980 | 0.8980 | 0.9184 | 136.869 |

## Interpretation

- Candidate Bio Recall@N shows whether expanding vector candidates increases the chance that BLAST can verify a biologically equivalent sequence.
- Because this is a prefix sweep from one max-budget vector search, vector lookup latency should be interpreted from `vector_search_summary`, not from each budget row.
- If recall plateaus, the next fix should be graph-expanded candidates or better vector ranking rather than simply increasing BLAST candidate count.
