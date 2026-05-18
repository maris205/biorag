# DRAG Hybrid Graph: Vector + BLAST Edges

Date: 2026-05-15

Purpose: test whether adding BLAST-derived sequence-similarity edges to the
pure vector-neighbor DRAG graph sharpens local biological modules while
preserving the broad connectivity that makes vector DRAG useful for RAG and
agent context expansion.

## Protocol

Hybrid graphs are built by merging same-node vector and BLAST view graphs while
preserving relation types:

```bash
python scripts/merge_view_graphs.py \
  --base-graph indexes/standard/graph/views/dna_sequence_window_10k.sqlite \
  --overlay-graph indexes/standard/graph/views/dna_sequence_window_blast_10k.sqlite \
  --output indexes/standard/graph/views/dna_sequence_window_hybrid_10k.sqlite

python scripts/merge_view_graphs.py \
  --base-graph indexes/standard/graph/views/protein_sequence_window_10k.sqlite \
  --overlay-graph indexes/standard/graph/views/protein_sequence_window_blast_10k.sqlite \
  --output indexes/standard/graph/views/protein_sequence_window_hybrid_10k.sqlite
```

The output graph keeps `vector_neighbor` and `blast_neighbor` as separate edge
types.

## Graph-Level Results

| Modality | Edge recipe | Nodes | Undirected edges | Edge rows by type | Components | Largest component | Communities | Modularity | Avg degree |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| DNA/cDNA | vector only | 579 | 19,344 | vector 25,349 | 2 | 571 | 9 | 0.1741 | 66.8187 |
| DNA/cDNA | BLAST only | 579 | 995 | BLAST 1,645 | 219 | 46 | 220 | 0.9383 | 3.4370 |
| DNA/cDNA | hybrid | 579 | 19,592 | vector 25,349; BLAST 1,645 | 2 | 571 | 7 | 0.1739 | 67.6753 |
| Protein | vector only | 2,623 | 31,794 | vector 37,371 | 2 | 2,617 | 16 | 0.3179 | 24.2425 |
| Protein | BLAST only | 2,623 | 7,572 | BLAST 10,921 | 421 | 496 | 447 | 0.9721 | 5.7735 |
| Protein | hybrid | 2,623 | 35,549 | vector 37,371; BLAST 10,921 | 1 | 2,623 | 12 | 0.3779 | 27.1056 |

## Main Hybrid Signals

DNA/cDNA hybrid graph:

- `IGKV`: 51 nodes in a 60-node community, enrichment x6.9317.
- `IG_J_gene`: 12 nodes in one compact community, enrichment x24.125.
- `IG_D_gene`: 8-node and 4-node compact communities, enrichment x26.3182.
- The graph keeps the same largest component size as vector-only (571), so
  adding BLAST edges does not fragment the vector graph.

Protein hybrid graph:

- `gnd`: 23 nodes in one community, enrichment x3.0251.
- `pgl`: 71 nodes in one community, enrichment x3.6245.
- `yfbR`: 42 nodes in a 63-node community, enrichment x41.6349.
- `qutE`: 13 nodes in a 33-node community, enrichment x73.8074.
- The hybrid graph becomes fully connected (largest component 2,623) while
  modularity increases from 0.3179 to 0.3779 compared with vector-only.

## Interpretation

The hybrid graph gives the most practical engineering story:

- Vector-only DRAG supplies global connectivity and broad candidate expansion.
- BLAST-only DRAG supplies precise local alignment neighborhoods but fragments
  heavily.
- Hybrid DRAG keeps vector connectivity while injecting BLAST-supported local
  edges. In protein, this raises modularity and reduces the number of broad
  communities, suggesting sharper local structure without losing reachability.

For the paper, this supports a layered BioRAG/DRAG design:

1. Use vector search as a unified multimodal candidate layer.
2. Use BLAST/domain/pathway edges as biologically grounded graph refinements.
3. Let the agent retrieve across both edge types, with citations showing which
   evidence came from representation similarity and which came from biological
   alignment/rule evidence.

## Claim Boundary

This does not claim that vector search replaces BLAST. The result supports a
complementary architecture: vector DRAG provides a unified representation graph,
and BLAST edges add high-confidence biological locality.

## Outputs

- DNA/cDNA hybrid graph: `indexes/standard/graph/views/dna_sequence_window_hybrid_10k.sqlite`
- Protein hybrid graph: `indexes/standard/graph/views/protein_sequence_window_hybrid_10k.sqlite`
- DNA/cDNA hybrid analysis: `reports/figures/dna_sequence_window_hybrid_10k_analysis.md`
- Protein hybrid analysis: `reports/figures/protein_sequence_window_hybrid_10k_analysis.md`
- Agent trace report: `reports/drag_agent_trace_10k.md`
