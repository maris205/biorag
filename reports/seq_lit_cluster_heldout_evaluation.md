# Cluster-Held-Out SeqLit-DAG and Agent Evidence Evaluation

## Research Question

This experiment asks whether a raw protein sequence can retrieve function-linked
literature evidence after stronger sequence-level leakage controls, and whether a
typed DAG improves the evidence actually exposed to an Agent. It separates three
claims:

1. sequence retrieval coverage;
2. typed sequence-to-GO-to-PMID path construction;
3. budget-matched evidence selection for an Agent.

It does not treat vector search as a replacement for alignment, and it does not
claim remote-homology or free-form biomedical question-answering performance.

## Split Controls

Both splits originate from the same 2,000-protein Swiss-Prot/GOA resource and use
100 held-out query proteins. Ground truth consists of low-frequency GO terms
shared with index proteins plus index-side GOA PMID evidence.

| Control | Index proteins | Excluded proteins | Excluded non-query proteins | Selected non-singleton clusters | Leakage audit |
|---|---:|---:|---:|---:|---|
| Observed UniRef50 cluster | 1,892 | 108 | 8 | 8/100 | 0 accession, cluster, query-fragment, or full-sequence overlap |
| BLASTP identity-30 component | 1,732 | 268 | 168 | 100/100 | 0 threshold cross-split pairs, cluster, query-fragment, or full-sequence overlap |

The UniRef50 control is the standard export: the query and every protein assigned
to the same observed UniRef50 cluster are removed. The source sample is already
highly deduplicated, so 1,969 of 1,984 observed clusters are singletons. The
identity-30 control is a harder, deliberately cluster-stratified stress test: it
removes the full BLASTP connected component at at least 30% identity and at least
80% coverage of the shorter sequence, and prioritizes non-singleton components.
It is not an unbiased prevalence sample.

## Retrieval Results

All methods return up to 50 protein candidates and rank up to 200 linked papers. The
table reports query-level means; confidence intervals are nonparametric paired
bootstrap intervals with 10,000 resamples.

| Split | Method | Candidate Hit@10 | Candidate MRR | Paper hit | Complete path |
|---|---|---:|---:|---:|---:|
| UniRef50 | Random | 0.040 | 0.022 | 0.190 | 0.160 |
| UniRef50 | 3-mer Jaccard | 0.240 | 0.165 | 0.430 | 0.410 |
| UniRef50 | BLASTP | 0.340 | 0.257 | 0.350 | 0.340 |
| UniRef50 | ProtT5 mean | **0.430** | **0.317** | **0.650** | **0.620** |
| UniRef50 | ProtT5+BLAST RRF | 0.440 | 0.322 | 0.660 | 0.620 |
| Identity-30 | Random | 0.070 | 0.020 | 0.210 | 0.190 |
| Identity-30 | 3-mer Jaccard | 0.130 | 0.062 | 0.280 | 0.270 |
| Identity-30 | BLASTP | 0.150 | 0.108 | 0.160 | 0.160 |
| Identity-30 | ProtT5 mean | **0.220** | **0.154** | **0.410** | **0.390** |
| Identity-30 | ProtT5+BLAST RRF | 0.200 | 0.126 | 0.390 | 0.370 |

ProtT5 minus BLASTP is `+0.090 [0.010, 0.180]` Hit@10 and
`+0.061 [0.004, 0.120]` MRR on UniRef50. On identity-30, the corresponding
deltas are `+0.070 [0.000, 0.150]` and `+0.047 [0.008, 0.091]`. These are
functional-path labels, not alignment correctness labels: the result supports
dense retrieval as a complementary route to function-linked evidence, not as a
better sequence aligner.

Simple reciprocal-rank fusion is not a robust improvement. Relative to ProtT5,
its Hit@10 delta is `+0.010 [-0.050, 0.070]` on UniRef50 and
`-0.020 [-0.070, 0.030]` on identity-30; identity-30 MRR falls by
`-0.028 [-0.054, -0.007]`. RRF therefore remains a heuristic ablation rather
than a main method.

## Agent Evidence Packs

The application evaluator reduces the paper budget from 200 to 20 and requires
an explicit candidate-to-GO-to-expected-PMID edge for `strict typed path`. This
metric is more informative than raw paper hit because common GOA papers make a
large unfiltered paper pool reachable by chance.

| Split | Route | Candidate hit@50 | GO bridge hit | Citation hit@20 | Strict typed path@20 |
|---|---|---:|---:|---:|---:|
| UniRef50 | Random | 0.160 | 0.160 | 0.040 | 0.040 |
| UniRef50 | 3-mer Jaccard | 0.410 | 0.410 | 0.230 | 0.220 |
| UniRef50 | BLASTP | 0.340 | 0.340 | 0.350 | 0.340 |
| UniRef50 | ProtT5 | **0.620** | **0.620** | 0.410 | 0.390 |
| UniRef50 | ProtT5+BLAST | **0.620** | **0.620** | **0.430** | **0.420** |
| Identity-30 | Random | 0.190 | 0.190 | 0.020 | 0.020 |
| Identity-30 | 3-mer Jaccard | 0.270 | 0.270 | 0.100 | 0.100 |
| Identity-30 | BLASTP | 0.160 | 0.160 | 0.160 | 0.160 |
| Identity-30 | ProtT5 | **0.390** | **0.390** | **0.200** | **0.190** |
| Identity-30 | ProtT5+BLAST | 0.370 | 0.370 | 0.190 | 0.180 |

