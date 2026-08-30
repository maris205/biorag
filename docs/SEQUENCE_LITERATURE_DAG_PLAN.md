# Sequence-Literature Evidence DAG Plan

## Motivation

Plain literature RAG and paper citation DAGs are already common. The stronger
BioRAG-DRAG direction is sequence-conditioned literature discovery: a user starts
from a protein sequence, and the system returns papers through explicit
biological evidence paths.

Working name:

```text
BioRAG-SeqLit-DAG
```

Core path:

```text
query protein sequence
  -> candidate proteins / homologs / sequence-neighbor proteins
  -> domains / families / GO terms / pathways
  -> curated literature references
  -> paper metadata and evidence records
```

The first version should use curated public database links rather than extracting
relations from paper full text. This makes the resource reproducible, auditable,
and easier to publish as a public dataset.

## Paper Claim

BioRAG-DRAG contributes a reusable protein sequence-to-literature evidence DAG
that supports sequence-first retrieval, graph-grounded paper discovery, and
agent-ready biological evidence assembly.

The claim is not that vector retrieval replaces BLAST. The claim is that BLAST,
specialized protein embeddings, curated annotations, and literature references
can be unified into one sequence-conditioned RAG/DAG resource.

## Current Evidence To Reuse

The existing held-out protein fragment experiments already support a
model-agnostic sequence-entry design:

| Protein embedding | Pooling | Bio Hit@10 | Bio MRR | Recall@200 |
|---|---:|---:|---:|---:|
| OmniGene-4-CPT BF16 | mean | 0.3120 | 0.2623 | 0.4940 |
| ESM-2 650M | mean | 0.6560 | 0.5764 | 0.7340 |
| ProtT5-XL-UniRef50 | mean | 0.7780 | 0.7158 | 0.8460 |

Mean pooling is consistently stronger than last-token pooling for OmniGene,
ESM-2, and ProtT5 on the completed protein fragment task. Therefore the first
SeqLit-DAG build should default to mean-pooled protein embeddings when vectors
are needed. OmniGene remains useful as the unified biological-language backbone,
but protein-only sequence retrieval should allow specialized encoders.

No GPU is needed for the initial schema, parser, graph build, SQLite/Parquet
export, or static figure. GPU is only needed when rebuilding large embedding
indexes with OmniGene, ESM-2, ProtT5, or future protein encoders.

## Data Sources

Start with a small Swiss-Prot sample, then scale to full Swiss-Prot.

Required v0 sources:

- UniProtKB Swiss-Prot entries: accession, sequence, protein name, organism,
  gene names, comments, cross-references, GO annotations, keywords, and curated
  PubMed references.
- GO term metadata: term name, namespace, and parent relations.
- PubMed or Europe PMC metadata: PMID, title, abstract when available, year,
  journal, authors, and DOI.

Useful v1 extensions:

- InterPro and Pfam domain/family mappings.
- Reactome UniProt-to-pathway mappings.
- AlphaFold DB links by UniProt accession for later structure-modal RAG.
- Citation edges between papers when metadata is available.

## Graph Model

The stored graph should be a heterogeneous graph, because biological relations
are naturally cyclic. The paper-facing view should expose a DAG by following
typed evidence paths in one direction from sequence to literature.

### Node Types

| Node type | Key | Main fields |
|---|---|---|
| `protein` | UniProt accession | sequence, length, reviewed flag, organism, gene symbols, protein name |
| `protein_window` | accession + offset | sequence window, offset, length, parent accession |
| `domain` | InterPro/Pfam ID | name, source, description |
| `family` | UniProt/InterPro/Pfam family ID | name, source |
| `go_term` | GO ID | name, namespace, definition |
| `pathway` | Reactome ID | name, organism |
| `paper` | PMID/DOI | title, abstract, year, journal, authors |
| `evidence` | annotation evidence ID | evidence code, source database, annotation text |
| `organism` | taxonomy ID | scientific name |
| `gene` | gene symbol or stable gene ID | symbol, synonyms, organism |

### Edge Types

