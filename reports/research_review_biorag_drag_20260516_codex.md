# Research Review: BioRAG-DRAG (Codex MCP, gpt-5.4 xhigh reasoning)

**Date:** 2026-05-16
**Target:** `paper/main.pdf` (BioRAG-DRAG: A Multimodal Biological Retrieval Layer for Local-First Biomedical Agents)
**Reviewer model:** gpt-5.4 via Codex MCP, `model_reasoning_effort=xhigh`
**Thread ID:** `019e2f1b-fb74-7840-9c3a-33096506247b` (resumable via `mcp__codex__codex-reply`)
**Rounds:** 3

---

## Executive verdict

> **Current ceiling: workshop / a Bioinformatics-style application paper if reframed honestly. Not currently a serious NeurIPS / ICLR submission.**

Two findings dominate the review:

1. **Construct validity is the load-bearing issue.** The 100-query sequence benchmark draws queries (exact / prefix / suffix / middle / mutated windows) from the *same parents* that are indexed. The headline retrieval table is therefore much closer to in-index near-duplicate recovery than to a credible biological retrieval benchmark. Once that is admitted, several headline claims weaken at once.
2. **The current thesis ("vector + BLAST is complementary") is too obvious to carry a paper.** The novel contribution must be *something else* — a benchmark protocol, a scale frontier, an agent-evidence story — not the complementarity itself.

Everything else in this document follows from those two findings.

---

## Round 1 — Initial critique

### Logical gaps and unjustified claims

- **Vector → candidate-BLAST has no current motivation.** On the local 100k corpus it is neither faster than full BLAST nor more accurate. The candidate-FASTA-via-`blastdbcmd` route in `scripts/evaluate_vector_blast_rerank.py` is an extra stage, not a serving advantage.
- **"Hybrid gated" wording is misleading.** The router in `dnarag/retrieval/hybrid.py:343` simply runs both BLAST and vector for sequence queries — it is not substantive gating.
- **"Biological Hit@k" is too permissive given benchmark construction.** The metric counts a hit if the retrieved record shares parent / gene ID / gene symbol / gene family with the gold (`dnarag/evaluation.py:164`). On same-corpus window queries this is partly label leakage and partly a different task definition — acceptable as auxiliary, not as the headline success metric.
- **Vector reranker is heuristic engineering.** k-mer Jaccard + cosine with fixed weights (0.25 vector / 0.75 overlap, k=5). Not a publishable methodological contribution.
- **"Instant" latency framing is misleading.** 4.7–6.1 ms is Chroma lookup *after* query embedding (`scripts/benchmark_instant_verified_latency.py`). On a 2816-dim BF16 OmniGene model, real warm `embed+lookup` is much larger.
- **DRAG biology is undercontrolled.** Same-parent exclusion exists for vector neighborhood enrichment, but DRAG community / GO / Reactome / PubMed analyses lack: (a) parent-collapsed graph; (b) k-mer/Jaccard NN baseline graph; (c) degree-preserving rewired null; (d) BLAST-threshold-matched graph. Risk: rediscovering corpus redundancy and gene-family structure.
- **OmniGene-4 is a manuscript-only backbone.** Central embedding model is unpublished and not independently benchmarked. Reviewers cannot tell whether gains are system-level or private-backbone artifact.
- **False precision.** Reporting 4 decimal places on a 100-query benchmark signals weak statistical discipline.

### Mock NeurIPS review (Round 1)

- **Score:** 3 / 10
- **Confidence:** 4 / 5
- **Summary:** Practical local-first integration; auditability emphasis; recognition that BLAST matters for verification.
- **Weaknesses:** in-index benchmark; candidate-BLAST never beats full BLAST in evaluated regime; permissive metric; under-controlled DRAG; manuscript-only backbone; latency excludes embedding.
- **Reviewer questions:**
  1. Can authors evaluate on held-out sequences not drawn from indexed parents?
  2. Under what corpus scale or latency budget does candidate-subset BLAST dominate full BLAST?
  3. Do DRAG results persist after same-parent collapse and degree-preserving null?
  4. How much performance depends on the unpublished OmniGene backbone?

