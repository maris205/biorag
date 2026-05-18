# DRAG View Graph Analysis: protein_sequence_window_hybrid_10k.sqlite

## Summary

- Target: `protein_sequence_window`
- Recipe: `hybrid_vector_blast_neighbors`
- Biological rules used: `true`
- Nodes: `2623`
- Edges: `35549` undirected from `48292` edge rows
- Connected components: `1`
- Largest component: `2623`
- Communities: `12`
- Modularity: `0.3779`

## Top Communities

| Community | Size | Density | Top gene/symbol/family/biotype labels |
| ---: | ---: | ---: | --- |
| 0 | 851 | 0.0363 | gene_symbol:pgl (23, x0.7161) |
| 1 | 539 | 0.0280 | gene_symbol:gnd (23, x3.0251) |
| 2 | 519 | 0.0293 | gene_symbol:pgl (71, x3.6245) |
| 3 | 513 | 0.0214 | gene_symbol:FV3-086L (1, x5.1131) |
| 4 | 63 | 0.2622 | gene_symbol:yfbR (42, x41.6349) |
| 5 | 41 | 0.2915 | gene_symbol:6b (4, x63.9756) |
| 6 | 33 | 0.3220 | gene_symbol:qutE (13, x73.8074) |
| 7 | 19 | 0.4035 | gene_symbol:Eif4ebp1 (2, x138.0526) |
| 8 | 15 | 0.8952 | gene_symbol:SAV2344 (1, x174.8667) |
| 9 | 12 | 0.9091 | gene_symbol:omp (12, x174.8667) |
| 10 | 9 | 0.9167 | gene_symbol:BCAN_B0743 (1, x291.4444) |
| 11 | 9 | 0.6667 | gene_symbol:nahJ (3, x291.4444) |

Interpretation: this graph is a hybrid DRAG view combining vector
neighbors with BLAST-derived sequence-similarity edges over the same
sequence entities. It tests whether biological-rule edges sharpen local
modules while preserving vector-graph connectivity for RAG expansion.
