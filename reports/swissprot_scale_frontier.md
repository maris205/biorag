# Swiss-Prot Scale Frontier

This is a scale-frontier tracking table. Completed BLAST rows show alignment-reference latency as the indexed protein corpus grows. Vector and candidate-BLAST rows are reported only where a matching vector index exists; larger vector indexes remain pending background jobs. Candidate-BLAST is treated as an ablation unless it improves both biological retrieval quality and verified-route latency at matched scale.

## Completed and Pending Scale Points

| Scale | Records | BLAST Bio@10 | BLAST MRR | BLAST ms | Vector Bio@10 | Vector MRR | Vector Recall@200 | Vector ms | Candidate-BLAST Bio@10 | Candidate MRR | Candidate Recall@200 | Candidate total ms | Candidate BLAST-only ms | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| controlled20k | 20000 | 0.8560 | 0.8289 | 138.6 | 0.7780 | 0.7158 | 0.8460 | 329.1 | - | - | - | - | - | vector_complete_candidate_pending |
| controlled100k | 100000 | 0.8320 | 0.7960 | 329.2 | 0.7260 | 0.6268 | 0.8000 | 581.4 | 0.7580 | 0.7245 | 0.8000 | 839.7 | 189.2 | complete |
| controlled300k | 300000 | 0.8140 | 0.7613 | 796.5 | 0.6760 | 0.5788 | 0.7740 | 812.5 | 0.7320 | 0.6835 | 0.7740 | 1020.6 | 209.6 | complete |
| full held-out Swiss-Prot | 483581 | 0.8060 | 0.7442 | 1039.3 | - | - | - | - | - | - | - | - | - | blast_complete_vector_pending |

## Interpretation

- Full-database BLAST remains the alignment-grounded reference and must stay in the verified route.
- ProtT5 mean pooling provides a nontrivial dense candidate layer, but the completed 20k/100k/300k vector points remain below BLAST on biological Hit@10 and MRR.
- At controlled100k, candidate-BLAST improves dense retrieval MRR over vector-only (0.7245 vs. 0.6268) and verifies candidates, but its total measured latency (839.7 ms) is slower than full BLAST at the same scale (329.2 ms).
- At controlled300k, vector Recall@200 remains 0.7740 while BLAST latency rises to 796.5 ms. Candidate-BLAST improves dense retrieval MRR over vector-only (0.6835 vs. 0.5788), but its measured total latency is 1020.6 ms.
- The 100k and 300k results therefore support candidate-BLAST as an evidence-quality ablation, not yet as a speed advantage in the current Chroma implementation. The candidate-BLAST-only portions are much smaller (189.2/209.6 ms), so the systems question shifts to optimized vector serving.
- The stop/go rule is simple: keep candidate-BLAST as an ablation unless top-200 candidate recall remains high and verified-route latency improves at larger scale.

## Pending Jobs

- Build ProtT5 or ESM-2 mean protein_sequence_window vector indexes for full held-out Swiss-Prot.
- Run vector top-200 and vector->candidate-BLAST budget sweeps at full scale.
- Only claim candidate-BLAST speed advantage if matched-accuracy latency crosses full BLAST at larger scale or after optimized vector serving; the completed 100k and 300k Chroma points do not cross it.