| Edge type | From -> To | Notes |
|---|---|---|
| `has_window` | protein -> protein_window | local retrieval windows |
| `sequence_candidate` | query/window -> protein | vector, BLAST, or hybrid candidate edge |
| `has_domain` | protein -> domain | InterPro/Pfam/UniProt xref |
| `member_of_family` | protein -> family | family or clan relation |
| `annotated_with_go` | protein -> go_term | keep GO evidence code when available |
| `participates_in_pathway` | protein -> pathway | Reactome mapping |
| `supported_by_paper` | protein/domain/GO/pathway/evidence -> paper | curated literature link |
| `describes_evidence` | evidence -> paper | stores evidence-level citation |
| `from_organism` | protein/gene -> organism | taxonomy edge |
| `encoded_by` | protein -> gene | gene symbol or stable ID |
| `cites` | paper -> paper | optional, year-directed when available |

### DAG View

For retrieval and visualization, expose directed paths such as:

```text
query_sequence
  -> protein_candidate
  -> domain_or_go_or_pathway
  -> evidence_record
  -> paper
```

This avoids claiming that the whole biology graph is acyclic while still giving
the agent an auditable DAG-shaped evidence pack.

## First Implementation Scope

The first version should be deliberately small and complete:

1. Build a `swissprot_sample` corpus from reviewed UniProt proteins.
2. Keep proteins that have at least one PubMed reference.
3. Parse or export:
   - protein nodes
   - GO nodes
   - paper nodes
   - evidence edges
   - organism and gene nodes
4. Save graph outputs as:
   - `graph.sqlite`
   - `nodes.parquet` or `nodes.jsonl`
   - `edges.parquet` or `edges.jsonl`
   - `manifest.json`
5. Add a Chroma-ready document export:
   - protein sequence records
   - annotation text records
   - paper title/abstract records
   - mixed sequence-annotation-paper evidence path records
6. Generate one publication figure showing `protein -> domain/GO/family -> PubMed`.

Suggested paths:

```text
configs/seq_lit_dag_swissprot_sample.yaml
scripts/build_seq_lit_dag.py
dnarag/seq_lit_dag/schema.py
dnarag/seq_lit_dag/build.py
docs/SEQUENCE_LITERATURE_DAG_PLAN.md
reports/seq_lit_dag_sample_report.md
figures/gen_fig7_seq_lit_dag.py
figures/fig7_seq_lit_dag.pdf
```

## Minimal Evaluation

The v0 evaluation should prove the resource is useful before optimizing models.

### Task A: Sequence-To-Paper Retrieval

Input: a protein sequence or sequence fragment.

Output: ranked papers connected through candidate proteins and curated
annotations.

Baselines:

- BLAST -> UniProt candidates -> PubMed references.
- ProtT5 mean vector -> UniProt candidates -> PubMed references.
- ESM-2 mean vector -> UniProt candidates -> PubMed references.
- OmniGene mean vector -> UniProt candidates -> PubMed references.
- Keyword PubMed search using protein/gene names.

Metrics:

- paper recall@K against curated UniProt references
- candidate protein biological Hit@K
- evidence path completeness
- citation coverage per query

### Task B: Evidence DAG Quality

For each query, measure whether retrieved paths contain coherent biological
intermediate nodes.

Metrics:

- GO/pathway/domain enrichment against random candidate proteins
- family/domain consistency
- percentage of answers with at least one paper-backed evidence path
- average path length and number of distinct evidence types

### Task C: Agent Utility

Use the DAG as an evidence pack for answer generation.

Conditions:

- vector-only sequence RAG
- BLAST-only sequence lookup
- BLAST + vector candidate union
- SeqLit-DAG evidence pack

Metrics:

- citation correctness
- answer evidence coverage
- hallucinated citation rate
- latency split: lookup-only, embedding, BLAST, graph expansion, end-to-end

## Hugging Face Dataset Release

Publish a versioned dataset rather than large generated indexes in Git.

Proposed repository:

```text
dnagpt/BioRAG-SeqLit-DAG
```

Files:

