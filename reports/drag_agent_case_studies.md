# DRAG Agent Case Studies

Date: 2026-05-16

Purpose: turn the existing DRAG graph traces into agent-facing evidence case
studies. These examples do not call an LLM. They define the evidence contract
that a biomedical agent can consume after BioRAG retrieval.

## Agent Evidence Contract

For sequence or mixed biomedical queries, the system should expose evidence as
typed routes:

```text
query
  -> vector candidates and instant context
  -> BLAST-supported candidate verification
  -> DRAG graph expansion with typed edges
  -> citation-ready evidence pack
```

The important design rule is that route labels are preserved. A downstream
agent should know whether an edge is `vector_neighbor`, `blast_neighbor`, text
evidence, or curated graph evidence.

## Case Study 1: DNA/cDNA Immunoglobulin Module

Focus label: `IGKV2-40`

| Graph | Avg context nodes | Avg context edges | Avg same-label neighbor hits | Relation evidence |
| --- | ---: | ---: | ---: | --- |
| vector | 13.0000 | 12.0000 | 2.0000 | vector 36 |
| BLAST | 4.0000 | 3.0000 | 2.0000 | BLAST 9 |
| hybrid | 10.3333 | 12.0000 | 2.0000 | BLAST 9; vector 27 |

Interpretation: BLAST gives a compact local alignment neighborhood. Vector
gives broader context. Hybrid keeps the BLAST-supported neighbors and adds
representation-neighbor context for RAG expansion.

## Case Study 2: Protein `pgl` Module

| Graph | Avg context nodes | Avg context edges | Avg same-label neighbor hits | Relation evidence |
| --- | ---: | ---: | ---: | --- |
| vector | 12.6667 | 11.6667 | 9.6667 | vector 35 |
| BLAST | 7.6667 | 6.6667 | 6.6667 | BLAST 20 |
| hybrid | 10.6667 | 12.0000 | 9.6667 | BLAST 20; vector 16 |

Interpretation: vector-only context recovers many same-label protein neighbors,
while BLAST provides alignment-labeled support. Hybrid gives the agent both the
broader neighborhood and typed alignment evidence.

## Case Study 3: Protein `yfbR` Module

| Graph | Avg context nodes | Avg context edges | Avg same-label neighbor hits | Relation evidence |
| --- | ---: | ---: | ---: | --- |
| vector | 13.0000 | 12.0000 | 11.0000 | vector 36 |
| BLAST | 6.0000 | 5.0000 | 5.0000 | BLAST 15 |
| hybrid | 11.3333 | 12.0000 | 10.3333 | BLAST 15; vector 21 |

Interpretation: this is a strong example for agent use. Vector retrieval
provides a rich same-label neighborhood; BLAST contributes compact verification;
hybrid packages both as route-labeled graph context.

## How This Supports Plan 3

These traces support the instant/verified BioRAG design:

- **Instant mode:** vector neighbors can be returned quickly as provisional
  multimodal context.
- **Verified mode:** BLAST and hybrid DRAG attach alignment-supported and
  graph-supported evidence.
- **Agent mode:** typed graph paths make it possible to cite whether a claim is
  grounded in representation similarity, alignment evidence, or later curated
  annotations such as GO/pathway/domain/literature records.

## Next Agent Evaluation

The next step is to convert these traces into explicit multi-hop tasks in
BioRAG-Standard:

| Task type | Example expected behavior |
| --- | --- |
| sequence -> gene family | retrieve sequence neighbors, verify with BLAST, identify family-level graph context |
| sequence -> protein module | retrieve protein neighbors, distinguish vector and BLAST evidence |
| sequence -> pathway/function | retrieve sequence, expand to annotation/pathway text when available |
| mixed English + sequence | combine natural-language intent with sequence retrieval and graph evidence |

Metrics should include evidence grounding rate, citation correctness, route
coverage, and whether the answer distinguishes vector similarity from BLAST
alignment support.

## Outputs

- `reports/drag_agent_trace_10k.md`
- `reports/traces/dna_igkv2_40_vector_trace.json`
- `reports/traces/dna_igkv2_40_blast_trace.json`
- `reports/traces/dna_igkv2_40_hybrid_trace.json`
- `reports/traces/protein_pgl_vector_trace.json`
- `reports/traces/protein_pgl_blast_trace.json`
- `reports/traces/protein_pgl_hybrid_trace.json`
- `reports/traces/protein_yfbr_vector_trace.json`
- `reports/traces/protein_yfbr_blast_trace.json`
- `reports/traces/protein_yfbr_hybrid_trace.json`
