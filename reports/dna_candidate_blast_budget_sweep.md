# DNA Vector Shortlist and Candidate-BLAST Budget Sweep

This is the first end-to-end DNA hybrid experiment for BioRAG. DNABERT-2 mean
pooling with 256/128 windows generates a local candidate pool from a 20k-window
Chroma index; `blastn` then verifies only those candidate nucleotide sequences.
The benchmark has 100 held-out transcript-fragment queries. Exact held-out
parents are absent, so strict exact-parent metrics are zero by construction;
the reported biological metrics use shared gene labels.

## Results

| Candidate budget | Candidate Bio Recall@N | Candidate Bio Hit@10 | Final Bio Hit@10 | Final Bio MRR | Vector+BLAST ms/query | Candidate BLAST ms/query |
|---:|---:|---:|---:|---:|---:|---:|
| 50 | 0.2900 | 0.2500 | **0.2800** | **0.2712** | 998.3 | 245.7 |
| 100 | 0.3000 | 0.2500 | 0.2700 | 0.2700 | 999.1 | 258.5 |
| 200 | **0.3100** | 0.2500 | 0.2700 | 0.2700 | 1028.8 | 279.9 |

All three budgets completed `100/100` BLASTN subset calls successfully. The
50-candidate route is the current default because it gives indistinguishable
final biological retrieval quality at the lowest verification cost. The small
differences are not large enough to claim a statistically significant ranking
advantage; the 200-candidate route has slightly higher candidate recall but no
final Hit@10/MRR gain in this 100-query sample.

## Engineering Interpretation

- The vector shortlist is functioning as a valid upstream candidate generator:
  candidate-subset BLAST promotes the biological match into the final top-10 on
  roughly 27--28% of these held-out transcript-fragment queries.
- Candidate BLAST is cheaper than full search in isolation, about 246--284
  ms/query here, but the current Chroma lookup and query processing dominate
  the complete route at about 1 second/query.
- This experiment does not establish a speed advantage over full BLASTN. It
  establishes the route contract and evidence composition. The performance
  claim requires a resident FAISS index, GPU lookup, or another optimized
  vector serving path.
- The biological quality remains below the direct full-database BLASTN
  reference (`Bio Hit@10/MRR = 0.91/0.91`), consistent with the intended
  complementary design rather than replacement.

## Artifacts

- Chroma index: `indexes/heldout_dna_parent_frag_100_controlled20k_dnabert2_mean256/vector`
- 50 candidates: `reports/results/dna_dnabert2_mean256_candidate_blast50.json`
- 100 candidates: `reports/results/dna_dnabert2_mean256_candidate_blast100.json`
- 200 candidates: `reports/results/dna_dnabert2_mean256_candidate_blast200.json`
- Builder configuration: `configs/heldout_dna_parent_frag_100_controlled20k_dnabert2_mean256.yaml`

The backend lookup-only comparison for this same DNA collection is reported in
`reports/dna_vector_backend_latency.md`. It measures Chroma, FAISS CPU, and
FAISS GPU separately from query embedding and candidate BLASTN.

The final exact-parent fields are intentionally zero because the query parent
accessions are held out. For the next experiment, candidate-level biological
recall should be evaluated on a larger family-stratified benchmark, followed by
FAISS CPU/GPU resident-index latency measurements.
