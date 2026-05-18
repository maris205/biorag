# DRAG Agent Trace: Vector vs BLAST vs Hybrid Context

Date: 2026-05-15

Purpose: evaluate graph-context traces that an agent could use after retrieval.
The experiment does not call an LLM. It compares the graph evidence available
from vector-only, BLAST-only, and hybrid vector+BLAST DRAG graphs for the same
biological labels.

## Protocol

For each label, seed nodes are found by biological labels extracted from Chroma
metadata (`gene_symbol`, `GN=`, gene family, biotype). For each seed, a one-hop
graph context is collected with up to 12 unique undirected evidence edges. The
trace records:

- context node count
- context edge count
- number of neighboring nodes carrying the same focus label
- relation types used in the trace

Example command:

```bash
python scripts/trace_graph_context.py \
  --graph indexes/standard/graph/views/protein_sequence_window_hybrid_10k.sqlite \
  --label pgl \
  --seed-limit 3 \
  --max-edges 12 \
  --output reports/traces/protein_pgl_hybrid_trace.json
```

## Trace Summary

| Label | Modality | Graph | Avg context nodes | Avg context edges | Avg same-label neighbor hits | Relation evidence |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `IGKV2-40` | DNA/cDNA | vector | 13.0000 | 12.0000 | 2.0000 | vector 36 |
| `IGKV2-40` | DNA/cDNA | BLAST | 4.0000 | 3.0000 | 2.0000 | BLAST 9 |
| `IGKV2-40` | DNA/cDNA | hybrid | 10.3333 | 12.0000 | 2.0000 | BLAST 9; vector 27 |
| `pgl` | protein | vector | 12.6667 | 11.6667 | 9.6667 | vector 35 |
| `pgl` | protein | BLAST | 7.6667 | 6.6667 | 6.6667 | BLAST 20 |
| `pgl` | protein | hybrid | 10.6667 | 12.0000 | 9.6667 | BLAST 20; vector 16 |
| `yfbR` | protein | vector | 13.0000 | 12.0000 | 11.0000 | vector 36 |
| `yfbR` | protein | BLAST | 6.0000 | 5.0000 | 5.0000 | BLAST 15 |
| `yfbR` | protein | hybrid | 11.3333 | 12.0000 | 10.3333 | BLAST 15; vector 21 |

## Interpretation

- BLAST-only traces are compact and precise. They provide fewer context nodes
  and edges, but those edges are alignment-derived and highly interpretable.
- Vector-only traces provide broader context. They often recover many same-label
  neighbors in protein modules, but all evidence is representation-neighbor
  evidence.
- Hybrid traces preserve the broader context budget while exposing both
  evidence types. This gives an agent a more useful context pack: BLAST edges
  can justify local sequence similarity, while vector edges can extend the
  neighborhood for multimodal RAG.

The `IGKV2-40` trace shows the clearest DNA/cDNA complementarity: BLAST-only
finds a compact exact/local neighborhood; vector-only expands to a broader
context; hybrid keeps the same BLAST-supported neighbors and adds vector
neighbors.

The `pgl` and `yfbR` traces show the same pattern in protein: hybrid keeps the
same-label recovery of vector-only while adding BLAST-supported edges that are
useful for evidence attribution.

## Agent Framing

For an agent system, the hybrid graph supports evidence-aware retrieval:

1. Use `blast_neighbor` paths when the answer needs local alignment support.
2. Use `vector_neighbor` paths when the answer needs broader candidate expansion
   or multimodal context.
3. Preserve edge types in citations so the downstream answer can distinguish
   representation similarity from biological alignment evidence.

This is the operational reason to use DRAG rather than a single retrieval list:
the graph can carry typed evidence paths, not just ranked documents.

## Outputs

- `reports/traces/dna_igkv2_40_vector_trace.json`
- `reports/traces/dna_igkv2_40_blast_trace.json`
- `reports/traces/dna_igkv2_40_hybrid_trace.json`
- `reports/traces/protein_pgl_vector_trace.json`
- `reports/traces/protein_pgl_blast_trace.json`
- `reports/traces/protein_pgl_hybrid_trace.json`
- `reports/traces/protein_yfbr_vector_trace.json`
- `reports/traces/protein_yfbr_blast_trace.json`
- `reports/traces/protein_yfbr_hybrid_trace.json`
