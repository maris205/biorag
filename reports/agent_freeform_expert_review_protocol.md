# Free-form SeqLit Agent Review Pilot

## Status

The 30-case, five-route generation run and assessor-blinded review package are
complete. Domain-expert ratings have **not** been collected. The automatic
results below are identifier and output-integrity diagnostics; they are not an
expert evaluation and do not establish free-form biological reasoning.

## Frozen Design

| Item | Frozen setting |
|---|---|
| Eligible set | 66 accession-masked SeqLit test queries |
| Selected set | 30 queries, selected before free-form generation |
| Stratification | 10 single-GO/sparse-literature, 10 single-GO/dense-literature, 10 multi-GO |
| Evidence routes | no retrieval; R2R text; sequence vector; BLAST+vector; BLAST+vector+DAG |
| Evidence budget | up to 5 candidates, 3 GO claims, and 3 papers |
| Literature context | 431/431 requested PubMed records resolved locally |
| Generator | Qwen3.5-9B BF16, deterministic decoding, 320-token ceiling |
| Output task | at most 150 words: function hypothesis, evidence, literature, uncertainty |
| Planned assessors | two independent sequence-analysis/protein-annotation reviewers |
| Primary human endpoint | mean of functional correctness, citation support, and calibration |
| Blinding | randomized balanced Latin square; each route occurs 6 times at A--E |

Selection uses only reference-label density, not retrieval outcomes or generated
answers. The evaluator bundle contains masked case IDs and no route labels or
held-out accessions. The separate organizer key confirms zero exact held-out-
accession exposure and zero route-name exposure in the evaluator bundle.

The frozen selected-ID file has SHA-256
`35d95b3907209abdc828dc4c0eb547816d8a38404d5485e9196d009e414f48ac`.
The evaluator JSONL and organizer key have SHA-256
`2962bc4dd2134ec8a80ee983f7d7211c4adc656b483fa73c4f5983b8caf24bee`
and `6cf048750fc9d5af11ba2fa552eae7a7c8ef2110de5b68afbde14462bd4d3d6d`,
respectively. The Qwen3.5 config and safetensors index hashes are
`d0883072e01861ed0b2d47be3c16c36a8e81c224c7ffaa310c6558fb3f932b05`
and `26d3539b516be613f39563617cb9d33b3f83d401298125be392c80cefb8f7fe5`.

## Automatic Diagnostic

| Route | GO F1 | PMID F1 | GO/PMID citation entailment | Out-of-pack ID rate | Format | Abstention | Mean/P95 generation ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| No retrieval | 0.000 | 0.000 | 1.000/1.000 | 0.000 | 1.000 | 1.000 | 5290.8/6996.8 |
| R2R text | 0.000 | 0.000 | 0.733/0.956 | 0.033 | 1.000 | 0.000 | 10244.0/14194.4 |
| Sequence vector | 0.125 | 0.100 | 0.767/0.956 | 0.067 | 1.000 | 0.000 | 10386.3/15340.2 |
| BLAST+vector | 0.105 | 0.098 | 0.822/0.983 | 0.033 | 0.967 | 0.000 | 10129.4/14125.2 |
| BLAST+vector+DAG | 0.069 | 0.119 | 0.817/1.000 | 0.000 | 1.000 | 0.000 | 9619.2/13482.7 |

All five runs use the same Qwen3.5 checkpoint and peak at 17.66--17.83 GiB.
The latency is resident-model generation only; it excludes retrieval, query
embedding, and model loading.

## Interpretation

1. **Modality routing is visible.** Generic R2R text retrieval has zero exact
   GO/PMID F1, while the protein sequence route recovers non-zero function and
   paper evidence. This agrees with the larger 66-query structured experiment.
2. **The extra layers are not monotonically better.** BLAST fusion does not
   improve exact-ID F1 in this 30-case pilot. DAG compression lowers exact GO
   F1 while raising PMID F1. These diagnostics do not support a universal
   retrieval-improvement claim.
3. **DAG's current signal is evidence control.** The DAG route has no
   out-of-pack identifier, full four-section completion, and perfect PMID-to-
   evidence-label entailment. Whether this organization is more biologically
   useful is the question assigned to blinded reviewers.
4. **Automatic checks are insufficient.** Regex calibration and overclaim
   checks cannot judge whether function transfer is biologically defensible or
   whether a paper is useful for a scientist. Human scores remain load-bearing.

## Blinded Handoff

Only `reports/agent_expert_review_package/evaluator/` should be sent to
reviewers. It contains the booklet, JSONL cases, protocol, and blank CSV form.
The `organizer/` directory must remain closed until both forms are complete.

After two forms are locked, decode and analyze them with:

```bash
python scripts/summarize_agent_expert_review.py \
  reviewer_1.csv reviewer_2.csv
```

The scorer validates complete 1--5 within-case rankings, averages reviewers
within case/route, bootstraps paired cases, and reports quadratic-weighted
inter-rater agreement.
