# DRAG Graph Controls

This report adds explicit controls for the exploratory biological interpretation of DRAG sequence graphs.

| Graph | Condition | Nodes | Edges | Communities | Modularity | Top Signal |
|---|---|---:|---:|---:|---:|---|
| dna | observed | 579 | 19344 | 9 | 0.1741 | biotype:IG_V_gene (21, purity 1.0) |
| dna | kmer_jaccard | 579 | 2111 | 26 | 0.8745 | gene_family:IGKV (29, purity 1.0) |
| dna | degree_preserving_null_mean | 579.0 | 19344.0 | 4.2 | 0.0756 | - |
| protein | observed | 2623 | 31794 | 16 | 0.3179 | gene_symbol:nbaC (7, purity 0.5) |
| protein | kmer_jaccard | 2623 | 9398 | 107 | 0.9715 | gene_symbol:pgl (28, purity 1.0) |
| protein | degree_preserving_null_mean | 2623.0 | 31794.0 | 12.6 | 0.1569 | - |

## Parent Collapse

### dna

- Already parent-collapsed: `true`
- Parent-style nodes: `579/579`
- Distinct source Chroma rows represented: `579`

### protein

- Already parent-collapsed: `true`
- Parent-style nodes: `2623/2623`
- Distinct source Chroma rows represented: `2623`

## Interpretation Boundary

- Passing these controls would support a stronger exploratory biology claim.
- Failing them means DRAG should remain an evidence-packaging and visualization module in the main paper.