**Comparators flagged:**
- **ERAST** (Nature Biotechnology, 2026-04). Architecture: HMMER/Pfam preretrieval + ESM-2 / Caduceus encoders + vector DB + reranking; ~1B sequences; benchmarked on SCOPe + Swiss-Prot (protein) and NCBI nucleotide (DNA); positioned closer to *replacing* BLAST/Foldseek/MMseqs2 than to verifying with them.
- **PLMSearch** (Nat Commun 2024) — protein language model + vector DB for remote homology, the closest precedent for the "dense candidate then alignment verify" pattern this paper wants to claim.

The paper currently cites neither ERAST nor PLMSearch in a way that handles this comparison.

---

## Round 2 — Pushbacks and answers

### Pushback A — `vector → candidate-BLAST` has a scaling motivation we underplayed

**Claim:** the route is justified only at corpus scales where BLAST itself becomes the bottleneck (Swiss-Prot 570k → UniRef90 150M → UniRef 600M). On 100k it cannot win.

**Reviewer answer (accepted in principle):** Acceptable as motivation, *not* as paper claim, without a crossover experiment. **Minimum credible test = (c) accuracy/latency curve at multiple corpus scales, anchored by full Swiss-Prot.** A single 570k run (a) is better than current state but does not answer the crossover question. UniRef-only (b) is harder for reviewers to contextualize.

**Concrete protocol the reviewer would run:** protein-only, 3 scales (100k → 300k → full Swiss-Prot ~570k), same query set, same metrics. Crossover present → real story. No crossover → cut candidate-BLAST as headline.

### Pushback B — DRAG controls are weaker than they should be, but not zero

**Reviewer answer:** Of the five missing controls, the **two that must run for DRAG biology to stay in main paper**:
- **Parent-collapsed graph** (kills the "trivial window redundancy" alternative)
- **k-mer / Jaccard-NN baseline graph** (kills the "any cheap sequence-similarity graph would show this" alternative)

Optional third: degree-preserving rewired null. Anything else → appendix.

### Pushback C — Latency claim is partly defensible

**Claim:** instant mode = `embed + lookup << verified mode (~300 ms DNA / ~1000 ms protein)` even after embedding is included; we just have not measured it.

**Reviewer answer:** A single warm end-to-end measurement fixes the misleading wording. To make latency a strong section, also need:
- Warm resident-model only (cold-start → appendix unless CLI UX is claimed).
- Batch size 1.
- p50 / p95 over 100 protein and 100 DNA queries.
- Decomposition: `embed / lookup / verify / graph`.

### ERAST facts (reviewer-confirmed)

- Architecture: preretrieval (HMMER/Pfam filter) → ESM-2 / Caduceus encoders → vector DB → postretrieval rerank.
- Scale: ~1B sequences, claimed largest biological vector DB to date.
- Benchmarks: SCOPe + Swiss-Prot (protein); NCBI nucleotide (DNA).
- Positioning: alternative search engine to BLAST/Foldseek/MMseqs2, not explicitly a BLAST-verification layer.

This forces the related-work section to be rewritten so this paper's distinction is not "we use vectors for biology" but "local-first multimodal packaging for agents with verified evidence routing."

---

## Round 3 — Salvage plan, claims matrix, reframe, runbook

### A. Salvage plan

**Cut, ranked by how much it hurts to keep:**

1. `BioRAG-Standard v0` framed as a *benchmark*. Keep only as a corpus/resource export.
2. `Biological Hit@k` as a *headline* result on the current 100-query window benchmark.
3. DRAG GO/Reactome/PubMed/community biology as a main-result pillar (unless the two controls below pass).
4. The literal "4–6 ms instant" wording.
5. The "hybrid gated" wording.
6. Any novelty framing implying "we discovered vector + BLAST complementarity."

**Keep, ranked by post-fix value:**

1. The local-first multimodal retrieval-layer-for-agents framing.
2. Accuracy / latency tradeoff between dense, full BLAST, and dense → BLAST verification.
3. Public-baseline comparison story (does OmniGene matter, or is the system backbone-agnostic?).
4. Warm end-to-end latency decomposition.
5. DRAG only as optional evidence packaging or controlled appendix result.

**Rerun, with evidence each produces:**

| Rerun | Evidence produced |
| --- | --- |
| Held-out parent benchmark | Fixes construct validity; tells you whether dense retrieval is biologically competitive at all |
| Swiss-Prot scale frontier | Tests whether candidate-BLAST has a real systems role |
| Public embedding baselines | Removes private-backbone-luck hypothesis |
| Warm end-to-end latency | Makes instant / verified split honest |
| DRAG control suite | Determines whether graph biology survives or should be demoted |

