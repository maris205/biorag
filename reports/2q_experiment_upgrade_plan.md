# BioRAG-DRAG 2Q Upgrade Experiment Plan

Date: 2026-05-16

Goal: keep the current manuscript defensible as a 3Q engineering/application
paper, while adding the smallest set of experiments that can plausibly lift it
toward a 2Q bioinformatics / biomedical AI systems submission.

## 2026-05-17 Update

- DNA/cDNA held-out transcript-fragment control is now implemented. The
  controlled20k split has 100/100 tasks with same-gene non-held-out candidates
  and zero exact held-out transcript leakage, but 62/100 query fragments are
  exact substrings of other indexed transcripts, so it should be described as a
  held-out transcript-fragment control rather than strict remote homology.
- BLASTN on the DNA controlled20k split reaches biological Hit@10/MRR
  0.9100/0.9100 with mean latency 94.7 ms.
- OmniGene-4-CPT BF16 mean on the DNA controlled20k 20k-window vector index
  reaches biological Hit@10/MRR 0.1000/0.0795. This is weak and strengthens the
  model-agnostic framing.
- Nucleotide Transformer 500M was evaluated as a public DNA encoder. Mean
  pooling over the full controlled20k window index reaches biological
  Hit@10/MRR 0.0100/0.0021, and a CLS-pooling 20k-window smoke run reaches
  0.0300/0.0090. Off-the-shelf pooling is therefore not sufficient for this
  cDNA transcript-fragment retrieval task.
- DNABERT-2 was attempted but blocked by custom-model compatibility issues
  under the current Transformers/Torch environment. Treat this as an
  environment blocker, not a scientific result; rerun in a pinned Transformers
  4.x environment if DNA public baselines become a submission blocker.
- The sequence-window candidate-budget sweep is complete. Vector top-200
  followed by candidate-subset BLAST reaches biological Hit@10/MRR
  0.9293/0.9293 and candidate biological recall 0.9596 on the 100-query
  in-index stress test. DNA/cDNA reaches candidate biological recall 1.0000 at
  200 candidates; protein reaches 0.9184.
- DRAG graph controls were added on the 10k graph views. Existing graphs are
  already parent-collapsed, observed vector graphs show label-enriched
  communities, degree-preserving null graphs do not show comparable top
  signals, and k-mer/Jaccard graphs also recover strong sequence-family
  communities. This supports a cautious exploratory DRAG claim but not a claim
  that learned-vector graphs uniquely reveal new biology.
- Agent-style evidence case studies were added from existing DRAG traces. The
  generated report does not call an LLM; it shows the evidence pack a downstream
  biomedical agent would receive, including vector-vs-BLAST route labels,
  representative edges, and answer boundaries for IGKV2-40, pgl, and yfbR.
- Swiss-Prot protein scale-frontier BLAST references were added on the
  500-query held-out parent-fragment benchmark. Controlled100k and
  controlled300k subsets preserve same-gene positive candidates for all 500
  queries and have zero exact held-out-parent leakage. BLAST Bio Hit@10/MRR and
  mean latency are: 20k 0.8560/0.8289 at 138.6 ms, 100k 0.8320/0.7960 at
  329.2 ms, 300k 0.8140/0.7613 at 796.5 ms, and full held-out Swiss-Prot
  0.8060/0.7442 at 1039.3 ms.
- The paper now includes a candidate-budget table and a DNA/cDNA held-out
  control table. Remaining 2Q blockers are matching 100k/300k/full vector
  indexes plus candidate-BLAST sweeps, a pinned-env DNABERT-2 run if needed,
  original Gemma4 MoE control if available, and a real downstream
  answer-quality evaluation if targeting a stronger venue.

## Claim Map

| Claim | Current Status | 2Q Evidence Needed |
| --- | --- | --- |
| Local BioRAG is useful for agent evidence packaging | Supported by system design, Chroma/BLAST/DRAG traces, and an agent-style evidence-pack case study | Add downstream answer-quality evaluation for stronger venues |
| Dense retrieval is useful beyond in-index window recovery | Partially supported by controlled20k held-out parent-fragment results; BLAST remains stronger | Extend to full Swiss-Prot scale and DNA tasks |
| OmniGene embeddings are meaningfully useful | Useful as unified biological-language backbone, but public protein encoders are stronger on current protein-only held-out retrieval; OmniGene is also weak on the current DNA held-out control, while NT 500M off-the-shelf pooling is weaker still | Compare original Gemma4 MoE, newer ESM-family protein encoders, and pinned-env DNABERT-2 for DNA |
| Candidate-BLAST can be a systems route | BLAST scale reference is now measured at 20k/100k/300k/full; vector/candidate-BLAST scale points are pending | Build matching vector indexes and run candidate-BLAST sweeps before claiming speed advantages |
| DRAG graph has biological meaning | Exploratory; parent-collapse and null controls are supportive, while k-mer controls explain part of the signal | Add larger parent-collapsed graphs plus GO/pathway/domain case studies before making biological-discovery claims |

## Must-Run Blocks

### B1. Held-Out Parent-Fragment Benchmark

