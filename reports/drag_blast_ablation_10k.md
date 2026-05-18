# DRAG Ablation: Vector-Neighbor vs BLAST-Neighbor Graphs

Date: 2026-05-15

Purpose: compare a pure text-style vector-neighbor DRAG graph against an
alignment-derived BLAST-neighbor graph on the same sequence entity nodes.

This is not a replacement test. BLAST is the biologically grounded alignment
baseline. The ablation asks whether the vector graph provides a complementary
graph structure for BioRAG/DRAG and agent context construction.

## Protocol

Starting point:

- DNA/cDNA vector graph: `indexes/standard/graph/views/dna_sequence_window_10k.sqlite`
- Protein vector graph: `indexes/standard/graph/views/protein_sequence_window_10k.sqlite`

For each vector graph, the same collapsed sequence entity nodes were copied to a
new graph. Node `description` sequence fragments were exported to FASTA,
temporary BLAST databases were built, and top BLAST neighbors were converted to
`blast_neighbor` edges.

Commands:

```bash
python scripts/build_blast_view_graph.py \
  --input-graph indexes/standard/graph/views/dna_sequence_window_10k.sqlite \
  --output indexes/standard/graph/views/dna_sequence_window_blast_10k.sqlite \
  --neighbors 5 \
  --blast-max-targets 25 \
  --min-identity 30 \
  --min-alignment-fraction 0.5

python scripts/build_blast_view_graph.py \
  --input-graph indexes/standard/graph/views/protein_sequence_window_10k.sqlite \
  --output indexes/standard/graph/views/protein_sequence_window_blast_10k.sqlite \
  --neighbors 5 \
  --blast-max-targets 25 \
  --min-identity 25 \
  --min-alignment-fraction 0.5
```

The BLAST graphs use the same node sets as the vector graphs. Only the edge
recipe changes.

## Graph-Level Results

| Modality | Edge recipe | Nodes | Undirected edges | Components | Largest component | Communities | Modularity | Avg degree |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DNA/cDNA | vector neighbors | 579 | 19,344 | 2 | 571 | 9 | 0.1741 | 66.8187 |
| DNA/cDNA | BLAST neighbors | 579 | 995 | 219 | 46 | 220 | 0.9383 | 3.4370 |
| Protein | vector neighbors | 2,623 | 31,794 | 2 | 2,617 | 16 | 0.3179 | 24.2425 |
| Protein | BLAST neighbors | 2,623 | 7,572 | 421 | 496 | 447 | 0.9721 | 5.7735 |

## Main Biological Signals

DNA/cDNA vector graph:

- `IGKV`: 50 nodes in one community, enrichment x6.178.
- `IGHV`: 19 nodes in one community, enrichment x4.942.
- `IG_D_gene` and `IG_J_gene` also appear as smaller enriched modules.

DNA/cDNA BLAST graph:

- `IGHV`: 42 nodes in the largest community, enrichment x4.9873.
- `IGKV`: 28 nodes in one community, enrichment x7.8737.
- `IGLV`: 15 nodes in one community, enrichment x12.8667.
- `IGHJ6`/`IG_J_gene` forms a compact J-gene module.

Protein vector graph:

- `acdS`: 46 nodes, enrichment x2.3525.
- `pgl`: 51 nodes, enrichment x4.4158.
- `yfbR`: 42 nodes, enrichment x11.6062.
- `nbaC`: 7 nodes, enrichment x17.6548.
- `MGF`: 3 nodes, enrichment x45.75.

Protein BLAST graph:

- `gnd`: 37 nodes, enrichment x43.7167.
- `pgl`: 27 and 43 node modules in separate BLAST communities.
- `YWHAB`: 6 nodes, enrichment x52.46.
- `YWHAE`: 4 nodes, enrichment x42.3065.
- `HTR1D`: 5 nodes, enrichment x47.6909.

Single-node high-enrichment labels are exploratory and are not headline claims.

## Interpretation

The two graph recipes expose different structure:

- BLAST-neighbor graphs are sparse, highly modular, and fragmented. This is
  expected for an alignment-derived biological baseline. They produce compact
  high-confidence local neighborhoods and many small components.
- Vector-neighbor graphs are much more connected. They create broader
  candidate-neighborhood structure over the same biological entities, which is
  better suited for RAG/DRAG expansion and agent context construction.
- The vector graph does not need to beat or replace BLAST. Its value is that it
  can unify sequence, text, and later structure/image modalities in one
  retrieval graph while still showing biologically labeled neighborhoods.
- BLAST-edge graphs should be used as a biologically grounded ablation and as a
  possible rule-enriched DRAG layer, not as the only retrieval substrate.

## Paper Framing

The key paper point is complementarity:

> Alignment-derived BLAST graphs recover precise local sequence-similarity
> neighborhoods, while OmniGene vector-neighbor graphs form broader connected
> biological representation neighborhoods. The latter are useful for multimodal
> BioRAG/DRAG and agent workflows because they can be constructed uniformly over
> biological sequences, natural-language text, and future structural or visual
> modalities.

This ablation strengthens the claim that DRAG is not merely a search module. It
can be studied as a graph view of the biological representation space. The
correct claim is “biologically enriched graph modules emerge under a simple
text-style vector recipe,” not “vector search replaces BLAST.”

## Outputs

- DNA/cDNA vector analysis: `reports/figures/dna_sequence_window_10k_analysis.md`
- DNA/cDNA BLAST analysis: `reports/figures/dna_sequence_window_blast_10k_analysis.md`
- Protein vector analysis: `reports/figures/protein_sequence_window_10k_analysis.md`
- Protein BLAST analysis: `reports/figures/protein_sequence_window_blast_10k_analysis.md`
- DNA/cDNA BLAST graph: `indexes/standard/graph/views/dna_sequence_window_blast_10k.sqlite`
- Protein BLAST graph: `indexes/standard/graph/views/protein_sequence_window_blast_10k.sqlite`

Follow-up hybrid graph report:

- `reports/drag_hybrid_graph_10k.md`