### B. Claims matrix (X × Y)

- **X** = held-out parent-benchmark gap between dense retrieval and BLAST on biological Hit@10.
  - X1 = within 5 pts; X2 = 5–20 pts gap; X3 = > 20 pts (collapse).
- **Y** = candidate-BLAST scale experiment on full Swiss-Prot.
  - Y1 = faster than full BLAST at matched accuracy; Y2 = slower but accuracy preserved; Y3 = loses both.

| | **Y1** faster at matched acc. | **Y2** slower, accuracy preserved | **Y3** loses both |
| --- | --- | --- | --- |
| **X1** within 5 pts | Dense retrieval is biologically competitive *and* enables faster verified search at Swiss-Prot scale. **Best case: strong Bioinformatics/BIB; ICLR/NeurIPS D&B long shot.** | Dense retrieval is a strong standalone instant layer; candidate-BLAST is accuracy-preserving but no scale benefit yet. **Strong application/systems paper.** | Dense retrieval is useful for instant multimodal context; candidate-BLAST should be cut. **Bioinformatics application or workshop.** |
| **X2** behind by 5–20 | Dense retrieval is not a replacement, but a useful high-recall prefilter that accelerates verified search. **Good bioinformatics systems paper.** | Dense retrieval is a useful candidate/context layer, not yet a speed win. **Modest application paper or workshop.** | Only weak "local-first integration" claim remains. **Workshop / demo.** |
| **X3** collapse | Dense retrieval is not biologically meaningful standalone, but may serve as a systems prefilter if speed win is real. **Narrow engineering note / workshop.** | Almost no claim beyond software integration. **Workshop / demo.** | Sequence-side dense story fails; cut to a tooling/resource paper. **Demo / internal.** |

### C. Reframe (assuming X1 / X2 with Y1 / Y2)

- **New title:** *BioRAG: Local Biological Retrieval for Agents via Dense Candidate Search and Alignment Verification*
- **Central thesis (one sentence):** Dense retrieval is useful in biological agent systems not as a replacement for alignment, but as a unified low-latency candidate / context layer whose value depends on benchmark realism and corpus scale.
- **Contributions (max 3):**
  1. A held-out evaluation protocol for local biological retrieval that separates instant dense retrieval from verified alignment search.
  2. An accuracy-latency *scaling study* of dense retrieval, BLAST/MMseqs2, and dense → alignment pipelines up to full Swiss-Prot scale, with public baselines.
  3. A local-first retrieval stack that packages verified sequence and text evidence for downstream agents.
- **Figure plan:**
  - Fig. 1 — System architecture and route decomposition.
  - Fig. 2 — Benchmark design including the leakage fix and task families.
  - Fig. 3 — Protein accuracy-latency frontier across corpus scales (100k → 300k → full Swiss-Prot).
  - Fig. 4 — Candidate recall vs budget; full-BLAST vs candidate-BLAST crossover.
  - Fig. 5 — End-to-end latency breakdown + one agent evidence-package case study.
  - DRAG → appendix unless both controls pass.

### D. One-week runbook (with stop/go rules)

Reviewer's recommendation on indexing strategy: **(c) build both, asymmetrically.**
- **Primary / main paper:** unwindowed parent-level `protein_sequence` index on full Swiss-Prot.
- **Secondary / appendix only:** the current windowed `protein_sequence_window` index, OmniGene only.

Rationale: parent-level is the only setup reviewers will trust against BLAST/MMseqs2/PLMSearch. Windowing is worth one ablation but cannot remain the main evaluation object.

Two new configs to create: `configs/review_parent.yaml` and `configs/review_window.yaml` with separate clean `vector_dir`s.

#### Day 0 — Benchmark + plumbing

Build the held-out benchmark *first*. Do not run anything expensive until this exists.

```bash
python scripts/make_parent_fragment_benchmark.py \
  --fasta raw/uniprot/uniprot_sprot.fasta.gz \
  --n 500 \
  --min-query-len 64 --max-query-len 128 \
  --query-types exact_fragment,prefix,suffix,middle,mutated \
  --target protein_sequence \
  --seed 20260516 \
  --output benchmarks/protein_parent_frag_500.jsonl

python scripts/check_benchmark_leakage.py \
  --benchmark benchmarks/protein_parent_frag_500.jsonl \
  --target protein_sequence \
  --config configs/review_parent.yaml \
  --output reports/protein_parent_frag_500_leakage.json
```

