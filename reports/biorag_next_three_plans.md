# BioRAG Next Three Plans

Date: 2026-05-16

The project should now converge into three paper tracks. This keeps the work
from becoming a loose collection of engineering tests.

## Plan 1: Vector Coarse Retrieval + BLAST Reranking

Goal: turn the core method into a formal two-stage retrieval experiment.

Pipeline:

```text
query sequence
  -> OmniGene/Chroma vector top-N parent sequence candidates
  -> candidate-subset BLAST scoring
  -> reranked evidence list with alignment metadata
```

Why it matters:

- avoids framing vector search as a BLAST replacement
- makes vector retrieval a fast candidate generator
- keeps BLAST as biological verification
- gives a clean method table: BLAST-only, vector-only, vector+rerank,
  hybrid/DRAG

Current outputs:

- `scripts/evaluate_vector_blast_rerank.py`
- `reports/vector_blast_rerank_eval.json`
- `reports/vector_blast_rerank_summary.md`
- `scripts/evaluate_vector_candidate_budget_sweep.py`
- `reports/vector_candidate_budget_sweep_eval.json`
- `reports/vector_candidate_budget_sweep_summary.md`
- `scripts/evaluate_vector_graph_blast_rerank.py`
- `reports/vector_graph_blast_rerank_eval.json`
- `reports/vector_graph_blast_rerank_summary.md`

Current result on the 100-query sequence subset:

| Condition | Exact Hit@10 | Exact MRR | Biological Hit@10 | Biological MRR | Candidate Bio Recall@50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Vector -> candidate BLAST rerank | 0.5700 | 0.4898 | 0.8687 | 0.8687 | 0.8788 |

Candidate-budget sweep:

| Budget | Exact Hit@10 | Exact MRR | Biological Hit@10 | Biological MRR | Candidate Bio Recall@N |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 0.5700 | 0.4898 | 0.8687 | 0.8687 | 0.8788 |
| 100 | 0.6100 | 0.5151 | 0.8990 | 0.8990 | 0.9293 |
| 200 | 0.6500 | 0.5377 | 0.9293 | 0.9293 | 0.9596 |

10k DRAG-expanded candidate ablation:

| Condition | Exact Hit@10 | Biological Hit@10 | Seed Bio Recall | Expanded Bio Recall |
| --- | ---: | ---: | ---: | ---: |
| Vector(50) + 10k DRAG expand -> BLAST | 0.5800 | 0.8687 | 0.8788 | 0.8788 |

Next retrieval work:

- use 200-candidate overfetch as the stronger current candidate-BLAST setting
- improve protein-side candidate-pool recall with calibrated candidate scoring
- build a full 100k or complete sequence DRAG graph before rerunning
  graph-expanded candidate retrieval
- keep full-database BLAST as fallback and reference verification

## Plan 2: DRAG Biological Significance

Goal: show that sequence-derived DRAG graphs have biological structure, not
only search utility.

Current evidence:

- vector neighborhoods recover biological labels above random baselines
- DNA/cDNA vector and hybrid graphs recover IGKV/IGHV/IG_D/IG_J modules
- protein vector and hybrid graphs recover pgl/yfbR-like gene-symbol modules
- hybrid graphs preserve vector connectivity while adding BLAST evidence
- DRAG communities share PubMed evidence through local NCBI gene2pubmed mappings

Next analyses:

- GO enrichment, now implemented as a first pass
- Reactome pathway enrichment, now implemented as a first pass
- Pfam/domain enrichment if source data is added
- gene-family and biotype purity, now implemented as a first pass
- literature support via gene2pubmed, now implemented as a first pass
- route-labeled graph case studies

Current outputs:

- `reports/drag_biological_significance.md`
- `reports/drag_gene_family_purity_10k.md`
- `reports/drag_functional_enrichment_10k.md`
- `reports/drag_literature_support_10k.md`
- figure-ready graph/community tables for the paper

Still expected:

- Pfam/domain enrichment tables
- title/abstract case studies for top shared PMIDs

## Plan 3: Agent and Multimodal BioRAG Application

Goal: demonstrate why this unified retrieval layer is useful for LLM agents.

Pipeline:

```text
instant mode:
  query -> vector context -> provisional answer

verified mode:
  query -> vector candidates -> BLAST verification -> DRAG graph paths
        -> citation-ready answer context
```

Why it matters:

- shows application value beyond sequence-search benchmarks
- supports local-first biomedical agents
- uses one corpus for text, DNA/cDNA, protein, graph evidence, and later
  structure/image modalities

Expected outputs:

- expanded BioRAG-Standard multi-hop tasks
- `reports/drag_agent_case_studies.md`
- evidence-grounding and citation-correctness evaluation
- updated latency/scaling table, with FAISS/Milvus GPU revisited when the
  runtime supports Blackwell cleanly

Current supporting outputs:

- `reports/instant_verified_biorag_system_design.md`
- `reports/drag_agent_trace_10k.md`
- route-labeled traces under `reports/traces/`

## Priority Order

1. Improve Plan 1 protein-side candidate-pool recall and rerun graph-expanded
   retrieval on a full-scale sequence DRAG graph.
2. Continue Plan 2 because it is the paper's strongest biological novelty.
3. Turn Plan 3 traces into multi-hop tasks and citation-grounding evaluation.
