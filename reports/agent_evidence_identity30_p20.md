# BioRAG-SeqLit-DAG identity-cluster-held-out Agent evidence stress test

This evaluates evidence-pack construction and label-based citation support without an LLM. It is not a human or model answer-quality benchmark. The query's full thresholded BLASTP component is absent from the index. Queries prioritize non-singleton components, so this is a cluster-stratified stress test rather than a prevalence sample.

Queries: `100`; candidate K: `50`; paper K: `20`.

| Method | Typed candidate rate | Candidate hit | GO bridge hit | Citation precision | Citation recall | Complete path | Strict typed path | Pack chars |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BLAST | 1.000 | 0.160 | 0.160 | 0.016 | 0.058 | 0.160 | 0.160 | 18892 |
| ProtT5 | 1.000 | 0.390 | 0.390 | 0.023 | 0.079 | 0.190 | 0.190 | 47279 |
| ProtT5+BLAST | 1.000 | 0.370 | 0.370 | 0.022 | 0.068 | 0.180 | 0.180 | 47118 |
| Random | 1.000 | 0.190 | 0.190 | 0.001 | 0.002 | 0.020 | 0.020 | 46328 |
| k-mer | 1.000 | 0.270 | 0.270 | 0.010 | 0.039 | 0.100 | 0.100 | 45366 |

## Metric Definitions

- `Typed candidate rate`: fraction of ranked candidates with local GO or paper metadata.
- `GO bridge hit`: at least one retrieved candidate carries a gold held-out GO term.
- `Citation precision/recall`: retrieved PMID support against the query's held-out expected PMIDs.
- `Complete path`: a ranked candidate and a ranked expected paper are both present.
- `Strict typed path`: a visible candidate contains an expected GO-to-PMID evidence edge under the paper budget.
- `Pack chars`: compact serialized pack size, a proxy for context budget rather than answer quality.

The evaluation measures auditable evidence construction. It does not claim that a downstream agent's generated answer is correct without a separate human or model-judged QA evaluation.