**Stop/go:** exact-window leakage rate must be 0. Otherwise stop and fix.

#### Day 1 — OmniGene parent index + core held-out benchmark

Build parent index, run BLAST / vector / MMseqs2 on the same benchmark.

Headline metric: OmniGene vs BLAST gap on Bio H@10 / MRR.

**Stop/go (assigns provisional X):**
- Gap < 5 pts → **X1**, proceed aggressively.
- Gap 5–20 pts → **X2**, proceed but lock paper to "instant candidate layer," not "near-BLAST biological retrieval."
- Gap > 20 pts → **X3**. Continue only to test Y; assume workshop/application ceiling.

#### Day 2 — Public dense baselines

Required: ESM-2 650M, ProtT5-XL-UniRef50. (DNA add-on later: DNABERT-2; nice-to-have NT-2.5B.)

Output: `reports/protein_parent_frag_500_dense_baselines.json` (consumes Fig. 3).

**Stop/go:** if OmniGene is *not* the best dense model and clearly behind a public baseline, **de-center OmniGene immediately** — keep the system story, not the model story. If all dense models are far behind BLAST, you're still in X2/X3; continue only if Y might rescue.

#### Day 3 — Candidate-BLAST scale curve (make-or-break for Y)

Corpora: 100k, 300k, full Swiss-Prot (~570k). Same query set, same metrics.

```bash
for SIZE in 100000 300000 full; do
  # build parent index
  python -m dnarag.cli build-vector \
    --config configs/review_parent_${SIZE}.yaml \
    --targets protein_sequence --backend omnigene \
    --model /path/to/OmniGene-4-CPT-merged \
    --pooling mean --dtype bf16 --batch-size 8 --store chroma

  # candidate-budget sweep
  python scripts/evaluate_vector_candidate_budget_sweep.py \
    --config configs/review_parent_${SIZE}.yaml \
    --benchmark benchmarks/protein_parent_frag_500.jsonl \
    --categories protein_sequence \
    --budgets 10,50,100,200,500 --final-limit 10 --blast-top-k 10 \
    --output reports/protein_candidate_budget_${SIZE}.json

  # vector → BLAST at fixed N=200
  python scripts/evaluate_vector_blast_rerank.py \
    --config configs/review_parent_${SIZE}.yaml \
    --benchmark benchmarks/protein_parent_frag_500.jsonl \
    --categories protein_sequence \
    --candidate-limit 200 --final-limit 10 --blast-top-k 10 \
    --output reports/protein_vec2blast_${SIZE}_N200.json
done
```

Headline: first corpus scale where vector → candidate-BLAST beats full BLAST at matched accuracy.

**Stop/go (assigns Y):**
- Crossover by full Swiss-Prot at matched accuracy → **Y1**, keep scale story.
- No crossover but accuracy preserved + high candidate recall → **Y2**, keep matched-recall plot only, no speed-win claim.
- No crossover and accuracy degrades → **Y3**, cut candidate-BLAST from headline.

#### Day 4 — End-to-end warm latency

Fix the misleading latency section.

```bash
python scripts/benchmark_end_to_end_latency.py \
  --config configs/review_parent_full.yaml \
  --benchmark benchmarks/protein_parent_frag_500.jsonl \
  --target protein_sequence --model omnigene \
  --n 100 --batch-size 1 \
  --modes vector,blast,vector_blast \
  --output reports/protein_latency_e2e_warm.json
```

Required output: p50/p95 over 100 protein + 100 DNA queries; decomposition `embed / lookup / verify / graph`. Cold start → appendix.

**Stop/go:** if warm `embed+lookup` clearly < verified BLAST → keep "instant vs verified" framing with honest numbers. Otherwise cut "instant mode" as a performance claim.

#### Day 5 — Windowed ablation

Compare parent-level vs windowed for fragment queries.

**Stop/go:** if windowed materially beats parent-level → keep one ablation paragraph + appendix figure. Otherwise drop windowing from main narrative almost entirely.

#### Day 6 — DRAG controls

Only after retrieval core is settled.

Build:
- `protein_parent_collapsed_10k.sqlite` (collapses windows by parent)
- `protein_kmer_10k.sqlite` (5-mer Jaccard NN graph, k=5, 5 neighbors)