- Purpose: fix construct validity.
- Data: Swiss-Prot parent sequences; hold out parents from vector index.
- Queries: 64--128 aa fragments from held-out parents, plus mutated fragments.
- Index: parent-level sequence index excluding held-out parents.
- Metrics: biological Hit@10/MRR, family/gene-level match when annotations allow, BLAST comparison.
- Success criterion:
  - Strong: vector biological Hit@10 within 5--15 points of BLAST.
  - Acceptable for 3Q/2Q systems: vector is lower but provides high recall@200 candidate pools.
  - Failure: vector collapses and cannot recover related parents.

### B2. Public Dense Baselines

- Internal backbone control: original Gemma4 MoE base/instruct model without the
  BioRAG sequence vocabulary expansion and CPT, if available.
- Protein baselines: ESM-2 650M, ProtT5-XL-UniRef50.
- Completed protein baselines: ProtT5 mean pooling reaches biological
  Hit@10/MRR 0.778/0.7158 and ESM-2 mean reaches 0.656/0.5764 on the
  controlled20k held-out parent-fragment task, versus OmniGene mean
  0.312/0.2623 and BLAST 0.856/0.8289. Last-token pooling is weaker for
  OmniGene, ESM-2, and ProtT5, supporting mean pooling as the default embedding
  mode for this sequence-window retrieval task.
- DNA baselines: Nucleotide Transformer 500M completed with negative results;
  DNABERT-2 needs a pinned environment because the current custom-model load is
  incompatible with the installed stack.
- Compare: OmniGene-CPT vs original Gemma4 MoE vs public encoder embeddings
  under identical retrieval setup.
- Success criterion:
  - OmniGene beats or matches original Gemma4 MoE: supports the tokenizer
    expansion + biological CPT contribution.
  - OmniGene best or comparable to public models: keep OmniGene as a strong local sequence-text embedding choice.
  - Public baseline better: de-center OmniGene and make BioRAG model-agnostic.
  - Public DNA baseline also weak: keep DNA dense retrieval as a negative
    result and emphasize routing, alignment verification, and future
    retrieval-specific DNA tuning.

### B3. DRAG Biological Controls

- Status: initial 10k controls completed.
- Parent-collapsed graph: current DNA/protein graph views are already collapsed
  at parent-style nodes.
- k-mer/Jaccard NN graph: cheap sequence-similarity baseline graph; it recovers
  strong family/gene communities, so simple sequence similarity explains part
  of the DRAG biological signal.
- Degree-preserving rewired null: graph topology control; null graphs do not
  show comparable top label signals in the current run.
- Metrics: community purity, GO/Reactome enrichment, shared PubMed communities.
- Success criterion:
  - Vector/hybrid DRAG remains stronger than k-mer and rewired controls.
  - Current outcome: stronger than rewired null, not clearly stronger than k-mer
    for all signals. Keep DRAG as evidence-packaging plus exploratory biology,
    not biological-discovery claim.

## Important Nice-to-Have Blocks

### B4. Swiss-Prot Scale Curve

- Sizes: 100k, 300k, full Swiss-Prot.
- Status: BLAST reference rows completed for 20k, 100k, 300k, and full
  held-out Swiss-Prot. Vector/candidate-BLAST rows are pending matching vector
  indexes.
- Compare: full BLAST vs vector -> candidate BLAST at N=50/100/200/500.
- Metrics: latency, biological Hit@10/MRR, candidate recall@N.
- Success criterion:
  - Candidate route reaches matched accuracy with lower latency at larger scale.
  - If no crossover, keep candidate-BLAST as an ablation only.

### B5. Warm End-to-End Latency

- Batch size: 1.
- Report p50/p95 over 100 protein and 100 DNA queries.
- Decompose: embedding, lookup, BLAST, graph expansion.
- Success criterion:
  - `embed + lookup` clearly below verified route.
  - Otherwise avoid instant-response performance claim.

## Run Order

| Order | Run | Why First | Stop/Go |
| --- | --- | --- | --- |
| 1 | Held-out parent benchmark + leakage report | Fixes biggest reviewer objection | If leakage > 0, stop and fix split |
| 2 | OmniGene held-out parent retrieval | Determines whether dense retrieval survives realistic split | If collapse, shift paper to engineering only |
| 3 | Gemma4 MoE and public protein baselines | Separates base-model capability from bio-tokenizer/CPT gains and removes private-backbone criticism | If public baselines win, make BioRAG model-agnostic |
| 4 | DRAG parent-collapsed + k-mer controls | Determines whether biology can stay a main contribution | If controls fail, keep DRAG exploratory |
| 5 | Swiss-Prot scale curve | Tests systems speed frontier | If no crossover, keep candidate-BLAST as ablation |
| 6 | Warm E2E latency | Supports product/application value | If embedding dominates, report lookup-only |

## Paper Decision Rules

- **3Q-now:** current conservative paper + DRAG showcase + honest limitations.
- **2Q plausible:** held-out benchmark survives, public baselines are competitive, and DRAG controls pass.
- **2Q strong:** above plus Swiss-Prot scale curve shows candidate-BLAST matched-accuracy speed advantage.
- **Do not overclaim:** if held-out dense retrieval or DRAG controls fail, keep BioRAG as local evidence infrastructure.

## First Implementation Tasks

1. Add `scripts/make_parent_fragment_benchmark.py`.
2. Add `scripts/check_benchmark_leakage.py`.
3. Add a parent-level vector index target, separate from the current window index.
4. Run a 50-query smoke test before any full embedding build.
5. Generate `reports/heldout_parent_leakage_report.md` and only then run dense retrieval.
