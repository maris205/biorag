# Evaluation

The evaluation plan follows `init.md` and keeps retrieval metrics separate from agent metrics.

## Retrieval Conditions

Compare at least these systems:

- public API only
- local classical retrieval: SQL / FTS / BLAST
- local vector RAG: OmniGene embeddings
- local DRAG: graph expansion
- local multi-view DRAG: DNA view, protein view, mixed English/sequence view, and unified view
- local Hybrid BioRAG: FTS + BLAST + vector + graph
- local-first with public fallback

The main paper experiment should use `data/biorag_standard_v0` as the shared
dataset substrate. This keeps Standard text records, DNA/protein sequence-window
records, mixed records, and annotated retrieval tasks under one manifest. See
`reports/biorag_research_matrix.md` for the current table that connects dataset,
retrieval, latency, and DRAG biological-structure results.

The paper framing should not claim that vector search replaces BLAST. BLAST has
explicit alignment and statistical assumptions and remains the correct baseline
for exact sequence similarity. The RAG contribution is the unified evidence
layer: sequence vectors, text vectors, graph expansion, and classical biological
tools are compared separately, then combined as a route-gated BioRAG system for
agent-facing retrieval.

## Task Families

- gene and protein lookup
- pathway and GO function lookup
- variant queries
- literature retrieval
- sequence similarity
- multi-hop sequence-to-knowledge questions
- emergent biological structure from text-style sequence graphs

## Retrieval Metrics

- Recall@1, Recall@5, Recall@10
- Hit@k
- MRR
- NDCG@k
- evidence precision
- local coverage
- latency

Latency should be reported at multiple levels when possible:

- cold start, including model load
- warm query embedding
- vector-index lookup
- BLAST/FTS/graph route time
- merge/rerank time
- end-to-end agent evidence-context construction

The current Chroma sequence-window POC is primarily a representation-quality
baseline. GPU speed claims should be evaluated separately with precomputed
embeddings and a GPU-capable ANN backend such as FAISS GPU.

Instant/verified latency decomposition:

```bash
python scripts/benchmark_instant_verified_latency.py \
  --config configs/standard.yaml \
  --output reports/instant_verified_latency_benchmark.json
```

Current 100k BF16 sequence-window Chroma result:

| Profile / component | DNA/cDNA median ms | Protein median ms | Scope |
| --- | ---: | ---: | --- |
| Vector lookup | 5.8997 | 6.6152 | Chroma top-10, query embedding excluded |
| BLAST | 294.5684 | 1081.9300 | local BLAST top-10 |
| Hybrid graph expansion | 0.3540 | 0.3254 | SQLite graph expansion, 12-edge limit |
| Instant vector-only profile | 5.8997 | 6.6152 | lookup after resident embedding service |
| Verified vector+BLAST+graph profile | 300.8221 | 1088.8706 | median route-latency sum |

This supports the engineering architecture in
`reports/instant_verified_biorag_system_design.md`: vector-only instant mode can
provide fast provisional multimodal context, while BLAST and hybrid DRAG run as
verification and evidence-attribution layers. The benchmark excludes model cold
start, query embedding, and LLM generation by design.

The main engineering comparison should therefore include a two-stage
vector-coarse + BLAST-rerank pipeline:

1. vector retrieval produces instant context and top-N candidate
   sequence/entity IDs
2. BLAST reranks or verifies the vector candidate set and supplies alignment
   evidence, with full-database BLAST as the fallback/reference path
3. hybrid DRAG packages vector and BLAST evidence paths for the downstream agent

This avoids framing the paper as "vector versus BLAST" only. The more useful
question is whether vector retrieval improves agent-facing BioRAG by providing
fast, unified, cross-modal candidates that can then be reranked by BLAST and
verified by other biological tools.

Candidate-subset BLAST reranking is now implemented:

```bash
python scripts/evaluate_vector_blast_rerank.py \
  --benchmark benchmarks/sequence_search_100_seed20260516_bio.jsonl \
  --output reports/vector_blast_rerank_eval.json \
  --markdown reports/vector_blast_rerank_summary.md \
  --candidate-limit 50 \
  --final-limit 10 \
  --blast-top-k 50
```