Run `evaluate_drag_biological_purity.py` and `evaluate_drag_functional_enrichment.py` over the three graphs.

**Stop/go:** if vector-graph signal vanishes after parent-collapse OR is matched by the k-mer graph → cut DRAG biology from main paper. Only keep in main text if it survives both controls *clearly*.

#### Day 7 — Decision tables

Produce `reports/main_claims_table.csv`, `reports/x_y_assignment.json`, `reports/submission_decision.md`.

Fields: `X_status`, `Y_status`, `dense_best_model`, `warm_latency_p50_ms`, `windowed_delta_h10`, `drag_survives_controls`.

### E. Stop/go submission rubric

| X × Y outcome | Action |
| --- | --- |
| X1 + Y1 | Full go. Strongest path. Strong bioinformatics venue first; consider NeurIPS/ICLR D&B *only* with one real downstream agent-quality result added. |
| X1 + Y2 or X2 + Y1 | Go with systems framing. Solid local-first retrieval systems paper, not retrieval-method novelty. |
| X2 + Y2 | Go only for bioinformatics / application venue. |
| Any Y3 with X2/X3, or any X3 | No main-paper push. Workshop / demo or hold for larger rewrite. |

### F. Risk register (top 5)

| Risk | Mitigation |
| --- | --- |
| Public-model embedding scripts may not work with current OmniGene-oriented loader | Add a standalone HF encoder script on Day 0; do not force through current CLI |
| Full Swiss-Prot indexing too slow on one GPU | Use 8x A100 burst only for parent-index embedding builds |
| CPU BLAST/MMseqs2 bottleneck | Cap benchmark at 300–500 queries; report confidence intervals |
| Hidden leakage / duplicated parents in benchmark | Explicit leakage report before any main run |
| Negative-result ambiguity causes thrash midweek | Lock the stop/go rules above before running |

### G. Artifact map (what feeds which figure)

| Figure | Inputs |
| --- | --- |
| Fig. 1 | static system diagram |
| Fig. 2 | `benchmarks/protein_parent_frag_500.jsonl` + `reports/protein_parent_frag_500_leakage.json` |
| Fig. 3 | `reports/protein_parent_frag_500_dense_baselines.json` |
| Fig. 4 | `reports/protein_scale_frontier_summary.json` |
| Fig. 5 | `reports/protein_latency_e2e_warm.json` + one agent case study |
| Appendix A | `reports/protein_parent_vs_windowed.json` |
| Appendix B | `reports/drag_controls_{purity,functional}.json` |

---

## Immediate action items (within the week)

1. **Build the held-out parent benchmark + leakage report.** Without this, every other experiment is wasted compute.
2. **Build OmniGene parent-level Swiss-Prot index** at 100k, 300k, full.
3. **Run public dense baselines** (ESM-2 650M, ProtT5-XL) on the held-out benchmark to remove the private-backbone-luck hypothesis.
4. **Run candidate-budget sweep + vec→BLAST at the three scales** to assign Y.
5. **Measure warm end-to-end latency** with embedding included.
6. **Run DRAG parent-collapse + k-mer-NN baseline** and decide whether DRAG biology survives in main text.
7. **Cut "BioRAG-Standard v0 benchmark" wording** to "exported corpus / library."
8. **Add ERAST + PLMSearch to Related Work** with explicit positioning vs this paper.
9. **Add explicit limitations paragraph** for the manuscript-only OmniGene backbone.
10. **Lower decimal places** on all 100–500 query metrics; report 95% CIs where possible.

---

## Reference: external comparators flagged

- **ERAST** (Nature Biotechnology, 2026-04). HMMER/Pfam preretrieval + ESM-2 / Caduceus + ~1B-vector DB. Benchmarks: SCOPe, Swiss-Prot, NCBI nucleotide. Positioning: alternative search engine to BLAST/Foldseek/MMseqs2.
- **PLMSearch** (Nat Commun 2024). Protein LM + vector DB for remote homology. Closest precedent for the "dense candidate then alignment verify" pattern.

---

## Conversation provenance

