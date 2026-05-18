# DRAG Paper Figure Analysis

This figure renders sequence-derived DRAG view graphs built with the
`text_style_vector_neighbors` recipe. Edges are vector-neighbor links only;
BLAST, domain, pathway, and curated biological-rule edges are not used.

## Figure Outputs

- SVG: `reports/figures/drag_paper_knowledge_graph.svg`
- HTML: `reports/figures/drag_paper_knowledge_graph.html`
- JSON: `reports/figures/drag_paper_knowledge_graph_summary.json`

## Panel Summary

| Panel | Nodes | Edges | Displayed edges | Communities | Modularity | Main signal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| DNA/cDNA sequence DRAG view | 170 | 2499 | 900 | 3 | 0.2998 | C1 IGHV x1.7286; C0 IGLV x2.0521; C2 IGHV x1.711 |
| Protein sequence DRAG view | 340 | 2938 | 900 | 5 | 0.3342 | C1 YWHAB x4.1975; C3 MGF x5.5435 |

## Interpretation

- DNA/cDNA is the strongest figure candidate: immunoglobulin variable-family neighborhoods are separated by a pure vector-neighbor graph recipe.
- Protein is more heterogeneous, but label-enriched modules are still visible; the clearest current example is the YWHAB-enriched community.
- The result supports DRAG as a hypothesis-generating biological representation layer for multimodal BioRAG, not as a replacement for BLAST.
- The next paper-grade ablation should compare pure vector edges with BLAST, domain, GO, and pathway rule-enriched DRAG graphs.
