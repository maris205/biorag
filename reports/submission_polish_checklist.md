# Submission Polish Checklist

Date: 2026-05-16

## Core Story

One-sentence contribution:

> BioRAG-DRAG turns OmniGene sequence-text embeddings, BLAST verification, and DRAG evidence graphs into a local-first multimodal retrieval layer for auditable biomedical agents.

Main claim boundaries:

- BioRAG-DRAG does not replace BLAST.
- Vector retrieval is the fast unified candidate/context layer.
- BLAST is the alignment-grounded verification/reranking layer.
- DRAG is the typed evidence and biological-structure layer.
- Biological graph signals are hypothesis-generating, not proof of mechanism.

## Claim-Evidence Matrix

| Claim | Evidence in manuscript | Status |
| --- | --- | --- |
| Unified local benchmark/library is available | BioRAG-Standard v0: 257,886 records, 112 annotated tasks | included |
| Vector retrieval is useful as coarse candidate layer | Vector biological Hit@10/MRR 0.8182/0.7088; reranked 0.9293/0.9217 | included |
| BLAST remains stronger verification route | BLAST biological Hit@10/MRR 0.9899/0.9768 | included |
| Vector candidates support verified two-stage retrieval | Vector -> candidate BLAST N=200 reaches 0.9293/0.9293; recall@200 0.9596 | included |
| Instant mode has engineering value | Chroma lookup 4.7-6.1 ms after embedding | included |
| Verified mode adds biological grounding | BLAST + graph verified route latency decomposed by modality | included |
| DRAG graphs contain non-random biological structure | community purity, GO/Reactome enrichment, shared PubMed evidence | included |
| Biological meaning is bounded | limitations explicitly state enrichment is not causal mechanism | included |

## Figures and Tables Needed Next

| Item | Purpose | Data source | Priority |
| --- | --- | --- | --- |
| Fig. 1 architecture | show instant vector, BLAST verified, DRAG evidence routes | `paper.md`, `docs/ARCHITECTURE.md` | high |
| Fig. 2 retrieval quality | compare BLAST, vector, rerank, candidate BLAST, hybrid | `reports/vector_candidate_budget_sweep_summary.md` | high |
| Fig. 3 instant/verified latency | show vector lookup vs BLAST/verified latency | `reports/instant_verified_biorag_system_design.md` | high |
| Fig. 4 DRAG biological graph | vector/BLAST/hybrid graph panels and enrichment signals | `reports/figures/*_analysis.md` | medium |
| Table 1 dataset | BioRAG-Standard partitions and task families | `reports/biorag_standard_dataset.md` | high |
| Table 2 enrichment | GO/Reactome/PubMed support | `reports/drag_functional_enrichment_10k.md`, `reports/drag_literature_support_10k.md` | medium |

## Submission Risks

- Related work citations are now present, but final LaTeX conversion should replace manuscript/self references with anonymized wording if submitting double blind.
- FAISS GPU is not reported because the local wheel lacks Blackwell `sm_120` kernels; keep this as a limitation, not a headline.
- The benchmark is still small for broad biological claims. The paper should emphasize system/resource contribution plus hypothesis-generating graph analysis.
- Mixed text-sequence records are only POC scale. Do not overclaim full multimodal coverage beyond text/DNA/protein/graph in the current experiments.
- Candidate BLAST is a reranking experiment, not a faster end-to-end BLAST replacement, because the current timing includes candidate extraction overhead and is not optimized.

## Venue-Facing Sections Present

| Section | Status |
| --- | --- |
| Abstract | polished, quantitative |
| Introduction | contribution and result preview included |
| Related Work | expanded with real citation scaffold |
| Dataset | included |
| Method | included |
| Experiments | included |
| Results | included |
| Discussion | included |
| Limitations | included |
| Reproducibility and Use Scope | included |
| References | included as Markdown author-year list |

## Next Polish Pass

- Convert Markdown to LaTeX when venue is chosen.
- Add generated figures and captions.
- Replace approximate manuscript citations for Open-Rosalind and OmniGene-4 with final preprint links once available.
- Add appendix commands and exact environment snapshot.
- Run one external review loop after figures are added.