- Reviewer: gpt-5.4 via `mcp__codex__codex` with `model_reasoning_effort=xhigh`.
- Thread ID: `019e2f1b-fb74-7840-9c3a-33096506247b` (resumable via `mcp__codex__codex-reply`).
- Round 1: full paper context + critical-review prompt with mock-NeurIPS-review request.
- Round 2: pushbacks on candidate-BLAST motivation, DRAG controls, latency framing; ERAST factual confirmation.
- Round 3: salvage plan + claims matrix + reframe + one-week runbook with stop/go rules.
- Round 4 (added 2026-05-16): re-review of framing-only edits to `paper/main.tex`; verdict moves 3/10 → 4/10 (NeurIPS) / 5/10 (Bioinformatics app), with five residual trims required before submission.

---

## Round 4 — Re-review of framing-only edits

The author revised `paper/main.tex` per Rounds 1–3. **No new experiments.** Edits are pure wording / claim-trimming. Reviewer's updated verdict:

> **The framing is much better. It moved the paper from "misleadingly over-claimed" to "mostly honest engineering paper with unresolved empirical core." But it is not fully landed yet.**

Under X = unknown (held-out benchmark not yet run) and Y = unknown (Swiss-Prot scale curve not yet run), the paper is now **close to legal** as a local-first biomedical retrieval/evidence-packaging system with an in-index sequence-window stress test plus exploratory DRAG. It is **not yet fully legal** if a reader could still infer biological retrieval competitiveness, candidate-BLAST practical value beyond the local ablation, a benchmark/resource contribution stronger than reality, or DRAG biological structure with more weight than "exploratory."

**Verdict:** *almost honest enough for a 3Q engineering/application submission, but still needs a few more trims.*

### Five residual trims required before submission

1. **Abstract metric prominence.** The `BLAST 0.99/0.98` and similar exact numbers in the abstract still over-anchor a casual reader, even with "stress test" wording in the body. Cut exact abstract numbers or keep at most one qualified stress-test number.
   - **Suggested wording:** *"On an in-index sequence-window stress test, BLAST nearly saturates biological matching, while vector retrieval recovers substantial but lower biological match rates."*

2. **"Useful candidate pools" still over-evaluative.** Borderline but fixable.
   - **Suggested wording:** *"...showing that, in this in-index local stress test, vector retrieval often places the biologically matched parent within a 200-candidate pool for downstream alignment-based verification."*

3. **Contribution #1 still inflated.** With 5+3 lookup tasks and 52+52 in-index sequence retrieval tasks, "first 112-task annotation layer" reads as a benchmark contribution.
   - **Suggested wording:** *"A reproducible local corpus/library export with an initial annotation layer for engineering evaluation."*

4. **DRAG biology too prominent for undercontrolled analysis.** Without the parent-collapsed graph + k-mer-NN + degree-preserving null controls, full GO/Reactome and PubMed enrichment tables in the main text remain too much real estate.
   - **Action:** move enrichment tables to Appendix. Keep in main: one compact qualitative DRAG figure + one short exploratory paragraph + one sentence stating stronger controls are future work.

5. **Candidate-BLAST as co-equal main condition.** Without the scale curve, it should not sit beside BLAST and vector as a peer in Table~\ref{tab:retrieval}.
   - **Action:** demote to an "Ablations" subsection or a separate panel, not a main retrieval condition.

Plus one optional but recommended:
- In the results section, add: *"These results should not be interpreted as evidence of held-out biological retrieval competitiveness."*
- Consider dropping `DRAG` from the title/subtitle if most graph biology is exploratory/appendix.

### Updated mock review scores

| Track | Round 1 | Round 4 |
| --- | --- | --- |
| NeurIPS-style | 3 / 10 | **4 / 10** (confidence 4/5) |
| Bioinformatics application track | n/a | **5 / 10** (confidence 4/5, borderline but defensible) |

> The extra point comes from honesty, not stronger science.

### Strengths called out (Round 4)

- Much improved claim discipline and clearer limitations.
- Practical local-first systems integration.
- Sensible separation of dense retrieval, BLAST verification, and agent evidence packaging.
- Better positioning relative to PLMSearch and ERAST.

### Remaining weaknesses (Round 4)

- No new evidence added; central empirical weakness unchanged.
- Abstract still foregrounds inflated stress-test numbers.
- Candidate-BLAST remains over-prominent without scale validation.
- Resource contribution overstated relative to actual annotation scope.
- DRAG biology too prominent for exploratory, undercontrolled analysis.

### "3Q now, 2Q later" split

**Defensible**, but only after the five residual trims above. Without them, even the 3Q version still slightly over-claims via abstract metric prominence, candidate-BLAST table prominence, and DRAG main-text weight.


