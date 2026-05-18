# Experiment Plan

**Problem**: Biomedical agents need a unified local evidence layer across text, DNA/cDNA, protein sequences, and graph relations without pretending that dense retrieval replaces alignment search.
**Method Thesis**: BioRAG-DRAG is a model-agnostic multimodal retrieval layer where vector indexes provide instant candidate context, BLAST verifies sequence evidence, and DRAG packages typed graph traces for agents.
**Date**: 2026-05-17

## Claim Map

| Claim | Why It Matters | Minimum Convincing Evidence | Linked Blocks |
|-------|----------------|-----------------------------|---------------|
| C1: BioRAG is a practical unified candidate layer, not a BLAST replacement. | This is the core 3Q-to-2Q engineering claim. | Held-out DNA and protein parent-fragment results, public protein encoders, leakage reports, and candidate-pool recall showing vector can feed downstream verification. | B1, B2, B3 |
| C2: Verified BioRAG improves agent evidence packaging. | This makes the system more than a search benchmark. | Vector-to-BLAST rerank curves, lookup/verified latency table, and DRAG traces with graph controls. | B3, B4 |
| C3: DRAG may expose biological structure but remains exploratory until controlled. | This is the 2Q-upside claim. | Parent-collapsed graph, k-mer nearest-neighbor graph, and degree-preserving null controls showing nontrivial biological enrichment beyond leakage and degree effects. | B5 |

## Paper Storyline

- Main paper must prove: held-out evaluation is leakage-aware; dense retrieval is useful as an instant/candidate layer; BLAST remains the verifier; embedding backend is partition-pluggable.
- Appendix can support: pooling ablations, extra candidate budgets, detailed graph enrichment tables, failed FAISS GPU notes, and expanded benchmark construction.
- Experiments intentionally cut: claims that OmniGene is the strongest protein retriever; claims that vector retrieval replaces BLAST; unconstrained DRAG biology claims without graph controls.

## Experiment Blocks

### Block 1: Held-Out Protein Representation Control

- Claim tested: BioRAG should be model-agnostic and use specialized encoders when they are stronger.
- Dataset / split / task: 500 protein parent-fragment queries, controlled20k index, exact held-out parent removed.
- Compared systems: BLAST, OmniGene mean/last, ESM-2 mean/last, ProtT5 mean/last.
- Metrics: Bio Hit@10, Bio MRR, candidate Recall@50/100/200, latency.
- Status: DONE.
- Table / figure target: main table plus appendix per-query-type breakdown.
- Priority: MUST-RUN.

### Block 2: Held-Out DNA/cDNA Representation Control

- Claim tested: BioRAG also works beyond protein-only retrieval and supports DNA/cDNA partitions.
- Dataset / split / task: 100 DNA/cDNA parent-fragment queries from Ensembl cDNA; exact held-out transcript removed from index; every query has gene_symbol annotation.
- Compared systems: BLASTN, OmniGene mean, optional DNABERT-2/Nucleotide Transformer if feasible.
- Metrics: Bio Hit@10, Bio MRR, candidate Recall@50/100/200, query-type breakdown, leakage report.
- Success criterion: BLASTN remains strongest, while vector retrieval recovers a nontrivial gene-symbol matched candidate pool; no exact held-out parent leakage.
- Failure interpretation: if vector is weak, frame DNA vector search as future encoder/backbone work while retaining unified indexing contribution.
- Table / figure target: new main or appendix DNA held-out table depending on strength.
- Priority: MUST-RUN.

### Block 3: Vector-to-BLAST Candidate Verification Curve

- Claim tested: vector retrieval is useful as candidate generation for verified BioRAG.
- Dataset / split / task: 100-query sequence-window stress test and held-out protein/DNA controls where vector indexes are available.
- Compared systems: full-database BLAST, vector-only, vector top-N followed by candidate-subset BLAST.
- Metrics: candidate Bio Recall@N, final Bio Hit@10/MRR, vector lookup latency, candidate-BLAST latency, total verified latency.
- Success criterion: vector candidate pools recover enough biological positives that candidate BLAST becomes a credible verified-mode route; do not claim speed advantage without scale curve.
- Failure interpretation: if candidate recall saturates low, add graph-expanded candidates or better partition encoder.
- Table / figure target: budget curve figure and engineering latency table.
- Priority: MUST-RUN.

