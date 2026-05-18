# DRAG View Graph Analysis: dna_sequence_window_hybrid_10k.sqlite

## Summary

- Target: `dna_sequence_window`
- Recipe: `hybrid_vector_blast_neighbors`
- Biological rules used: `true`
- Nodes: `579`
- Edges: `19592` undirected from `26994` edge rows
- Connected components: `2`
- Largest component: `571`
- Communities: `7`
- Modularity: `0.1739`

## Top Communities

| Community | Size | Density | Top gene/symbol/family/biotype labels |
| ---: | ---: | ---: | --- |
| 0 | 257 | 0.1563 | gene_id:ENSG00000291428.1 (14, x2.1027); gene_symbol:BRSK2 (14, x2.1027); gene_family:IGHV (50, x1.0627); biotype:protein_coding (133, x1.0227) |
| 1 | 234 | 0.2338 | gene_id:ENSG00000281449.2 (14, x2.4744); gene_symbol:BCL2L14 (14, x2.4744); gene_family:IGHV (56, x1.3072); biotype:protein_coding (159, x1.3427) |
| 2 | 60 | 0.2774 | gene_id:ENSG00000282811.1 (2, x9.65); gene_symbol:IGKV1-33 (3, x9.65); gene_family:IGKV (51, x6.9317); biotype:IG_V_gene (59, x2.4541) |
| 3 | 12 | 0.5152 | gene_id:ENSG00000211904.2 (1, x48.25); gene_symbol:IGHJ2 (2, x48.25); biotype:IG_J_gene (12, x24.125) |
| 4 | 8 | 0.8571 | gene_id:ENSG00000282754.1 (1, x72.375); gene_symbol:IGHD3-3 (2, x72.375); biotype:IG_D_gene (8, x26.3182) |
| 5 | 4 | 1.0000 | gene_id:ENSG00000211597.2 (1, x144.75); gene_symbol:IGKJ1 (1, x144.75); biotype:IG_J_gene (4, x24.125) |
| 6 | 4 | 1.0000 | gene_id:ENSG00000211911.1 (1, x144.75); gene_symbol:IGHD3-22 (2, x144.75); biotype:IG_D_gene (4, x26.3182) |

Interpretation: this graph is a hybrid DRAG view combining vector
neighbors with BLAST-derived sequence-similarity edges over the same
sequence entities. It tests whether biological-rule edges sharpen local
modules while preserving vector-graph connectivity for RAG expansion.