Current result:

| Condition | Exact Hit@10 | Exact MRR | Biological Hit@10 | Biological MRR | Candidate Bio Recall@50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Vector -> candidate BLAST rerank | 0.5700 | 0.4898 | 0.8687 | 0.8687 | 0.8788 |

Candidate-budget sweep:

```bash
python scripts/evaluate_vector_candidate_budget_sweep.py \
  --benchmark benchmarks/sequence_search_100_seed20260516_bio.jsonl \
  --output reports/vector_candidate_budget_sweep_eval.json \
  --markdown reports/vector_candidate_budget_sweep_summary.md \
  --budgets 10,25,50,100,200
```

| Candidate budget | Exact Hit@10 | Exact MRR | Biological Hit@10 | Biological MRR | Candidate Bio Recall@N |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 0.5700 | 0.4898 | 0.8687 | 0.8687 | 0.8788 |
| 100 | 0.6100 | 0.5151 | 0.8990 | 0.8990 | 0.9293 |
| 200 | 0.6500 | 0.5377 | 0.9293 | 0.9293 | 0.9596 |

By modality:

| Category | Budget | Exact Hit@10 | Exact MRR | Biological Hit@10 | Biological MRR | Candidate Bio Recall@N |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DNA/cDNA | 50 | 0.5400 | 0.4167 | 0.8600 | 0.8600 | 0.8600 |
| DNA/cDNA | 200 | 0.6400 | 0.4625 | 0.9600 | 0.9600 | 1.0000 |
| Protein | 50 | 0.6000 | 0.5629 | 0.8776 | 0.8776 | 0.8980 |
| Protein | 200 | 0.6600 | 0.6129 | 0.8980 | 0.8980 | 0.9184 |

Interpretation: this experiment validates the two-stage architecture, but also
shows that candidate-pool recall is the bottleneck. Larger overfetch improves
overall biological Hit@10/MRR to 0.9293 at 200 candidates. DNA/cDNA benefits
strongly, reaching candidate biological recall 1.0000 at 200 candidates, while
protein plateaus earlier at biological Hit@10 0.8980. The next retrieval
improvement should focus on protein-side candidate generation, calibrated vector
scoring, and full-scale graph-expanded candidates before candidate-subset BLAST.

Graph-expanded candidate ablation:

```bash
python scripts/evaluate_vector_graph_blast_rerank.py \
  --benchmark benchmarks/sequence_search_100_seed20260516_bio.jsonl \
  --output reports/vector_graph_blast_rerank_eval.json \
  --markdown reports/vector_graph_blast_rerank_summary.md \
  --seed-limit 50 \
  --graph-neighbors 20 \
  --max-candidates 200
```

| Condition | Exact Hit@10 | Exact MRR | Biological Hit@10 | Biological MRR | Seed Bio Recall | Expanded Bio Recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vector(50) + 10k DRAG expand -> candidate BLAST | 0.5800 | 0.4912 | 0.8687 | 0.8687 | 0.8788 | 0.8788 |

This 10k DRAG ablation adds about 94 graph candidates per query on average, but
does not improve biological recall beyond the vector seed pool. Treat it as a
coverage-limited result: the existing DRAG view graph is useful for biological
meaning analysis, but full 100k or complete sequence graph construction is
needed before making a strong graph-expanded retrieval claim.

FAISS lookup-only benchmark:

```bash
python scripts/benchmark_faiss_lookup.py \
  --config configs/standard.yaml \
  --target protein_sequence_window \
  --limit 100000 \
  --queries 5000 \
  --top-k 10 \
  --batch-size 256 \
  --gpu
```

This benchmark intentionally excludes query embedding, hybrid routing, and graph
expansion. Use it to test the engineering claim that precomputed vector lookup
can scale efficiently on GPU.

Current local vector lookup results:

