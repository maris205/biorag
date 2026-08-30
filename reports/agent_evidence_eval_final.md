# Agent Evidence Evaluation

This evaluates evidence-pack construction and label-based citation support without an LLM. It is not a human or model answer-quality benchmark. Relevance follows the held-out split labels.

Queries: `99`; candidate K: `50`; paper K: `20`.

| Method | Typed candidate rate | Candidate hit | GO bridge hit | Citation precision | Citation recall | Complete path | Strict typed path | Pack chars |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BLAST | 1.000 | 0.242 | 0.242 | 0.026 | 0.121 | 0.222 | 0.222 | 18375 |
| ESM-2 | 1.000 | 0.364 | 0.364 | 0.021 | 0.128 | 0.202 | 0.202 | 47657 |
| ProtT5 | 1.000 | 0.465 | 0.465 | 0.027 | 0.142 | 0.253 | 0.253 | 47201 |
| ProtT5+BLAST | 1.000 | 0.444 | 0.444 | 0.027 | 0.146 | 0.263 | 0.263 | 47398 |
| Random | 1.000 | 0.061 | 0.061 | 0.000 | 0.000 | 0.000 | 0.000 | 46462 |
| k-mer | 1.000 | 0.313 | 0.313 | 0.017 | 0.084 | 0.152 | 0.152 | 45065 |

## Metric Definitions

- `Typed candidate rate`: fraction of ranked candidates with local GO or paper metadata.
- `GO bridge hit`: at least one retrieved candidate carries a gold held-out GO term.
- `Citation precision/recall`: retrieved PMID support against the query's held-out expected PMIDs.
- `Complete path`: a ranked candidate and a ranked expected paper are both present.
- `Strict typed path`: a visible candidate contains an expected GO-to-PMID evidence edge under the paper budget.
- `Pack chars`: compact serialized pack size, a proxy for context budget rather than answer quality.

The evaluation measures auditable evidence construction. It does not claim that a downstream agent's generated answer is correct without a separate human or model-judged QA evaluation.
