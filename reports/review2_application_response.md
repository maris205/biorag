# Response to `review2.md`: Application and R2R Work

## Decision

The review's strongest recommendation is adopted: the paper is positioned as a
model-independent local biological evidence layer, and the next experiment is a
downstream Agent ablation rather than another DNA encoder sweep.

## Implemented in This Revision

| Review concern | Action |
|---|---|
| Retrieval engineering is not yet a downstream scientific task | Added a frozen 66-query application ablation over no retrieval, sequence vector, combined vector+BLAST, and combined vector+BLAST+typed DAG evidence |
| Open-Rosalind/application connection is conceptual | Added an R2R v3 application adapter because the production project already uses R2R; the same evidence contract can be exposed to Open-Rosalind-style agents |
| DRAG edges need auditable provenance | Added `source_record`, `evidence_level`, `retrieval_score`, `verification_method`, and `database_version` to SeqLit-DAG edges and R2R relationship metadata |
| Ordinary text RAG needs a controlled comparison | Added a live R2R text-only evaluator and a separately labeled sequence-in-text control collection; no result is claimed without a frozen live endpoint |
| Generator choice should not define the contribution | Retrieval packs are frozen independently of the generator; Qwen3.5 is the main executor and Qwen2.5 is retained as a robustness reference |
| Unknown evidence should not trigger invention | Added evidence-aware abstention prompts and scoring for empty evidence packs |
| Deployment should be realistic | R2R handles CRUD, collections, text retrieval, and Agent APIs; BioRAG supplies sequence retrieval, BLAST, typed graph paths, and evidence provenance |

## Completed Fixed-Generator Result

On the frozen 66-query split, Qwen3.5-9B is held fixed while only the evidence
route changes:

| Route | Function F1 | Literature F1 | GO/PMID prompt recall | GO/PMID selection F1 |
|---|---:|---:|---:|---:|
| Sequence vector | 0.072 | 0.075 | 0.187 / 0.128 | 0.944 / 1.000 |
| Combined BLAST+vector | 0.087 | 0.084 | 0.202 / 0.133 | 0.933 / 1.000 |
| Combined BLAST+vector+DAG | 0.094 | 0.088 | 0.202 / 0.133 | 1.000 / 1.000 |

DAG does not increase prompt coverage under the matched budget. Its resolved
effect is evidence organization: GO selection improves by 0.067 with paired
95% CI `[0.035, 0.105]`; the smaller answer-F1 deltas cross zero. All
evidence-bearing routes have citation entailment 1.000, no out-of-pack GO/PMID
identifier, and complete mechanism abstention. Qwen2.5 reproduces the same DAG
result at function/literature F1 0.094/0.090, so the conclusion is not tied to
Qwen3.5.

The 2k SeqLit-DAG was rebuilt as v0.2.0 with unchanged counts and complete
static-edge provenance. Its R2R application projection contains 12,858
text/mixed documents, 22,939 entities, and 63,651 explicit relationships. The
live R2R text-only result remains pending because this machine has no frozen R2R
endpoint or collection; no proxy is substituted.

## Still Required for a Stronger Biological Claim

- family/Pfam-cluster, species, temporal, or database-version holdout;
- a live R2R text-only run with a frozen server, collection, and embedding model;
- free-form expert evaluation beyond GO/PMID identifier execution;
- larger sequence-to-literature resources and title/abstract coverage;
- end-to-end concurrent latency on the deployed application;
- controlled biological case studies that do not infer mechanism from graph
  connectivity alone.

These items remain limitations or future work. They are not implied by the
current 2k SeqLit-DAG result.