| Backend | Text / Standard | DNA/cDNA | Protein | Notes |
| --- | ---: | ---: | ---: | --- |
| Chroma | 4.6924 ms | 5.9630 ms | 6.0948 ms | top-10, sampled existing embeddings, query embedding excluded |
| FAISS CPU `IndexFlatIP` | 8.3346 ms | 15.4626 ms | 15.6090 ms | top-10, brute-force flat index |
| FAISS GPU | blocked | blocked | blocked | `faiss-gpu-cu12` detects 1 GPU but lacks Blackwell `sm_120` kernels |

The benchmark script has a Blackwell guard for `--gpu`. On the current RTX PRO
6000 Blackwell machine, a compatible FAISS GPU build/container is needed before
reporting GPU lookup speed.

Backend roles:

- Chroma: simple RAG POC and CRUD-complete local vector database.
- FAISS GPU: easiest local lookup-speed benchmark.
- Milvus GPU: production-scale serving benchmark for very large indexes and
  high concurrency.

## Multi-View DRAG Metrics

- cross-view entity alignment rate: sequence hit to gene/protein/text evidence
- graph path completeness: sequence to annotation to source evidence
- biological cluster enrichment: GO, pathway, or family labels within retrieved neighborhoods
- view contribution: answer quality after removing DNA, protein, or mixed-text views
- rule-free emergence check: compare text-style graphs against later BLAST/domain/rule-enriched graphs

The first rule-free enrichment check is now implemented in
`scripts/evaluate_vector_neighborhood_enrichment.py`. It evaluates pure vector
neighbors before adding BLAST/domain/pathway biological rules, excludes
same-parent windows, deduplicates parent records, and compares against a random
neighbor baseline from the same collection.

Current 100-anchor result on BF16 100k sequence-window collections:

| Target | Match | Vector Hit@10 | Random Hit@10 | Vector P@10 | Random P@10 |
| --- | --- | ---: | ---: | ---: | ---: |
| protein windows | `GN=` / gene symbol | 0.4300 | 0.0200 | 0.1710 | 0.0020 |
| DNA/cDNA windows | gene ID | 0.6900 | 0.0600 | 0.2460 | 0.0060 |
| DNA/cDNA windows | gene symbol | 0.7188 | 0.0625 | 0.2563 | 0.0063 |
| DNA/cDNA windows | any identity | 0.7100 | 0.0600 | 0.2570 | 0.0060 |

This is a DRAG-facing signal: a text-style vector-neighbor graph contains
biological-label enrichment before explicit biological-rule edges are added. It
should be reported as neighborhood enrichment, not as proof of biological
mechanism. Follow-up layers are now partially complete through graph community
analysis, community purity, GO/Reactome functional enrichment, and PubMed
literature support; Pfam/domain enrichment and stronger BLAST/domain-rule
ablations remain open.

The first rendered view graphs are stored under `reports/figures/`:

| View | Nodes | Edges | Communities | Modularity | Main label signal |
| --- | ---: | ---: | ---: | ---: | --- |
| DNA/cDNA windows | 170 | 2548 | 3 | 0.3052 | `IGLV` and `IGHV` family communities |
| Protein windows | 340 | 3082 | 7 | 0.3621 | `YWHAB`-enriched community |

See `reports/drag_view_graph_visualization.md` for the generated HTML/SVG
figure outputs and interpretation.

Community-level purity is now implemented:

```bash
python scripts/evaluate_drag_biological_purity.py \
  --output reports/drag_gene_family_purity_10k.json \
  --markdown reports/drag_gene_family_purity_10k.md
```

Key DRAG biological-purity signals:

| Graph | Signal |
| --- | --- |
| DNA/cDNA vector-only | IGKV 50/64 labeled nodes in a 66-node community; IG_D and IG_J compact modules reach 1.0 labeled purity |
| DNA/cDNA hybrid | IGKV 51/58 labeled nodes in a 60-node community; IG_D/IG_J compact modules preserved |
| Protein vector-only | `pgl` 51/251 labeled nodes in a 306-node community |
| Protein hybrid | `pgl` 71/467 and `yfbR` 42/62 labeled-neighbor modules while retaining a connected graph |

Report this as biological neighborhood/community enrichment, not as proof that
vector edges have the same interpretation as BLAST alignments.

Functional enrichment is now implemented:

