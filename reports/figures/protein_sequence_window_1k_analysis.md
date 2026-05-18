# DRAG View Graph Analysis: protein_sequence_window_1k.sqlite

## Summary

- Target: `protein_sequence_window`
- Recipe: `text_style_vector_neighbors`
- Biological rules used: `false`
- Nodes: `340`
- Edges: `2938` undirected from `3567` edge rows
- Connected components: `1`
- Largest component: `340`
- Communities: `5`
- Modularity: `0.3342`

## Top Communities

| Community | Size | Density | Top gene/symbol/family/biotype labels |
| ---: | ---: | ---: | --- |
| 0 | 146 | 0.1147 | gene_symbol:FV3-039R (1, x2.3288) |
| 1 | 81 | 0.1861 | gene_symbol:YWHAB (5, x4.1975) |
| 2 | 56 | 0.0903 | gene_symbol:IIV3-103L (1, x6.0714) |
| 3 | 46 | 0.1159 | gene_symbol:MGF (3, x5.5435) |
| 4 | 11 | 0.1818 | gene_symbol:IIV6-026R (1, x30.9091) |

Interpretation: this graph is a text-style vector-neighbor DRAG view.
Edges are not BLAST/domain/pathway biological rules. Community labels are
therefore evidence of neighborhood structure that emerges from the vector
representation and graph recipe, not proof of a biological mechanism.