The strict-path result is the application-level finding: sequence embeddings can
retrieve proteins that expose auditable GOA-to-PMID paths under a fixed context
budget. On UniRef50, fusion adds a small citation-ordering benefit; on the harder
identity-30 control, it does not. This again argues against claiming generic
fusion superiority.

## Frozen Agent Selector

Graph-IDF hyperparameters are selected on 33 development queries and frozen on
67 test queries. `Retrieval oracle` is a ceiling that checks whether a correct
identifier exists anywhere in the available pack; it is not executable.

| Split / route | Selector | Function F1 | Literature F1 | Literature delta vs rank-first (95% CI) |
|---|---|---:|---:|---:|
| UniRef50 / ProtT5 | Rank-first | 0.1250 | 0.0812 | -- |
| UniRef50 / ProtT5 | Graph-IDF | **0.1274** | **0.0990** | **+0.0178 [0.0030, 0.0322]** |
| UniRef50 / ProtT5 | Retrieval oracle | 0.4468 | 0.2126 | -- |
| UniRef50 / fused | Rank-first | **0.1351** | 0.0724 | -- |
| UniRef50 / fused | Graph-IDF | 0.0791 | **0.1006** | **+0.0283 [0.0114, 0.0450]** |
| UniRef50 / fused | Retrieval oracle | 0.4393 | 0.2174 | -- |
| Identity-30 / ProtT5 | Rank-first | **0.0437** | 0.0401 | -- |
| Identity-30 / ProtT5 | Graph-IDF | 0.0234 | **0.0498** | +0.0096 [-0.0031, 0.0240] |
| Identity-30 / ProtT5 | Retrieval oracle | 0.2816 | 0.0914 | -- |
| Identity-30 / fused | Rank-first | **0.0337** | 0.0334 | -- |
| Identity-30 / fused | Graph-IDF | 0.0234 | **0.0338** | +0.0004 [-0.0138, 0.0137] |
| Identity-30 / fused | Retrieval oracle | 0.2856 | 0.0926 | -- |

Graph-IDF gives a resolved literature-ordering gain on the UniRef50 control, but
not on identity-30. It also harms function F1 on the UniRef50 fused route
(`-0.0560 [-0.1042, -0.0058]`). The defensible conclusion is task-specific:
typed graph structure helps compress and order literature evidence in one
standard held-out control, but it is not yet a general retrieval or function
selection improvement. The large oracle gaps show that both retrieval coverage
and selector quality remain open bottlenecks.

## Engineering Cost

ProtT5 BF16 used 128-residue windows with stride 64 and batch size 16 on an RTX
4080 32GB GPU.

| Split | Index windows | Index embedding | Query embedding | Lookup | Warm embedding+lookup | Peak GPU memory |
|---|---:|---:|---:|---:|---:|---:|
| UniRef50 | 14,714 | 83.14 s | 7.25 ms/query | 11.78 ms/query | 19.04 ms/query | 2.59 GiB |
| Identity-30 | 13,491 | 76.82 s | 7.05 ms/query | 10.30 ms/query | 17.35 ms/query | 2.59 GiB |

These timings exclude model load, graph expansion, Agent generation, network
calls, and R2R orchestration. They demonstrate that the scientific retrieval
stage fits comfortably on the 32GB deployment card; no 96GB GPU is needed for
this experiment.

## Claim Boundary and Decision

- Keep the UniRef50 split as the standard cluster-held-out application control.
- Keep identity-30 as a named stress test, not as a benchmark prevalence result.
- Make ProtT5 the protein SeqLit candidate route; keep BLASTP as alignment-grounded verification.
- Report RRF as a negative/mixed ablation rather than a contribution.
- Claim a resolved DAG benefit only for literature selection on UniRef50; call the identity-30 selector result unresolved.
- Do not claim family/clan, species, temporal, remote-homology, mechanism-discovery, or free-form Agent generalization without new data.

Reproducible inputs and detailed outputs are generated by
`scripts/build_seq_lit_uniref50_heldout.py`,
`scripts/build_seq_lit_identity_heldout.py`,
`scripts/eval_seq_lit_heldout_cpu.py`,
`scripts/eval_seq_lit_embeddings.py`,
`scripts/analyze_seq_lit_cluster_heldout.py`,
`scripts/evaluate_agent_evidence.py`, and
`scripts/evaluate_graph_evidence_selector.py`.
