# BioRAG-DRAG Submission Reframe: 3Q Baseline, 2Q Upside

Date: 2026-05-16

## Current Paper Positioning

The current manuscript has been reframed as an engineering-oriented biomedical
retrieval systems paper:

- **Core claim:** BioRAG-DRAG is a local-first multimodal retrieval and evidence
  packaging layer for biomedical agents.
- **Engineering novelty:** unified local indexing of text, DNA/cDNA, protein,
  and graph evidence; vector candidate retrieval; BLAST verification; DRAG
  evidence traces.
- **Biological lift:** DRAG communities show exploratory biological structure
  through family/gene enrichment, GO/Reactome enrichment, and PubMed evidence
  sharing.
- **Boundary:** the current 100-query sequence result is a local
  sequence-window stress test, not a held-out homology benchmark.

This is a safer 3Q-style application/systems paper. The biological graph
analysis gives it an upward path, but we should not claim 2Q-level biological
meaning until the controls pass.

## Manuscript Changes Already Made

- Changed "benchmark/library" to "corpus/library" and "first annotation layer".
- Explicitly states the 100-query set is not a held-out homology benchmark.
- Changed "Hybrid gated" to "Combined BLAST+vector evidence".
- Changed "instant latency" to lookup-only latency after query embedding.
- Added ERAST and PLMSearch positioning in Related Work.
- Described sequence reranker as a heuristic engineering ablation, not a method.
- Added public-baseline and held-out-parent evaluation as limitations/future
  work.
- Added DRAG controls needed for stronger biological claims:
  parent-collapsed graph, k-mer NN graph, degree-preserving nulls.

Updated files:

- `paper/main.tex`
- `paper/main.pdf`

## 3Q Submission Package

Minimum acceptable package:

1. Current PDF with conservative claims.
2. Reproducibility notes and scripts listed in `reports/`.
3. Strong discussion of practical value:
   - local-first use;
   - unified retrieval interface for agents;
   - BLAST remains verification;
   - DRAG provides evidence organization.
4. Biological graph analysis included as exploratory, not causal.

This should be framed for biomedical informatics / bioinformatics application /
AI-for-biomed systems venues, not top ML.

## 2Q Upgrade Experiments

To raise the paper from engineering integration to stronger biological/scientific
contribution, run these in order:

1. **Held-out parent-fragment benchmark + leakage report**
   - Parent-level split; no indexed exact parent for held-out queries.
   - This fixes construct validity.

2. **Public dense baselines**
   - Internal backbone control: original Gemma4 MoE base/instruct model without
     biological tokenizer expansion and CPT, if available.
   - Protein: ESM-2 650M, ProtT5-XL.
   - DNA: DNABERT-2, Nucleotide Transformer if feasible.
   - This separates base-model capability from the tokenizer-extension/CPT
     contribution and prevents the "private OmniGene-only artifact" criticism.

3. **Warm end-to-end latency**
   - p50/p95, batch size 1.
   - Decompose `embed / lookup / BLAST / graph`.
   - This determines whether "rapid response" can be an end-to-end claim.

4. **Swiss-Prot scale curve**
   - 100k, 300k, full Swiss-Prot.
   - Compare full BLAST vs vector -> candidate BLAST.
   - Only claim a speed advantage if matched-accuracy crossover appears.

5. **DRAG biological controls**
   - Parent-collapsed graph.
   - k-mer/Jaccard nearest-neighbor graph.
   - Degree-preserving null if time allows.
   - If vector DRAG survives these controls, biological significance can move
     from exploratory to a main contribution.

## Stop/Go Rules

- If held-out dense retrieval is within 5-20 points of BLAST and DRAG controls
  pass: reasonable 2Q target.
- If dense retrieval collapses but DRAG controls pass: keep engineering paper,
  use DRAG as the biological lift.
- If DRAG controls fail: keep DRAG as evidence packaging only, not biological
  meaning.
- If original Gemma4 MoE is close to OmniGene: weaken the CPT-specific claim and
  emphasize BioRAG as the system contribution.
- If public baselines beat OmniGene: de-center OmniGene and emphasize the
  model-agnostic BioRAG system.