```text
README.md
dataset_card.md
manifest.json
schema.json
nodes.parquet
edges.parquet
documents.jsonl.gz
sample_queries.jsonl
checksums.txt
```

Versioning:

- `v0.1-swissprot-sample`: small reproducible sample for paper figures and tests.
- `v0.2-swissprot-full`: full Swiss-Prot graph.
- `v0.3-plus-interpro-reactome`: adds domain/family/pathway enrichments.
- monthly or quarterly rebuild tags after the first public release.

Do not upload raw third-party databases if redistribution terms are unclear.
Instead upload derived graph tables where allowed, plus scripts, manifests, and
exact source version metadata.

## Paper Integration

Add this as a main contribution, not just an appendix:

1. A sequence-conditioned literature discovery task.
2. A public protein sequence-to-literature evidence DAG.
3. A BioRAG retrieval pipeline that combines BLAST, specialized protein
   embeddings, curated annotations, and literature references.
4. Evidence-DAG analysis showing that sequence-derived paths recover coherent
   biological annotations and citations.

Suggested title direction:

```text
BioRAG-DRAG: Sequence-Conditioned Literature Evidence Graphs for Biological Retrieval-Augmented Generation
```

The old vector-vs-BLAST results should become support for the candidate layer.
The new central novelty is that a raw protein sequence can be used as an entry
point into literature evidence.

## Immediate CPU-Only Milestone

No GPU is required for this milestone.

1. Define the schema and config.
2. Download or reuse a small Swiss-Prot subset.
3. Parse protein, GO, PubMed, organism, and gene links.
4. Build SQLite and JSONL/Parquet graph outputs.
5. Export Chroma-ready documents.
6. Generate a sample graph figure.
7. Write `reports/seq_lit_dag_sample_report.md`.
8. Add a short subsection and figure placeholder to the LaTeX paper.

GPU checkpoint:

- Reopen GPU only when building or refreshing large-scale sequence embeddings
  for ProtT5, ESM-2, OmniGene, or when benchmarking FAISS GPU lookup.

## Current v0 Sample Build

The first CPU-only sample now builds from the local Standard raw data:

```bash
python scripts/build_seq_lit_dag.py \
  --config configs/seq_lit_dag_swissprot_sample.yaml \
  --output data/seq_lit_dag_swissprot_sample \
  --limit-proteins 200 \
  --max-go-annotations-per-protein 8 \
  --max-windows-per-protein 2 \
  --pubmed-xml-limit 0 \
  --reset
```

Current sample counts:

| Item | Count |
|---|---:|
| proteins | 200 |
| GO annotations | 985 |
| unique PMIDs | 228 |
| graph nodes | 2,231 |
| graph edges | 5,240 |
| Chroma-ready documents | 1,185 |
| sample queries | 50 |

`--pubmed-xml-limit 0` avoids scanning the 44 GB local PubMed baseline. The
implemented resumable EFetch cache enriches all 228 referenced PMIDs and is
loaded with `--pubmed-cache`; keeping the cache outside the reset output path
makes rebuilds deterministic.

The CPU milestone now also persists all 1,185 documents in Chroma using a
clearly labeled hashing smoke-test backend. A 50-query in-index path sanity run
checks graph-oracle, k-mer, and batched BLAST candidate routes. All 50 paths
recover the indexed parent and at least one expected PMID at protein top-10 and
paper top-50. This is pipeline evidence only: the queries are windows from the
indexed parents and must not be interpreted as held-out biological retrieval.
The CPU run measured `91.7 ms/query` for local k-mer candidates and an amortized
`3.48 s/query` for one batched BLAST run against the full local Swiss-Prot DB;
controlled warm-cache and GPU latency experiments remain pending.

The first GPU model-integration run is also complete on 1,275 windows from 200
proteins and 50 in-index queries:

| Encoder | Protein Hit@1 | Protein Hit@10 | Protein MRR | Paper Recall@50 | E2E ms/query |
|---|---:|---:|---:|---:|---:|
| ProtT5-XL mean | 1.000 | 1.000 | 1.000 | 1.000 | 2.88 |
| ESM-2 650M mean | 0.960 | 1.000 | 0.977 | 1.000 | 2.67 |
| OmniGene-4-CPT BF16 mean | 0.900 | 0.940 | 0.914 | 0.947 | 52.28 |

