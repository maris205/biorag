# Agent Evidence Case Study

This report summarizes existing DRAG trace JSON files into agent-facing evidence packs. No LLM is called; the goal is to show what a downstream biomedical agent can consume after BioRAG retrieval.

## Summary Table

| Case | Modality | Route | Avg nodes | Avg edges | Avg same-label hits | Relation evidence |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `IGKV2-40` | DNA/cDNA | vector | 13.0000 | 12.0000 | 2.0000 | vector_neighbor 36 |
| `IGKV2-40` | DNA/cDNA | blast | 4.0000 | 3.0000 | 2.0000 | blast_neighbor 9 |
| `IGKV2-40` | DNA/cDNA | hybrid | 10.3333 | 12.0000 | 2.0000 | blast_neighbor 9; vector_neighbor 27 |
| `pgl` | Protein | vector | 12.6667 | 11.6667 | 9.6667 | vector_neighbor 35 |
| `pgl` | Protein | blast | 7.6667 | 6.6667 | 6.6667 | blast_neighbor 20 |
| `pgl` | Protein | hybrid | 10.6667 | 12.0000 | 9.6667 | blast_neighbor 20; vector_neighbor 16 |
| `yfbR` | Protein | vector | 13.0000 | 12.0000 | 11.0000 | vector_neighbor 36 |
| `yfbR` | Protein | blast | 6.0000 | 5.0000 | 5.0000 | blast_neighbor 15 |
| `yfbR` | Protein | hybrid | 11.3333 | 12.0000 | 10.3333 | blast_neighbor 15; vector_neighbor 21 |

## Case Details

### DNA/cDNA immunoglobulin module

- Focus label: `IGKV2-40`
- Agent-style query: Given a local IGKV2-40 cDNA fragment, retrieve nearby sequence evidence and distinguish alignment-supported neighbors from representation-neighbor context.
- Evidence contract:
  - Instant context: vector_neighbor edges supply provisional neighborhood context.
  - Verified context: blast_neighbor edges supply alignment-labeled verification evidence.
  - Boundary: The downstream agent may describe retrieved neighborhoods and route support, but should not infer function, mechanism, or clinical meaning unless annotation/literature evidence is present.

Representative hybrid edges:

| Source | Target | Relation | Confidence | pident | bitscore | Target labels |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `ENST00000620613.1` | `ENST00000429992.3` | `blast_neighbor` | 1 | 100 | 157 | IGKV, IGKV2D-40, IG_V_gene |
| `ENST00000620613.1` | `ENST00000632384.1` | `blast_neighbor` | 1 | 100 | 254 | IGKV, IGKV2-40, IG_V_gene |
| `ENST00000620613.1` | `ENST00000632811.1` | `blast_neighbor` | 1 | 100 | 238 | IGKV, IGKV2-40, IG_V_gene |
| `ENST00000620613.1` | `ENST00000632384.1` | `vector_neighbor` | 0.9984 | - | - | IGKV, IGKV2-40, IG_V_gene |
| `ENST00000620613.1` | `ENST00000429992.3` | `vector_neighbor` | 0.9922 | - | - | IGKV, IGKV2D-40, IG_V_gene |
| `ENST00000620613.1` | `ENST00000468494.1` | `vector_neighbor` | 0.9917 | - | - | IGKV, IGKV2-30, IG_V_gene |

Answer skeleton:

- BioRAG-DRAG retrieved a DNA/cDNA neighborhood for IGKV2-40 with 10.3 average context nodes and 12.0 average typed edges.
- The hybrid trace includes 9 BLAST-labeled edges and 27 vector-neighbor edges across the sampled seeds.
- Average same-label neighbor recovery is 2.0; example neighbors include ENST00000429992.3 via blast_neighbor, ENST00000632384.1 via blast_neighbor, ENST00000632811.1 via blast_neighbor.
- This supports an evidence-pack answer, not a mechanistic claim: the agent should cite BLAST edges for local alignment support and vector edges for broader candidate context.

### Protein pgl module

