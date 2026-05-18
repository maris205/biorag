# DRAG View Graph Analysis: dna_sequence_window_1k.sqlite

## Summary

- Target: `dna_sequence_window`
- Recipe: `text_style_vector_neighbors`
- Biological rules used: `false`
- Nodes: `170`
- Edges: `2499` undirected from `3341` edge rows
- Connected components: `1`
- Largest component: `170`
- Communities: `3`
- Modularity: `0.2998`

## Top Communities

| Community | Size | Density | Top gene/symbol/family/biotype labels |
| ---: | ---: | ---: | --- |
| 0 | 81 | 0.2432 | gene_id:ENSG00000282811.1 (2, x2.0988); gene_symbol:IGLV5-45 (2, x2.0988); gene_family:IGLV (44, x2.0521); biotype:IG_V_gene (81, x1.0) |
| 1 | 62 | 0.3644 | gene_id:ENSG00000278042.2 (2, x2.7419); gene_symbol:IGHV6-1 (2, x2.7419); gene_family:IGHV (58, x1.7286); biotype:IG_V_gene (62, x1.0) |
| 2 | 27 | 0.6154 | gene_id:ENSG00000211973.2 (1, x6.2963); gene_symbol:IGHV1-69 (2, x6.2963); gene_family:IGHV (25, x1.711); biotype:IG_V_gene (27, x1.0) |

Interpretation: this graph is a text-style vector-neighbor DRAG view.
Edges are not BLAST/domain/pathway biological rules. Community labels are
therefore evidence of neighborhood structure that emerges from the vector
representation and graph recipe, not proof of a biological mechanism.
