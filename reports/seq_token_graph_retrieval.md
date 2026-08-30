# Held-out Sequence Token-Graph Retrieval

## Scope

Token-to-GO edges are learned only from the 1,901 index proteins. The 99 held-out parent proteins do not participate in graph construction. A 33-query development split selects the graph-expansion weight; the table reports the frozen 66-query test split.

Selected graph alpha on development data: `0.25`. Selected ProtT5 prefixes for candidate-tail replacement: BPE `75`, BPE+GO `75` of `100`.

The index-only graph contains 10 FDR-significant token--GO associations over 4,169 eligible tokens and 94 eligible GO terms.

| Test route | Hit@10 | Hit@50 | Hit@100 | Recall@100 | MRR | Paper hit | Paper recall | Candidate ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bpe_bm25 | 0.0909 | 0.1970 | 0.3788 | 0.1092 | 0.0588 | 0.2576 | 0.0744 | 15.05 |
| bpe_token_go_graph | 0.0758 | 0.1818 | 0.3333 | 0.0877 | 0.0558 | 0.2273 | 0.0672 | 15.05 |
| fixed3_bm25 | 0.0909 | 0.2727 | 0.4091 | 0.1540 | 0.0806 | 0.3636 | 0.1348 | 20.18 |
| kmer_jaccard | 0.1515 | 0.3485 | 0.3939 | 0.1236 | 0.1022 | 0.3636 | 0.1439 | saved ranking |
| blast | 0.2576 | 0.2576 | 0.2576 | 0.1143 | 0.1724 | 0.2576 | 0.1229 | saved ranking |
| prott5_vector | 0.2879 | 0.5152 | 0.5758 | 0.2737 | 0.2094 | 0.5455 | 0.2586 | 26.25 |
| prott5_bpe_rrf | 0.2727 | 0.4697 | 0.5455 | 0.2334 | 0.1180 | 0.5000 | 0.2314 | 41.30 |
| prott5_bpe_graph_rrf | 0.2576 | 0.4545 | 0.5455 | 0.2334 | 0.1092 | 0.5000 | 0.2253 | 41.30 |
| prott5_bpe_tail | 0.2879 | 0.5152 | 0.5909 | 0.2770 | 0.2095 | 0.5455 | 0.2586 | 41.30 |
| prott5_bpe_graph_tail | 0.2879 | 0.5152 | 0.5909 | 0.2770 | 0.2095 | 0.5455 | 0.2586 | 41.30 |

## Paired Test Deltas vs ProtT5

| Route | Metric | Delta | 95% CI |
|---|---|---:|---:|
| prott5_bpe_rrf | candidate_hit_at_10 | -0.0152 | [-0.1061, +0.0758] |
| prott5_bpe_rrf | candidate_hit_at_50 | -0.0455 | [-0.1212, +0.0152] |
| prott5_bpe_rrf | candidate_hit_at_100 | -0.0303 | [-0.1061, +0.0455] |
| prott5_bpe_rrf | candidate_recall_at_100 | -0.0403 | [-0.0829, -0.0057] |
| prott5_bpe_rrf | candidate_mrr | -0.0914 | [-0.1626, -0.0260] |
| prott5_bpe_rrf | paper_hit | -0.0455 | [-0.1212, +0.0303] |
| prott5_bpe_rrf | paper_recall | -0.0272 | [-0.0608, +0.0035] |
| prott5_bpe_graph_rrf | candidate_hit_at_10 | -0.0303 | [-0.1212, +0.0606] |
| prott5_bpe_graph_rrf | candidate_hit_at_50 | -0.0606 | [-0.1364, +0.0000] |
| prott5_bpe_graph_rrf | candidate_hit_at_100 | -0.0303 | [-0.1061, +0.0455] |
| prott5_bpe_graph_rrf | candidate_recall_at_100 | -0.0403 | [-0.0829, -0.0057] |
| prott5_bpe_graph_rrf | candidate_mrr | -0.1002 | [-0.1746, -0.0302] |
| prott5_bpe_graph_rrf | paper_hit | -0.0455 | [-0.1212, +0.0303] |
| prott5_bpe_graph_rrf | paper_recall | -0.0332 | [-0.0684, -0.0008] |
| prott5_bpe_tail | candidate_hit_at_10 | +0.0000 | [+0.0000, +0.0000] |
| prott5_bpe_tail | candidate_hit_at_50 | +0.0000 | [+0.0000, +0.0000] |
| prott5_bpe_tail | candidate_hit_at_100 | +0.0152 | [+0.0000, +0.0455] |
| prott5_bpe_tail | candidate_recall_at_100 | +0.0033 | [-0.0063, +0.0147] |
| prott5_bpe_tail | candidate_mrr | +0.0002 | [+0.0000, +0.0005] |
| prott5_bpe_tail | paper_hit | +0.0000 | [+0.0000, +0.0000] |
| prott5_bpe_tail | paper_recall | +0.0000 | [+0.0000, +0.0000] |
| prott5_bpe_graph_tail | candidate_hit_at_10 | +0.0000 | [+0.0000, +0.0000] |
| prott5_bpe_graph_tail | candidate_hit_at_50 | +0.0000 | [+0.0000, +0.0000] |
| prott5_bpe_graph_tail | candidate_hit_at_100 | +0.0152 | [+0.0000, +0.0455] |
| prott5_bpe_graph_tail | candidate_recall_at_100 | +0.0033 | [-0.0063, +0.0147] |
| prott5_bpe_graph_tail | candidate_mrr | +0.0002 | [+0.0000, +0.0005] |
| prott5_bpe_graph_tail | paper_hit | +0.0000 | [+0.0000, +0.0000] |
| prott5_bpe_graph_tail | paper_recall | +0.0000 | [+0.0000, +0.0000] |

## Interpretation

- BPE BM25 is the direct `query token -> protein` path; BPE token-GO graph adds `query token -> associated GO -> protein` expansion.
- Direct BPE BM25 reaches Hit@100 0.3788, and GO expansion lowers it to 0.3333; fixed 3-mer BM25 is the stronger local-token control at 0.4091.
- Naive reciprocal-rank fusion lowers ProtT5 MRR and Recall@100. It is a negative ablation, not the selected retrieval route.
- The development-selected tail route preserves the first 75 ProtT5 candidates and fills the remaining positions from token retrieval. It leaves Hit@10/50 unchanged and changes Hit@100 from 0.5758 to 0.5909 by recovering one additional test query; the paired Hit@100 interval includes no improvement, Recall@100 is unresolved, and paper metrics do not change.
- BPE+GO tail replacement produces the same frozen-test ranking as direct BPE tail replacement, so the GO expansion adds no observed retrieval value in this pilot.
- Reported combined latency is a sequential sum of measured ProtT5 end-to-end time and CPU token lookup. It is an unoptimized upper bound; the routes could be run concurrently.
- GO graph expansion is an annotation-assisted retrieval route, not a sequence-only homology method and not a BLAST replacement.
- Improvements whose paired confidence interval crosses zero are directional engineering results only.
- The split is parent-held-out but not UniRef50 family-held-out; remote-family claims remain out of scope.