```bash
python scripts/evaluate_drag_functional_enrichment.py \
  --output reports/drag_functional_enrichment_10k.json \
  --markdown reports/drag_functional_enrichment_10k.md
```

This maps graph nodes through local HGNC/UniProt/NCBI cross-references and uses
local GOA human, NCBI `gene2go`, UniProt2Reactome, and NCBI2Reactome files.
Enrichment is tested against annotated graph nodes with Benjamini-Hochberg
correction.

| Graph | GO annotated | Reactome annotated | Top functional signal |
| --- | ---: | ---: | --- |
| DNA/cDNA vector-only | 155 | 68 | GO proton transmembrane transport; Reactome Metabolism |
| DNA/cDNA BLAST-only | 155 | 68 | GO immunoglobulin mediated immune response |
| DNA/cDNA hybrid | 155 | 68 | GO proton transmembrane transport; Reactome Metabolism |
| Protein vector-only | 63 | 213 | GO intracellular protein localization; Reactome steroid hormone metabolism |
| Protein BLAST-only | 63 | 213 | GO postsynaptic membrane; Reactome GPCR downstream signalling |
| Protein hybrid | 63 | 213 | GO focal adhesion; Reactome TP53 regulates metabolic genes |

Report this as community-level functional annotation coherence, not as proof of
causal mechanism.

Literature support is now implemented:

```bash
python scripts/evaluate_drag_literature_support.py \
  --output reports/drag_literature_support_10k.json \
  --markdown reports/drag_literature_support_10k.md
```

This maps graph nodes through local HGNC/NCBI cross-references and then uses
local NCBI `gene2pubmed.gz` to test whether graph communities share PubMed
evidence anchors.

| Graph | PubMed nodes | Unique PMIDs | Shared-PMID communities | Top shared PMID |
| --- | ---: | ---: | ---: | --- |
| DNA/cDNA vector-only | 196 | 1,092 | 7 | PMID:19050702, 12/63, q=0.000314 |
| DNA/cDNA BLAST-only | 196 | 1,092 | 20 | PMID:8490662, 9/24, q=0.000596 |
| DNA/cDNA hybrid | 196 | 1,092 | 6 | PMID:20301403, 11/59, q=0.000312 |
| Protein vector-only | 63 | 5,856 | 4 | PMID:11697890, 6/8, q=0.000146 |
| Protein BLAST-only | 63 | 5,856 | 13 | PMID:25402006, 4/4, q=0.000682 |
| Protein hybrid | 63 | 5,856 | 4 | PMID:27432908, 8/8, q=0.000159 |

Report this as shared literature evidence structure for citation and case-study
generation, not as a causal biological mechanism.

## Agent Metrics

- final answer accuracy
- tool correctness
- evidence grounding rate
- citation correctness
- trace completeness
- hallucination rate
- workflow success

## Initial Smoke Set

The first smoke suite should include:

```text
BRCA1
TP53
EGFR
KRAS G12D
DNA repair
apoptosis
MAPK signaling
MVKVGVNGFGRIGRLVTRA
```

These cover FTS, graph expansion, ClinVar summaries, Reactome/GO lookup, and BLAST sequence search.

## Basic Search Benchmark

The first reproducible benchmark is `benchmarks/basic_search.jsonl`. It uses exact expected IDs for:

- gene lookup: BRCA1, TP53, EGFR, KRAS, PTEN
- pathway lookup: DNA repair, apoptosis, MAPK signaling
- protein sequence retrieval: Swiss-Prot fragments with known accessions
- DNA sequence retrieval: Ensembl cDNA fragments with known transcript IDs

Run:

```bash
python -m dnarag.cli eval-search \
  --config configs/standard.yaml \
  --benchmark benchmarks/basic_search.jsonl \
  --conditions classical,vector,drag,hybrid,hybrid_gated \
  --limit 10 \
  --output reports/basic_search_eval.json
```

The compared conditions are:

- `classical`: SQLite FTS + local BLAST
- `vector`: OmniGene embeddings + Chroma
- `drag`: FTS-seeded graph expansion
- `hybrid`: ungated FTS + BLAST + graph + vector
- `hybrid_gated`: route-gated Hybrid BioRAG, using BLAST + vector for pure
  sequence queries and FTS + graph + vector for natural-language queries

