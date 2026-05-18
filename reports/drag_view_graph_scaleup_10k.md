# DRAG View Graph Scale-Up: 1k to 10k

Date: 2026-05-15

Model/index: `dnagpt/OmniGene-4-CPT-v2-merged` BF16 sequence-window Chroma
collections.

Recipe: `text_style_vector_neighbors`.

Biological rules used: `false`. Edges are pure vector-neighbor DRAG edges, not
BLAST, domain, pathway, or curated biological-rule edges.

## Protocol

Commands:

```bash
python -m dnarag.cli build-view-graph \
  --config configs/standard.yaml \
  --target dna_sequence_window \
  --limit 10000 \
  --neighbors 5 \
  --output indexes/standard/graph/views/dna_sequence_window_10k.sqlite

python -m dnarag.cli build-view-graph \
  --config configs/standard.yaml \
  --target protein_sequence_window \
  --limit 10000 \
  --neighbors 5 \
  --output indexes/standard/graph/views/protein_sequence_window_10k.sqlite

python scripts/analyze_view_graph.py \
  --graph indexes/standard/graph/views/dna_sequence_window_10k.sqlite \
  --config configs/standard.yaml \
  --output-dir reports/figures \
  --prefix dna_sequence_window_10k \
  --analysis-only

python scripts/analyze_view_graph.py \
  --graph indexes/standard/graph/views/protein_sequence_window_10k.sqlite \
  --config configs/standard.yaml \
  --output-dir reports/figures \
  --prefix protein_sequence_window_10k \
  --analysis-only
```

The 10k graphs are analyzed without full spring-layout rendering. Full graph
statistics and community labels are computed; visualization should use sampled
subgraphs or community summaries.

## Graph Summary

| View | Input windows | Entity nodes | Undirected edges | Components | Largest component | Communities | Modularity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DNA/cDNA 1k | 1,000 | 170 | 2,499 | 1 | 170 | 3 | 0.2998 |
| DNA/cDNA 10k | 10,000 | 579 | 19,344 | 2 | 571 | 9 | 0.1741 |
| Protein 1k | 1,000 | 340 | 2,938 | 1 | 340 | 5 | 0.3342 |
| Protein 10k | 10,000 | 2,623 | 31,794 | 2 | 2,617 | 16 | 0.3179 |

Input sequence windows are collapsed to sequence entity nodes in the view graph.
This is why the DNA/cDNA 10k graph has 579 entity nodes rather than 10,000
nodes: many windows come from the same transcript/gene sequence entity. The
collapsed graph is useful for biological interpretation, while the window-level
retrieval collection remains the 100k-vector Chroma index.

## Main 10k Biological Signals

DNA/cDNA 10k:

| Community | Size | Dominant signal |
| ---: | ---: | --- |
| 2 | 66 | `IGKV`: 50 nodes, enrichment x6.178; `IG_V_gene`: 65 nodes, enrichment x2.4579 |
| 3 | 21 | `IGHV`: 19 nodes, enrichment x4.942; `IG_V_gene`: 21 nodes, enrichment x2.4957 |
| 4 | 8 | `IG_D_gene`: 8 nodes, enrichment x26.3182; `IGHD3-3`: 2 nodes, enrichment x72.375 |
| 5 | 6 | `IG_D_gene`: 6 nodes, enrichment x26.3182; `IGHD2-15`: 2 nodes, enrichment x96.5 |
| 7 | 4 | `IG_J_gene`: 4 nodes, enrichment x24.125; `IGHJ1`: 2 nodes, enrichment x144.75 |

Protein 10k:

| Community | Size | Dominant signal |
| ---: | ---: | --- |
| 0 | 1,115 | `acdS`: 46 nodes, enrichment x2.3525 |
| 1 | 756 | `ORF1a`: 15 nodes, enrichment x3.4696 |
| 2 | 306 | `pgl`: 51 nodes, enrichment x4.4158 |
| 3 | 226 | `yfbR`: 42 nodes, enrichment x11.6062 |
| 4 | 52 | `nbaC`: 7 nodes, enrichment x17.6548 |
| 6 | 43 | `MGF`: 3 nodes, enrichment x45.75 |
| 8 | 15 | `nbaC`: 5 nodes, enrichment x43.7167 |

Single-node labels with very high enrichment are treated as exploratory only
and are not used as headline claims.

## Interpretation

- The 10k run strengthens the DRAG story because the pure vector-neighbor recipe
  still produces label-enriched communities after scaling beyond the 1k figure.
- DNA/cDNA changes from a compact 1k immunoglobulin-variable view into a broader
  graph with distinct `IGKV`, `IGHV`, `IG_D_gene`, and `IG_J_gene` modules.
- Protein remains more heterogeneous, but the 10k graph shows several multi-node
  enriched communities rather than only isolated labels.
- The lower DNA/cDNA modularity at 10k is expected because the graph includes
  more protein-coding and immune-region entities, and many windows collapse to
  shared transcript/gene sequence nodes.
- This remains a hypothesis-generating graph representation result. It does not
  replace BLAST and does not prove biological mechanism by itself.

## Paper Use

Use the 1k SVG as the readable figure and the 10k table as the scale-up
evidence. The combined claim is stronger than either alone:

- 1k figure: visually clear DRAG modules from pure vector-neighbor graph
  construction.
- 10k analysis: the same construction scales and preserves multi-node
  label-enriched modules.

Next ablations:

- Compare pure vector edges with BLAST-edge, domain/Pfam, GO, and pathway
  rule-enriched DRAG graphs.
- Build sampled visualizations from the 10k graph by selecting communities or
  k-core subgraphs rather than drawing the entire graph.
- Add agent-context evaluation: whether graph paths improve answer grounding
  over vector-only retrieval.

Machine-readable outputs:

- `reports/figures/dna_sequence_window_10k_analysis.json`
- `reports/figures/protein_sequence_window_10k_analysis.json`
