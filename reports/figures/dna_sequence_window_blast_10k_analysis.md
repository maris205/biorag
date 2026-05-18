# DRAG View Graph Analysis: dna_sequence_window_blast_10k.sqlite

## Summary

- Target: `dna_sequence_window`
- Recipe: `blast_sequence_neighbors`
- Biological rules used: `true`
- Nodes: `579`
- Edges: `995` undirected from `1645` edge rows
- Connected components: `219`
- Largest component: `46`
- Communities: `220`
- Modularity: `0.9383`

## Top Communities

| Community | Size | Density | Top gene/symbol/family/biotype labels |
| ---: | ---: | ---: | --- |
| 0 | 46 | 0.1556 | gene_id:ENSG00000278042.2 (2, x12.587); gene_symbol:IGHV3-72 (3, x12.587); gene_family:IGHV (42, x4.9873); biotype:IG_V_gene (44, x2.3872) |
| 1 | 30 | 0.2207 | gene_id:ENSG00000211935.3 (1, x19.3); gene_symbol:IGHV1-3 (2, x19.3); gene_family:IGHV (23, x4.1877); biotype:IG_V_gene (26, x2.1629) |
| 2 | 29 | 0.2488 | gene_id:ENSG00000243290.3 (1, x19.9655); gene_symbol:IGKV1-12 (2, x19.9655); gene_family:IGKV (28, x7.8737); biotype:IG_V_gene (29, x2.4957) |
| 3 | 18 | 0.3660 | gene_id:ENSG00000282451.1 (1, x32.1667); gene_symbol:IGHV4-61 (2, x32.1667); gene_family:IGHV (15, x4.5519); biotype:IG_V_gene (17, x2.357) |
| 4 | 15 | 0.3810 | gene_id:ENSG00000211642.4 (1, x38.6); gene_symbol:IGLV1-44 (2, x38.6); gene_family:IGLV (15, x12.8667); biotype:IG_V_gene (15, x2.4957) |
| 5 | 15 | 0.4286 | gene_id:ENSG00000282182.1 (2, x38.6); gene_symbol:IGKV2-40 (3, x38.6); gene_family:IGKV (15, x8.1549); biotype:IG_V_gene (15, x2.4957) |
| 6 | 12 | 0.5303 | gene_id:ENSG00000211643.2 (1, x48.25); gene_symbol:IGLV5-37 (2, x48.25); gene_family:IGLV (11, x11.7944); biotype:IG_V_gene (12, x2.4957) |
| 7 | 12 | 0.5152 | gene_id:ENSG00000282615.1 (1, x48.25); gene_symbol:IGHJ5 (2, x48.25); biotype:IG_J_gene (12, x24.125) |
| 8 | 10 | 0.6222 | gene_id:ENSG00000282566.2 (2, x57.9); gene_symbol:PRAMEF25 (2, x57.9); biotype:protein_coding (10, x1.9761) |
| 9 | 10 | 0.6667 | gene_id:ENSG00000291380.1 (10, x48.25); gene_symbol:NECAP2 (10, x48.25); biotype:protein_coding (10, x1.9761) |
| 10 | 10 | 0.6889 | gene_id:ENSG00000291426.1 (10, x44.5385); gene_symbol:TOLLIP (10, x44.5385); biotype:protein_coding (10, x1.9761) |
| 11 | 9 | 0.6667 | gene_id:ENSG00000282482.1 (1, x64.3333); gene_symbol:IGHV2-70D (2, x64.3333); gene_family:IGHV (9, x5.4623); biotype:IG_V_gene (9, x2.4957) |

Interpretation: this graph is an alignment-derived BLAST-neighbor DRAG
view over the same sequence entities. It is a biological-rule baseline
for comparison with the pure vector-neighbor graph, not a text-style
embedding-only graph.