This deliberately evaluates retrieval before agent answer generation. Agent-system evaluation should reuse the same benchmark IDs but add answer quality, grounding, citation correctness, and workflow success.

Current basic-search result, after adding Ensembl cDNA BLASTN:

| Condition | Hit@1 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: |
| `fts` | 0.6667 | 0.6667 | 0.6667 | 78.128 |
| `blast` | 0.2500 | 0.3333 | 0.2917 | 356.531 |
| `classical` | 0.9167 | 1.0000 | 0.9583 | 419.446 |
| `vector` | 0.0000 | 0.0000 | 0.0000 | 1482.673 |
| `drag` | 0.6667 | 0.6667 | 0.6667 | 4049.735 |
| `hybrid` | 0.9167 | 1.0000 | 0.9583 | 5592.487 |

Interpretation:

- Classical FTS + BLAST is the correct baseline for exact lookup tasks.
- Hybrid reaches the same recall but is slower until route gating is added.
- Vector-only is not appropriate for exact entity/accession lookup in the current prompt/index setup; it should be evaluated separately on semantic-neighbor tasks.

Full output: `reports/basic_search_eval.json`.
Readable summary: `reports/basic_search_summary.md`.

## Sequence-Window POC

`benchmarks/sequence_search.jsonl` isolates protein and DNA/cDNA fragment
retrieval from gene/pathway text lookup. It targets the dedicated Chroma
collections `protein_sequence_window` and `dna_sequence_window`, built with
OmniGene CPT embeddings over sequence-only windows.

This benchmark is a sanity check for the sequence-vector view, not the main
paper claim. A useful result is that vectors are close enough to BLAST on basic
sequence retrieval to participate in a unified BioRAG stack. Stronger paper
evidence should come from mixed text/sequence queries, cross-modal evidence
assembly, DRAG graph enrichment, and agent grounding.

For paper-scale experiments on the RTX PRO 6000 96 GB machine, use the BF16
merged checkpoint as the main model:

```bash
bash scripts/download_omnigene_merged_autodl.sh
bash scripts/build_omnigene_merged_sequence_windows.sh protein_sequence_window,dna_sequence_window 10000 128 64 8
```

Then scale to `100000` windows and full collections after checking that the
model is not CPU-offloaded and Chroma writes are stable. The 4-bit path below is
kept as a low-memory/efficiency baseline rather than the main paper result.

Current BF16 100k sequence-window result:

| Condition | Hit@1 | Hit@5 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `blast` | 0.7500 | 1.0000 | 1.0000 | 0.8750 | 812.242 |
| `vector` | 0.7500 | 0.7500 | 0.7500 | 0.7500 | 5236.183 |
| `hybrid_gated` | 0.7500 | 1.0000 | 1.0000 | 0.8750 | 5808.516 |

The 100k run is the more realistic current paper baseline. Vector-only remains
competitive on three of four exact-fragment tasks but falls behind BLAST on an
immunoglobulin-heavy cDNA fragment: `dna_enst00622028_fragment` is rank 30 in
the vector top-100 diagnostic run. This is useful rather than fatal: it shows
why the practical system should be route-gated. BLAST supplies exact sequence
evidence, while vector neighborhoods supply RAG/DRAG context.

Build notes:

- 100,000 protein windows built in 2,536.6 seconds.
- 100,000 DNA/cDNA windows built in 2,240.9 seconds.
- Batch size 16 used about 58.5 GB of VRAM on the RTX PRO 6000 96 GB.
- Chroma persist directory was about 21 GB after the 100k+100k run.

The generated 100-query benchmark `benchmarks/sequence_search_100.jsonl` is a
larger strict-ID sanity set sampled from the 100k Chroma window collections. It
contains 50 protein and 50 DNA/cDNA queries, with balanced `exact_window`,
`prefix_96`, `suffix_96`, `middle_short`, and `mutated_96` query types.

Strict-ID 100-query result:

