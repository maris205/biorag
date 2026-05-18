# DRAG View Graph Visualization

Date: 2026-05-15

Input graphs:

- `indexes/standard/graph/views/dna_sequence_window_1k.sqlite`
- `indexes/standard/graph/views/protein_sequence_window_1k.sqlite`

Recipe: `text_style_vector_neighbors`.

Biological rules used: `false`. Edges are pure vector-neighbor DRAG edges, not
BLAST, domain, pathway, or curated biology rules.

## Outputs

Paper-style combined figure:

- SVG: `reports/figures/drag_paper_knowledge_graph.svg`
- Interactive HTML: `reports/figures/drag_paper_knowledge_graph.html`
- Analysis: `reports/figures/drag_paper_knowledge_graph_analysis.md`
- Machine-readable: `reports/figures/drag_paper_knowledge_graph_summary.json`

Scale-up analysis:

- 10k report: `reports/drag_view_graph_scaleup_10k.md`
- Vector-vs-BLAST ablation: `reports/drag_blast_ablation_10k.md`
- Hybrid vector+BLAST graph: `reports/drag_hybrid_graph_10k.md`
- Agent trace context comparison: `reports/drag_agent_trace_10k.md`
- DNA/cDNA 10k analysis: `reports/figures/dna_sequence_window_10k_analysis.md`
- Protein 10k analysis: `reports/figures/protein_sequence_window_10k_analysis.md`
- DNA/cDNA BLAST-neighbor 10k analysis: `reports/figures/dna_sequence_window_blast_10k_analysis.md`
- Protein BLAST-neighbor 10k analysis: `reports/figures/protein_sequence_window_blast_10k_analysis.md`
- DNA/cDNA hybrid 10k analysis: `reports/figures/dna_sequence_window_hybrid_10k_analysis.md`
- Protein hybrid 10k analysis: `reports/figures/protein_sequence_window_hybrid_10k_analysis.md`

DNA/cDNA view:

- Interactive HTML: `reports/figures/dna_sequence_window_1k_graph.html`
- Standalone SVG: `reports/figures/dna_sequence_window_1k_graph.svg`
- Analysis: `reports/figures/dna_sequence_window_1k_analysis.md`
- Machine-readable: `reports/figures/dna_sequence_window_1k_analysis.json`

Protein view:

- Interactive HTML: `reports/figures/protein_sequence_window_1k_graph.html`
- Standalone SVG: `reports/figures/protein_sequence_window_1k_graph.svg`
- Analysis: `reports/figures/protein_sequence_window_1k_analysis.md`
- Machine-readable: `reports/figures/protein_sequence_window_1k_analysis.json`

## Graph Summary

| View | Nodes | Edges | Components | Communities | Modularity |
| --- | ---: | ---: | ---: | ---: | ---: |
| DNA/cDNA windows | 170 | 2499 | 1 | 3 | 0.2998 |
| Protein windows | 340 | 2938 | 1 | 5 | 0.3342 |

The view graph builder now skips duplicate-entity self-loop edges before
analysis. The combined paper figure uses the full graph for layout and
statistics, but renders a 900-edge high-confidence visual backbone per panel for
readability.

## Biological Signals

DNA/cDNA graph:

| Community | Size | Dominant signal |
| ---: | ---: | --- |
| 0 | 81 | `IGLV` family: 44 nodes, enrichment x2.0521 |
| 1 | 62 | `IGHV` family: 58 nodes, enrichment x1.7286 |
| 2 | 27 | `IGHV` family: 25 nodes, enrichment x1.711; `IGHV1-69` gene symbol enrichment x6.2963, hypergeom p=0.024434 |

Protein graph:

| Community | Size | Dominant signal |
| ---: | ---: | --- |
| 1 | 81 | `YWHAB`: 5 nodes, enrichment x4.1975, hypergeom p=0.000697 |
| 3 | 46 | `MGF`: 3 nodes, enrichment x5.5435, hypergeom p=0.008457 |
| 4 | 11 | `IIV6-026R`: 1 node, enrichment x30.9091 |

Small protein communities with one repeated label should be treated as
hypothesis-generating only. The stronger current protein signals are the
`YWHAB` and `MGF` communities because they include multiple labeled nodes and
low enrichment p-values.

## Interpretation

- The DNA/cDNA graph is the cleanest figure candidate: a pure vector-neighbor
  DRAG graph separates immunoglobulin light-chain and heavy-chain variable
  family neighborhoods without using BLAST or curated biological-rule edges.
- The protein graph is more heterogeneous but still forms non-random communities
  with identifiable labels, including a `YWHAB`-enriched community.
- This supports the paper framing that vector DRAG is a biological
  representation layer and not just a retrieval speed trick.
- The claim should remain careful: this is evidence of label-enriched
  neighborhoods and graph modules, not proof of biological mechanism.

## Paper Figure Caption Draft

**Figure X. Sequence-derived DRAG view graphs reveal label-enriched biological
neighborhoods under a text-style vector-neighbor recipe.** Each node represents
a sequence window collapsed to a sequence entity, and each edge is induced by
nearest-neighbor similarity in the BF16 OmniGene embedding space. No BLAST,
domain, pathway, or curated biological-rule edges are used. The DNA/cDNA panel
forms three communities with clear immunoglobulin variable-family structure
(`IGLV` and `IGHV`). The protein panel is more heterogeneous, but still contains
multi-node enriched modules such as `YWHAB` and `MGF`. The result should be
interpreted as hypothesis-generating evidence that DRAG can expose biological
structure from a unified sequence/text embedding space, not as a replacement for
alignment-based biological search.

## 中文解读

这张图可以作为论文里“DRAG 不只是搜索增强，也可能形成有生物学意义的视图图谱”的第一张核心证据图。关键点是构图方法刻意保持朴素：按照普通文本 RAG 的做法，把向量近邻连成图，没有使用 BLAST、结构域、通路或任何人工生物规则。即便如此，DNA/cDNA 图里仍然出现了相对清晰的免疫球蛋白变量区家族分群，说明生物序列 embedding 的邻域结构并不是完全随机的。

蛋白图目前比 DNA/cDNA 更复杂，社区也更异质，但 `YWHAB` 和 `MGF` 这类多节点富集模块值得保留。论文中建议把这部分表述为“label-enriched modules / hypothesis-generating biological neighborhoods”，不要直接说发现了机制。后续如果加入 GO、Pfam/domain、Reactome pathway 或 BLAST-edge 对照，就可以进一步判断这些向量图谱模块是否对应已知功能、结构域或进化关系。

## Next Analyses

- Build larger 10k view graphs with approximate layout or sampled subgraphs.
- Add GO/pathway labels to protein nodes where mappings exist.
- Compare pure vector-neighbor graphs against BLAST-edge and domain-rule
  enriched graphs as ablations.
- Evaluate graph path utility in agent answer grounding.
