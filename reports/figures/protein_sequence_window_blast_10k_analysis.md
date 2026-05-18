# DRAG View Graph Analysis: protein_sequence_window_blast_10k.sqlite

## Summary

- Target: `protein_sequence_window`
- Recipe: `blast_sequence_neighbors`
- Biological rules used: `true`
- Nodes: `2623`
- Edges: `7572` undirected from `10921` edge rows
- Connected components: `421`
- Largest component: `496`
- Communities: `447`
- Modularity: `0.9721`

## Top Communities

| Community | Size | Density | Top gene/symbol/family/biotype labels |
| ---: | ---: | ---: | --- |
| 0 | 118 | 0.0597 | gene_symbol:IIV6-300R (1, x22.2288) |
| 1 | 104 | 0.0736 | gene_symbol:ORF2b (1, x6.3053) |
| 2 | 92 | 0.0719 | gene_symbol:Cpha266_2098 (1, x28.5109) |
| 3 | 90 | 0.0779 | gene_symbol:WNTX10 (1, x29.1444) |
| 4 | 70 | 0.1039 | - |
| 5 | 62 | 0.1137 | gene_symbol:YWHAE (4, x42.3065) |
| 6 | 60 | 0.1209 | gene_symbol:gnd (37, x43.7167) |
| 7 | 55 | 0.1104 | gene_symbol:HTR1D (5, x47.6909) |
| 8 | 50 | 0.1437 | gene_symbol:YWHAB (6, x52.46) |
| 9 | 50 | 0.1282 | gene_symbol:pgl (27, x14.3073) |
| 10 | 49 | 0.1514 | gene_symbol:4CL1 (7, x53.5306) |
| 11 | 43 | 0.1927 | gene_symbol:pgl (43, x26.4949) |

Interpretation: this graph is an alignment-derived BLAST-neighbor DRAG
view over the same sequence entities. It is a biological-rule baseline
for comparison with the pure vector-neighbor graph, not a text-style
embedding-only graph.