| Condition | Hit@1 | Hit@5 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `blast` | 0.5100 | 0.6600 | 0.7800 | 0.5882 | 730.180 |
| `vector` | 0.4200 | 0.5300 | 0.5700 | 0.4703 | 434.565 |
| `hybrid_gated` | 0.5100 | 0.6600 | 0.7800 | 0.5954 | 1019.733 |

A second 100-query sample with seed `20260516` gives the same qualitative
conclusion:

| Condition | Hit@1 | Hit@5 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `blast` | 0.4700 | 0.5900 | 0.7300 | 0.5425 | 739.838 |
| `vector` | 0.3500 | 0.4800 | 0.5000 | 0.4063 | 435.237 |
| `hybrid_gated` | 0.4700 | 0.5900 | 0.7300 | 0.5516 | 1028.810 |

Mean over the two generated 100-query seeds:

| Condition | Hit@1 | Hit@5 | Hit@10 | MRR |
| --- | ---: | ---: | ---: | ---: |
| `blast` | 0.4900 | 0.6250 | 0.7550 | 0.5654 |
| `vector` | 0.3850 | 0.5050 | 0.5350 | 0.4383 |
| `hybrid_gated` | 0.4900 | 0.6250 | 0.7550 | 0.5735 |

The combined table should not be the main paper table. Protein and DNA/cDNA
should be reported separately:

| Condition | Modality | Hit@1 | Hit@5 | Hit@10 | MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| `blast` | protein | 0.8800 | 0.9400 | 0.9600 | 0.9110 |
| `blast` | DNA/cDNA | 0.1000 | 0.3100 | 0.5500 | 0.2197 |
| `vector` | protein | 0.3900 | 0.5200 | 0.5500 | 0.4486 |
| `vector` | DNA/cDNA | 0.3800 | 0.4900 | 0.5200 | 0.4280 |
| `hybrid_gated` | protein | 0.8800 | 0.9400 | 0.9600 | 0.9121 |
| `hybrid_gated` | DNA/cDNA | 0.1000 | 0.3100 | 0.5500 | 0.2349 |

The split summary is stored in
`reports/sequence_window_bf16_100k_100query_split_summary.md`. The separated
benchmark JSONL files are also written under `benchmarks/` for reruns.

By modality, BLAST and `hybrid_gated` reach protein Hit@10 `1.0000`, while
vector protein Hit@10 is `0.5800`. DNA/cDNA strict-parent Hit@10 is `0.5600`
for both BLAST and vector, showing that exact transcript recovery is a harsh
metric for repeated or near-duplicate cDNA windows.

Vector by query type shows a clear engineering issue: `exact_window` Hit@10 is
`0.9000` and `prefix_96` Hit@10 is `0.9500`, but `middle_short` is `0.3500` and
`suffix_96` is `0.2000`. This suggests the next retrieval experiment should
improve query-windowing, use denser/overlapping indexes, or add reranking before
making broader sequence-search claims.

An experimental vector reranker is available through
`DNARAG_VECTOR_SEQUENCE_RERANK=1`. It reranks sequence-window vector hits with a
lightweight sequence-overlap score after vector retrieval and parent-record
grouping. This is an engineering ablation, not a replacement for BLAST
statistics.

On the two generated 100-query seeds, this reranker improves mean vector Hit@10
from `0.5350` to `0.6950` and mean MRR from `0.4383` to `0.6041`. The largest
improvements are on `suffix_96`, `middle_short`, and `mutated_96` queries,
which were the main raw-vector failure modes.

For paper evaluation, report both strict-ID and biological-equivalence metrics.
The `_bio` benchmark variants add expected biological fields from sequence
headers:

- protein `GN=` gene names where available.
- DNA/cDNA Ensembl gene IDs, gene symbols, gene/transcript biotypes, and a
  first pass of immune gene-family prefixes.

The current two-seed `_bio` result changes the interpretation substantially:

| Condition | Strict Hit@10 | Strict MRR | Bio Hit@10 | Bio MRR |
| --- | ---: | ---: | ---: | ---: |
| `blast` | 0.7550 | 0.5654 | 0.9898 | 0.9772 |
| `vector` | 0.5350 | 0.4383 | 0.7751 | 0.6677 |
| `vector_rerank` | 0.6950 | 0.6041 | 0.8822 | 0.8758 |
| `hybrid_gated` | 0.7550 | 0.5735 | 0.9898 | 0.9780 |

