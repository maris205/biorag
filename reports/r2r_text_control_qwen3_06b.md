# Live R2R Ordinary Text-RAG Control

## Scope

This experiment is the ordinary semantic text-RAG application control requested
in `review2.md`. It does not replace a biological sequence baseline. The same 66
frozen raw-protein-sequence queries, Qwen3.5-9B executor, decoding settings, and
structured answer contract are used for every Agent route. Only retrieval and
the resulting evidence pack change.

The collection contains 14,071 documents: 1,901 index-protein records and
12,170 flattened sequence-to-annotation/literature records. All 99 held-out
parent accessions are absent from the index (exact accession overlap 0). R2R
graph, full-text, and hybrid search are disabled, leaving only generic semantic
text retrieval.

## Frozen Runtime

| Component | Frozen value |
|---|---|
| R2R | 3.6.6, collection `8e999977-1eb4-4b24-a6d9-ce833a0f5d21` |
| Database | PostgreSQL 14.24, pgvector 0.8.1 |
| Text embedder | `qwen3-embedding:0.6b`, 595.78M parameters, 1,024 dimensions |
| Artifact | Ollama 0.33.2, Q8_0, digest `ac6da0dfba84` |
| Generator | Qwen3.5-9B, BF16, fixed raw-evidence prompt |
| Main retrieval budget | 50 R2R chunks; five unique candidates enter the prompt |

The result JSON records the sanitized R2R settings, dependency versions, corpus
manifest, collection size, and leakage audit. API latency includes server-side
query embedding and pgvector lookup.

## Raw Results

| Condition | Candidate Hit | Candidate recall | GO prompt recall | PMID prompt recall | Mean / P50 / P95 retrieval ms |
|---|---:|---:|---:|---:|---:|
| R2R semantic text, top 50 (main) | 0.000 | 0.000 | 0.000 | 0.000 | 833.2 / 754.9 / 1431.6 |
| R2R semantic text, top 200 (diagnostic) | 0.121 | 0.039 | 0.000 | 0.000 | 1022.8 / 1029.0 / 1496.2 |

At top 50, each query returns 50 chunks and 22--50 unique accessions (mean
38.68). The observed candidate budget would produce an expected 5.46 hits over
66 queries under independent uniform sampling, whereas this retriever produces
zero. That calculation is a diagnostic reference, not a formal null test,
because dense ranks are neither independent nor uniformly sampled.

## Integrity Diagnostics

The zero main-task result is not caused by missing records or metadata parsing:

| Diagnostic | Result |
|---|---:|
| Five natural-language accession/title queries | 5/5 target proteins at rank 1 |
| Twenty exact indexed-protein sequence queries, Hit@1 | 0.050 |
| Twenty exact indexed-protein sequence queries, Hit@10 | 0.050 |
| Twenty exact indexed-protein sequence queries, Hit@50 | 0.100 |
| Held-out task with 200 chunks, candidate hits | 8/66 |
| Held-out task with 200 chunks, gold evidence in first five candidates | 0/66 |

Thus R2R collection filtering, metadata, and natural-language retrieval work,
but this specific generic text embedding artifact does not preserve a reliable
protein-sequence neighborhood. Increasing the chunk budget finds some relevant
accessions by rank 200 but does not move gold GO or PMID evidence into the fixed
Agent prompt budget.

## Fixed-Generator Agent Result

| Route | Function F1 | Literature F1 | GO / PMID selection F1 | Citation entailment | Pack hallucination | Mechanism abstention |
|---|---:|---:|---:|---:|---:|---:|
| Ordinary text RAG (R2R) | 0.000 | 0.000 | 0.865 / 1.000 | 1.000 | 0.000 | 1.000 |
| Sequence vector | 0.072 | 0.075 | 0.944 / 1.000 | 1.000 | 0.000 | 1.000 |
| Combined BLAST+vector | 0.087 | 0.084 | 0.933 / 1.000 | 1.000 | 0.000 | 1.000 |
| Combined BLAST+vector+DAG | 0.094 | 0.088 | 1.000 / 1.000 | 1.000 | 0.000 | 1.000 |

Relative to R2R text-only retrieval, sequence-vector evidence raises
function/literature F1 by 0.072/0.075 with paired 95% bootstrap intervals
`[0.035, 0.116]` and `[0.039, 0.115]`. GO/PMID prompt recall increases by
0.187/0.128 with intervals `[0.106, 0.278]` and `[0.069, 0.195]`.

Qwen3.5 faithfully copies the non-gold R2R pack rather than inventing gold
labels: citation entailment remains 1.000 and no identifier comes from outside
the pack, but biological answer F1 is zero. This separates a retrieval failure
from a generation-grounding failure.

## Interpretation

1. **Observation:** The live application and text retrieval path are functional,
   but raw protein sequences are not reliably represented by this generic text
   embedder, even for most exact indexed-sequence queries.
2. **Interpretation:** Sequence strings require a sequence-aware representation;
   successful natural-language lookup does not imply useful biological sequence
   geometry.
3. **Implication:** A production Agent should route natural-language queries to
   ordinary R2R text retrieval and raw sequences to BioRAG's protein/DNA encoder,
   then use BLAST for alignment-grounded verification and the DAG for evidence
   organization.
4. **Boundary:** This result concerns one frozen Qwen3-Embedding 0.6B Q8_0
   artifact and this held-out function-to-literature task. It does not establish
   that every general-purpose embedding model fails on every biological sequence
   task.

No additional generic text-embedding sweep is required for the current paper:
public protein encoders already provide the relevant positive control, while the
live R2R route supplies the requested downstream application baseline.
