# DRAG View Graph Analysis: protein_sequence_window_10k.sqlite

## Summary

- Target: `protein_sequence_window`
- Recipe: `text_style_vector_neighbors`
- Biological rules used: `false`
- Nodes: `2623`
- Edges: `31794` undirected from `37371` edge rows
- Connected components: `2`
- Largest component: `2617`
- Communities: `16`
- Modularity: `0.3179`

## Top Communities

| Community | Size | Density | Top gene/symbol/family/biotype labels |
| ---: | ---: | ---: | --- |
| 0 | 1115 | 0.0145 | gene_symbol:acdS (46, x2.3525) |
| 1 | 756 | 0.0276 | gene_symbol:ORF1a (15, x3.4696) |
| 2 | 306 | 0.0353 | gene_symbol:pgl (51, x4.4158) |
| 3 | 226 | 0.0626 | gene_symbol:yfbR (42, x11.6062) |
| 4 | 52 | 0.0980 | gene_symbol:nbaC (7, x17.6548) |
| 5 | 47 | 0.0999 | gene_symbol:IIV6-384L (1, x55.8085) |
| 6 | 43 | 0.1019 | gene_symbol:MGF (3, x45.75) |
| 7 | 19 | 0.4678 | gene_symbol:SaurJH9_2368 (1, x138.0526) |
| 8 | 15 | 0.2667 | gene_symbol:nbaC (5, x43.7167) |
| 9 | 8 | 0.9286 | gene_symbol:BOV_A0688 (1, x327.875) |
| 10 | 8 | 0.7143 | gene_symbol:RrIowa_0572 (1, x327.875) |
| 11 | 7 | 1.0000 | gene_symbol:CLI_1349 (1, x374.7143) |

Interpretation: this graph is a text-style vector-neighbor DRAG view.
Edges are not BLAST/domain/pathway biological rules. Community labels are
therefore evidence of neighborhood structure that emerges from the vector
representation and graph recipe, not proof of a biological mechanism.
