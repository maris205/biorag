# BioRAG-SeqLit-DAG UniRef50-cluster-held-out Agent evidence evaluation

This evaluates evidence-pack construction and label-based citation support without an LLM. It is not a human or model answer-quality benchmark. The query and every protein in its observed UniRef50 cluster are absent from the index; the small control does not establish Pfam-clan, species, temporal, or remote-homology generalization.

Queries: `100`; candidate K: `50`; paper K: `20`.

| Method | Typed candidate rate | Candidate hit | GO bridge hit | Citation precision | Citation recall | Complete path | Strict typed path | Pack chars |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BLAST | 0.990 | 0.340 | 0.340 | 0.036 | 0.143 | 0.340 | 0.340 | 16798 |
| ProtT5 | 1.000 | 0.620 | 0.620 | 0.048 | 0.182 | 0.400 | 0.390 | 47833 |
| ProtT5+BLAST | 1.000 | 0.620 | 0.620 | 0.047 | 0.178 | 0.420 | 0.420 | 47525 |
| Random | 1.000 | 0.160 | 0.160 | 0.003 | 0.005 | 0.040 | 0.040 | 46247 |
| k-mer | 1.000 | 0.410 | 0.410 | 0.019 | 0.099 | 0.220 | 0.220 | 45520 |

## Metric Definitions

- `Typed candidate rate`: fraction of ranked candidates with local GO or paper metadata.
- `GO bridge hit`: at least one retrieved candidate carries a gold held-out GO term.
- `Citation precision/recall`: retrieved PMID support against the query's held-out expected PMIDs.
- `Complete path`: a ranked candidate and a ranked expected paper are both present.
- `Strict typed path`: a visible candidate contains an expected GO-to-PMID evidence edge under the paper budget.
- `Pack chars`: compact serialized pack size, a proxy for context budget rather than answer quality.

The evaluation measures auditable evidence construction. It does not claim that a downstream agent's generated answer is correct without a separate human or model-judged QA evaluation.
