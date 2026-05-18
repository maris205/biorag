# DRAG View Graph Analysis: dna_sequence_window_10k.sqlite

## Summary

- Target: `dna_sequence_window`
- Recipe: `text_style_vector_neighbors`
- Biological rules used: `false`
- Nodes: `579`
- Edges: `19344` undirected from `25349` edge rows
- Connected components: `2`
- Largest component: `571`
- Communities: `9`
- Modularity: `0.1741`

## Top Communities

| Community | Size | Density | Top gene/symbol/family/biotype labels |
| ---: | ---: | ---: | --- |
| 0 | 240 | 0.2210 | gene_id:ENSG00000281449.2 (14, x2.4125); gene_symbol:BCL2L14 (14, x2.4125); gene_family:IGHV (56, x1.2745); biotype:protein_coding (159, x1.3092) |
| 1 | 228 | 0.1759 | gene_id:ENSG00000291428.1 (14, x2.3702); gene_symbol:BRSK2 (14, x2.3702); gene_family:IGLV (31, x1.7494); biotype:protein_coding (133, x1.1527) |
| 2 | 66 | 0.2224 | gene_id:ENSG00000282182.1 (2, x8.7727); gene_symbol:IGKV1-33 (3, x8.7727); gene_family:IGKV (50, x6.178); biotype:IG_V_gene (65, x2.4579) |
| 3 | 21 | 0.6238 | gene_id:ENSG00000211961.3 (1, x27.5714); gene_symbol:IGHV1-46 (2, x27.5714); gene_family:IGHV (19, x4.942); biotype:IG_V_gene (21, x2.4957) |
| 4 | 8 | 0.8571 | gene_id:ENSG00000211930.1 (1, x72.375); gene_symbol:IGHD3-3 (2, x72.375); biotype:IG_D_gene (8, x26.3182) |
| 5 | 6 | 0.8000 | gene_id:ENSG00000211925.1 (1, x96.5); gene_symbol:IGHD2-8 (2, x96.5); biotype:IG_D_gene (6, x26.3182) |
| 6 | 4 | 1.0000 | gene_id:ENSG00000211911.1 (1, x144.75); gene_symbol:IGHD3-22 (2, x144.75); biotype:IG_D_gene (4, x26.3182) |
| 7 | 4 | 0.6667 | gene_id:ENSG00000282065.1 (1, x144.75); gene_symbol:IGHJ4 (2, x144.75); biotype:IG_J_gene (4, x24.125) |

Interpretation: this graph is a text-style vector-neighbor DRAG view.
Edges are not BLAST/domain/pathway biological rules. Community labels are
therefore evidence of neighborhood structure that emerges from the vector
representation and graph recipe, not proof of a biological mechanism.