- Focus label: `pgl`
- Agent-style query: Given a protein sequence neighborhood labeled pgl, collect local module evidence and expose which links are vector-derived versus alignment-derived.
- Evidence contract:
  - Instant context: vector_neighbor edges supply provisional neighborhood context.
  - Verified context: blast_neighbor edges supply alignment-labeled verification evidence.
  - Boundary: The downstream agent may describe retrieved neighborhoods and route support, but should not infer function, mechanism, or clinical meaning unless annotation/literature evidence is present.

Representative hybrid edges:

| Source | Target | Relation | Confidence | pident | bitscore | Target labels |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `A1A909` | `B7MGM4` | `blast_neighbor` | 1 | 100 | 269 | pgl |
| `A1A909` | `B7MPQ2` | `blast_neighbor` | 1 | 100 | 269 | pgl |
| `A1A909` | `B7ULP0` | `blast_neighbor` | 1 | 100 | 269 | pgl |
| `A1A909` | `B1IXL9` | `vector_neighbor` | 1 | - | - | pgl |
| `A1A909` | `Q0TJT3` | `vector_neighbor` | 1 | - | - | pgl |
| `A1A909` | `Q8FJR2` | `vector_neighbor` | 1 | - | - | pgl |

Answer skeleton:

- BioRAG-DRAG retrieved a Protein neighborhood for pgl with 10.7 average context nodes and 12.0 average typed edges.
- The hybrid trace includes 20 BLAST-labeled edges and 16 vector-neighbor edges across the sampled seeds.
- Average same-label neighbor recovery is 9.7; example neighbors include B7MGM4 via blast_neighbor, B7MPQ2 via blast_neighbor, B7ULP0 via blast_neighbor.
- This supports an evidence-pack answer, not a mechanistic claim: the agent should cite BLAST edges for local alignment support and vector edges for broader candidate context.

### Protein yfbR module

- Focus label: `yfbR`
- Agent-style query: Given a yfbR-like protein sequence, return a compact evidence pack that preserves both broad neighborhood context and BLAST-supported verification edges.
- Evidence contract:
  - Instant context: vector_neighbor edges supply provisional neighborhood context.
  - Verified context: blast_neighbor edges supply alignment-labeled verification evidence.
  - Boundary: The downstream agent may describe retrieved neighborhoods and route support, but should not infer function, mechanism, or clinical meaning unless annotation/literature evidence is present.

Representative hybrid edges:

| Source | Target | Relation | Confidence | pident | bitscore | Target labels |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `A1ADE0` | `B7MG55` | `blast_neighbor` | 1 | 100 | 275 | yfbR |
| `A1ADE0` | `B7MXX0` | `blast_neighbor` | 1 | 100 | 275 | yfbR |
| `A1ADE0` | `Q0TFF5` | `blast_neighbor` | 1 | 100 | 275 | yfbR |
| `A1ADE0` | `Q0TFF5` | `vector_neighbor` | 1 | - | - | yfbR |
| `A1ADE0` | `Q8FFJ5` | `vector_neighbor` | 1 | - | - | yfbR |
| `A1ADE0` | `A8A2G0` | `vector_neighbor` | 0.9998 | - | - | yfbR |

Answer skeleton:

- BioRAG-DRAG retrieved a Protein neighborhood for yfbR with 11.3 average context nodes and 12.0 average typed edges.
- The hybrid trace includes 15 BLAST-labeled edges and 21 vector-neighbor edges across the sampled seeds.
- Average same-label neighbor recovery is 10.3; example neighbors include B7MG55 via blast_neighbor, B7MXX0 via blast_neighbor, Q0TFF5 via blast_neighbor.
- This supports an evidence-pack answer, not a mechanistic claim: the agent should cite BLAST edges for local alignment support and vector edges for broader candidate context.

## Paper Interpretation

- Vector traces provide instant neighborhood context but do not by themselves prove alignment or function.
- BLAST traces provide compact alignment-labeled evidence.
- Hybrid DRAG gives an agent a single evidence pack that keeps both route labels visible.
- The answer boundary is explicit: without annotation, GO/pathway, domain, or literature evidence, the agent should describe retrieved sequence neighborhoods rather than infer mechanism.