Split by modality:

| Condition | Modality | Strict Hit@10 | Strict MRR | Bio Hit@10 | Bio MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| `blast` | protein | 0.9600 | 0.9110 | 0.9898 | 0.9845 |
| `blast` | DNA/cDNA | 0.5500 | 0.2197 | 0.9900 | 0.9704 |
| `vector` | protein | 0.5500 | 0.4486 | 0.7273 | 0.6565 |
| `vector` | DNA/cDNA | 0.5200 | 0.4280 | 0.8200 | 0.6782 |
| `vector_rerank` | protein | 0.6700 | 0.6235 | 0.8102 | 0.8026 |
| `vector_rerank` | DNA/cDNA | 0.7200 | 0.5847 | 0.9500 | 0.9450 |
| `hybrid_gated` | protein | 0.9600 | 0.9121 | 0.9898 | 0.9852 |
| `hybrid_gated` | DNA/cDNA | 0.5500 | 0.2349 | 0.9900 | 0.9711 |

This supports a more defensible claim than strict-ID alone: BLAST remains the
strong exact sequence baseline, while the vector layer retrieves biologically
meaningful neighborhoods often enough to serve as a unified BioRAG candidate
space. The sequence-aware reranker improves the vector layer without changing
the embedding model, which suggests that ranking calibration and DRAG expansion
are the next high-value system layers.

This is still not a full functional-biology claim. The next paper metrics
should score same-gene, same-family, BLAST-equivalent, GO/pathway-enriched, and
DRAG-path-equivalent hits separately.

Earlier BF16 10k sequence-window result:

| Condition | Hit@1 | Hit@5 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `blast` | 0.7500 | 1.0000 | 1.0000 | 0.8750 | 821.263 |
| `vector` | 0.7500 | 0.7500 | 1.0000 | 0.7750 | 4479.744 |

This 10k result was the first locked sequence-vector smoke baseline. It shows
that vectors can reach BLAST Hit@10 when the distractor set is small. The 100k
run above is more informative for paper claims because it includes more
near-neighbor competition.

Build notes:

- 10,000 protein windows built in about 245 seconds.
- 10,000 DNA/cDNA windows built in about 221 seconds.
- Batch size 16 used about 57 GB of VRAM on the RTX PRO 6000 96 GB.
- The vector route overfetches raw Chroma window hits before parent-record
  deduplication; otherwise top-k deduplication can hide the correct parent.
  The default raw window overfetch is at least 1,000 hits and is capped at
  5,000 hits via `DNARAG_VECTOR_WINDOW_RAW_MIN`,
  `DNARAG_VECTOR_WINDOW_RAW_MULTIPLIER`, and `DNARAG_VECTOR_WINDOW_RAW_MAX`.

Build a small 4-bit POC:

```bash
bash scripts/build_omnigene_4bit_sequence_windows.sh protein_sequence_window,dna_sequence_window 1024 128 64 1
```

Evaluate BLAST against the sequence-window vector route:

```bash
python -m dnarag.cli eval-search \
  --config configs/standard_4bit.yaml \
  --benchmark benchmarks/sequence_search.jsonl \
  --conditions blast,vector \
  --limit 10 \
  --output reports/sequence_window_eval.json
```

Current small POC result:

| Condition | Hit@1 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: |
| `blast` | 0.7500 | 1.0000 | 0.8750 | 1789.964 |
| `vector` | 1.0000 | 1.0000 | 1.0000 | 10168.009 |

Interpretation:

- Sequence-window vectors can retrieve exact held-out fragments when the target
  windows are present; this fixes the earlier whole-record GGUF sequence-vector
  failure.
- This is not yet a full-scale SOTA claim: the POC index has 36 protein windows
  and 16 DNA windows, intentionally covering the smoke benchmark.
- The local 32 GB GPU loads the transformers 4-bit checkpoint but uses about
  28 GB VRAM and CPU offload, so latency is much higher than BLAST. Full
  experiments should shard the build or use larger GPU memory.