### Block 4: Scale and Latency Frontier

- Claim tested: vector indexes provide an instant operating mode and scale-friendly lookup substrate.
- Dataset / split / task: Chroma and optional FAISS CPU/GPU over 100k, 300k, and full sequence-window collections.
- Compared systems: Chroma lookup, FAISS CPU lookup, FAISS GPU if compatible, BLAST full DB, candidate BLAST.
- Metrics: lookup-only latency, end-to-end warm query latency, throughput if easy, memory footprint.
- Success criterion: lookup-only latency remains small after query embedding; verified mode latency is transparent.
- Failure interpretation: report FAISS GPU as pending if Blackwell kernels remain incompatible; keep Chroma POC numbers.
- Table / figure target: engineering table.
- Priority: MUST-RUN for Chroma/CPU; NICE-TO-HAVE for FAISS GPU.

### Block 5: DRAG Biological Meaning Controls

- Claim tested: sequence-neighborhood graphs may carry biological signal beyond trivial near-duplicate or degree effects.
- Dataset / split / task: DNA and protein 10k view graphs already built from vector, BLAST, and hybrid edges.
- Compared systems: raw vector graph, BLAST graph, hybrid graph, parent-collapsed graph, k-mer nearest-neighbor graph, degree-preserving null.
- Metrics: community label purity, GO/Reactome enrichment where available, shared PubMed support, null z-score or empirical p-value.
- Success criterion: hybrid/vector graphs retain enriched communities after parent collapse and beat k-mer/degree-null controls.
- Failure interpretation: keep DRAG as evidence packaging, move biological meaning to future work.
- Table / figure target: main qualitative graph figure; controls in appendix or main depending on strength.
- Priority: MUST-RUN for 2Q attempt.

## Run Order and Milestones

| Milestone | Goal | Runs | Decision Gate | Cost | Risk |
|-----------|------|------|---------------|------|------|
| M0 | Fix data validity | DNA header parsing, leakage audits, benchmark summaries | 100% DNA queries have gene_symbol and 0 exact parent leakage | CPU minutes | Missing labels |
| M1 | DNA baseline | BLASTN, OmniGene mean vector, optional DNABERT-2 | BLASTN strong; vector nontrivial candidate recall | 1-4 GPU hours for OmniGene index | full cDNA index is large |
| M2 | Candidate verification | budget sweep N=10/25/50/100/200 | candidate recall/latency curve supports verified route | CPU/GPU minutes-hours | candidate subset extraction overhead dominates |
| M3 | Scale/latency | Chroma lookup and FAISS CPU/GPU if available | report lookup-only and verified latency honestly | CPU/GPU minutes | FAISS GPU Blackwell incompatibility |
| M4 | DRAG controls | parent-collapsed, k-mer NN, degree-null controls | biological enrichment survives controls | CPU hours | controls weaken biology claim |
| M5 | Paper integration | update tables, figures, limitations, title if needed | claims match evidence | writing time | overclaiming |

## Compute and Data Budget

- Total estimated GPU-hours: 4-12 for OmniGene DNA indexing/eval; less if using 100k/source-limited POC first.
- Data preparation needs: DNA held-out FASTA, BLASTN DB, leakage reports, optional DNABERT/Nucleotide Transformer download.
- Human evaluation needs: none for this pass.
- Biggest bottleneck: embedding large DNA/cDNA window collections with OmniGene; use staged 20k/100k before full.

## Risks and Mitigations

- DNA vectors underperform badly: keep DNA result as honest partition stress test and add DNABERT-2/Nucleotide Transformer baseline.
- Candidate-BLAST is not faster locally: frame it as verified evidence routing; reserve speed claims for scale curve.
- DRAG biology disappears under controls: keep DRAG as agent evidence packaging and move biology to exploratory appendix.
- OmniGene loses to public encoders: frame BioRAG as pluggable; OmniGene is for unified biological-language/agent contexts.

## Final Checklist

- [x] Protein public baselines completed.
- [ ] DNA held-out baseline completed.
- [ ] Candidate-BLAST budget curve completed.
- [ ] Lookup/verified latency table updated.
- [ ] DRAG parent-collapsed/k-mer/degree-null controls completed.
- [ ] Main paper claims updated to match evidence.