This supports modality-aware encoder routing rather than an OmniGene-only
retrieval claim. It also confirms that window indexing plus parent collapse is
required; direct fragment-to-full-protein mean pooling was weak. The next
claim-bearing experiment is a held-out parent/family sequence-to-paper split.

The first held-out function-to-paper pilot is now complete without GPU. Scaling
the curated graph from 200 to 2,000 proteins yields 99 held-out queries, 1,901
index proteins, 132 low-frequency GO labels, and 377 index-side PMIDs, with zero
exact-parent or full-sequence substring leakage. BLAST is stronger at top-10
candidate ranking, while k-mer retrieval at top-50 broadens paper coverage over
random. This remains the accession-masked application split rather than a
family-independent biological benchmark.

The fixed-split GPU run is complete. At top-50 candidates, ProtT5 reaches paper
Hit/Recall `0.465/0.248`, ESM-2 `0.364/0.203`, BLAST `0.242/0.135`, k-mer
`0.313/0.147`, and random `0.071/0.025`. ProtT5's paired paper-coverage gains
over BLAST exclude zero at the 95% bootstrap level, while its candidate-MRR
gain does not. This is evidence for complementary sequence-conditioned
literature discovery, not evidence that dense retrieval supersedes alignment.

A simple ProtT5+BLAST RRF ablation reduces paper coverage and should remain a
negative engineering result. The next combination experiment should use vector
coarse selection followed by candidate-subset BLAST reranking with unaligned
vector candidates retained.

## Cluster-Held-Out Application Controls

The sequence-family audit is now implemented as two complementary 100-query
controls over the same 2,000-protein resource:

| Split | Index proteins | Extra cluster exclusions | ProtT5 Hit@10 / MRR | BLASTP Hit@10 / MRR |
|---|---:|---:|---:|---:|
| Observed UniRef50 cluster | 1,892 | 8 | 0.430 / 0.317 | 0.340 / 0.257 |
| Identity-30 component stress test | 1,732 | 168 | 0.220 / 0.154 | 0.150 / 0.108 |

The UniRef50 sample is highly deduplicated: only 8 of the selected query
clusters contain another source protein. It is therefore a standard
same-UniRef50-cluster leakage control but not a strong family-diversity sample.
The identity-30 split removes every BLASTP connected component member meeting
30% pair identity and 80% shorter-sequence coverage, and deliberately selects
100 non-singleton components. It is a harder cluster-stratified stress test,
not a natural-prevalence benchmark or Pfam-clan holdout.

Paired query bootstrap intervals support a complementary dense route. ProtT5
minus BLASTP MRR is `+0.061 [0.004, 0.120]` on UniRef50 and
`+0.047 [0.008, 0.091]` on identity-30. These labels measure recovery of an
index protein sharing a low-frequency GO term and index-side GOA literature,
not alignment correctness. Reciprocal-rank fusion is not robust: it changes
identity-30 MRR by `-0.028 [-0.054, -0.007]` relative to ProtT5.

The Agent-facing result uses 50 protein candidates and only 20 papers. ProtT5,
BLASTP, and random strict typed-path rates are `0.390/0.340/0.040` on UniRef50
and `0.190/0.160/0.020` on identity-30. On a frozen 67-query UniRef50 test split,
Graph-IDF improves literature F1 over rank-first by
`+0.0178 [0.0030, 0.0322]`; the identity-30 delta is unresolved. Graph-IDF can
therefore be claimed as evidence compression and literature ordering in one
standard control, not as a general function-retrieval improvement.

The consolidated results, engineering latency, oracle gaps, and claim boundary
are recorded in `reports/seq_lit_cluster_heldout_evaluation.md`. The next
claim-bearing expansion should use a larger taxonomy-diverse corpus with Pfam
clan, species, and temporal controls rather than further tuning on this 2k
sample.
