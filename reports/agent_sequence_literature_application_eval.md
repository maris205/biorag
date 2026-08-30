# Sequence-to-Literature DAG and Agent Evidence Evaluation

## Scope

This experiment evaluates the final BioRAG application path:

`held-out protein sequence -> retrieved protein candidates -> GO/GOA evidence -> PubMed identifiers -> compact evidence pack -> local Agent`

The task is structured evidence execution, not free-form biomedical question answering. Expected GO and PMID identifiers come from curated split labels. A correct citation must point to a typed edge in the supplied evidence pack. The evaluation does not establish molecular mechanism, clinical validity, or expert-level interpretation.

## Dataset and Leakage Controls

- Source DAG: 2,000 Swiss-Prot proteins, 12,858 GO annotations, 4,304 PMIDs, and 63,651 typed edges.
- Held-out benchmark: 99 query proteins and 1,901 index proteins.
- Expected labels: 132 unique GO IDs and 377 unique PMIDs, restricted to GO document frequency 2--10.
- Exact held-out accession overlap: 0.
- Full-sequence substring overlap: 0.
- Selector split: deterministic 33-query development set and frozen 66-query test set, seed `20260830`.
- The query accession is masked from the generation prompt to prevent parametric identifier lookup.

## Budget-Matched Evidence Baselines

All methods use at most 50 protein candidates and 20 paper identifiers. The table uses the corrected merged document loader and full stored top-50 rankings.

| Method | Candidate hit | Candidate recall | GO bridge recall | Citation hit | Strict typed path | Citation precision |
|---|---:|---:|---:|---:|---:|---:|
| Random | 0.061 | 0.027 | 0.045 | 0.000 | 0.000 | 0.000 |
| k-mer Jaccard | 0.313 | 0.127 | 0.248 | 0.152 | 0.152 | 0.017 |
| BLASTP | 0.242 | 0.124 | 0.194 | 0.222 | 0.222 | 0.026 |
| ESM-2 mean | 0.364 | 0.181 | 0.301 | 0.202 | 0.202 | 0.021 |
| ProtT5 mean | **0.465** | **0.225** | **0.368** | 0.253 | 0.253 | 0.027 |
| ProtT5 + BLAST RRF | 0.444 | 0.220 | 0.353 | **0.263** | **0.263** | **0.027** |

Observation: ProtT5 provides the strongest candidate and annotation coverage. Adding BLAST through reciprocal-rank fusion slightly lowers candidate hit by 0.020 but raises strict path completion by 0.010. This is evidence of route complementarity at the citation path, not a general fusion win.

## Frozen Graph-IDF Selector

The selector ranks claims using only candidate rank, corpus GO document frequency, and typed GO-to-PMID edges. Hyperparameters were selected on 33 development queries and then frozen. The selected configuration uses the first five protein candidates, IDF power 1.0, and three output claims for both function and literature.

| Test method | Function P/R/F1/Hit | Literature P/R/F1/Hit |
|---|---:|---:|
| Rank-first | 0.055 / 0.172 / 0.079 / 0.227 | 0.044 / 0.123 / 0.058 / 0.258 |
| Rank-first, budget matched | 0.056 / 0.114 / 0.071 / 0.152 | 0.101 / 0.091 / 0.085 / 0.197 |
| Graph-IDF | **0.081 / 0.153 / 0.100 / 0.212** | **0.116 / 0.109 / 0.100 / 0.227** |
| Retrieval oracle | 0.515 / 0.394 / 0.431 / 0.515 | 0.258 / 0.124 / 0.153 / 0.258 |

Paired bootstrap deltas for Graph-IDF versus the budget-matched selector are:

| Task | Absolute F1 delta | 95% CI | Relative delta |
|---|---:|---:|---:|
| Function | +0.029 | [0.006, 0.057] | +41.1% |
| Literature | +0.015 | [0.000, 0.034] | +18.3% |

Conditional on the answer being present in the retrieval pack, Graph-IDF reaches function F1 0.194 on 34 queries and literature F1 0.389 on 17 queries. The gap to the retrieval oracle shows that candidate/evidence coverage, not citation formatting, is now the primary bottleneck.

Increasing the paper expansion budget from 20 to 200 raises the test literature-oracle hit rate from 0.258 to 0.515, but does not improve the frozen executable selector. Larger unfiltered paper pools therefore increase the ceiling and the noise together; exploiting them requires a stronger learned or metadata-aware paper selector.

## Generated Agent Evaluation

Qwen2.5-7B-Instruct BF16 executes the frozen Graph-IDF packs for all 66 test queries. Each query produces function, literature, and mechanism answers. Prompts expose typed evidence IDs but mask the held-out accession.

| QA type | End-to-end F1 | Prompt gold recall | Retrievable F1 | Evidence-selection F1 | Citation validity | Citation entailment | Out-of-pack hallucination | Correct abstention |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Function | 0.100 | 0.172 | 0.111 | 0.985 | 1.000 | 1.000 | 0.000 | n/a |
| Literature | 0.100 | 0.128 | 0.138 | 1.000 | 1.000 | 1.000 | 0.000 | n/a |
| Mechanism | n/a | n/a | n/a | n/a | 1.000 | 1.000 | 0.000 | 1.000 |

All 198 answers satisfy the required two-line format and bracketed citation syntax. Three function answers select a later valid GO item instead of the requested third Graph-IDF item, producing the 0.985 selection F1. These deviations are retained as frozen test errors. The model does not invent a GO ID, PMID, or citation outside the supplied pack, and it abstains on all mechanism questions because mechanism evidence is absent.

Generation measurements on one RTX PRO 6000 Blackwell GPU are:

| Quantity | Value |
|---|---:|
| Model load | 5.431 s |
| Mean generation per answer | 607.4 ms |
| P50 / P95 generation | 777.4 / 825.3 ms |
| Generated throughput | 74.75 tokens/s |
| Peak GPU memory | 14.35 GiB |
| Total for 198 answers | 132.46 s |

The measured memory confirms that a 32 GB GPU is sufficient for this BF16 Agent pilot. The 96 GB GPU was convenient but not required.

## Claim Boundary

Supported claim: a held-out protein sequence can be used as the entry point to retrieve candidate proteins, traverse curated function-to-paper edges, select a compact evidence pack, and execute citation-bounded structured Agent answers with reliable citation syntax and explicit abstention.

Unsupported claim: the current system solves remote homology, discovers new function, proves mechanisms, or produces expert-grade free-form biomedical answers. Expected papers are curated evidence associated with function-linked index proteins; they are not automatically direct experimental evidence for the held-out query protein.

## Reproducible Artifacts

- `reports/results/agent_evidence_eval_final.json`
- `reports/results/agent_graph_selector_prott5_full_p20.json`
- `reports/results/agent_graph_selector_prott5_full_p20_packs.jsonl`
- `reports/results/agent_qa_generated_qwen25_7b_graph_masked_test66.json`
- `reports/results/agent_qa_generated_qwen25_7b_graph_masked_test66_score.json`
- `reports/agent_qa_generated_qwen25_7b_graph_masked_test66_score.md`
