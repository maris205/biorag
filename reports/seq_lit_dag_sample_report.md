# BioRAG-SeqLit-DAG Sample Report

This CPU-built sample links protein sequences to curated GO evidence and PubMed references.

## Build

- Rebuilt with PubMed cache: `2026-07-20`
- GPU required: `False`
- Output: `data/seq_lit_dag_swissprot_sample/graph.sqlite`

## Counts

- Proteins: `200`
- GO annotations: `985`
- Unique PMIDs: `228`
- PubMed metadata records: `228 / 228`
- Graph nodes: `2231`
- Graph edges: `5240`
- Chroma-ready documents: `1185`
- Sample sequence-to-literature queries: `50`

## Evidence Codes

- `IPI`: 621
- `IDA`: 256
- `IMP`: 76
- `HDA`: 20
- `HTP`: 5
- `EXP`: 4
- `IEP`: 2
- `IGI`: 1

## GO Aspects

- `F`: 722
- `P`: 144
- `C`: 119

## Example DAG Paths

- `A5X5Y0` -> `GO:0005515` protein binding -> `PMID:17392525`
- `A1A5B4` -> `GO:0005229` intracellularly calcium-gated chloride channel activity -> `PMID:22946059`
- `A6NJG6` -> `GO:1990837` sequence-specific double-stranded DNA binding -> `PMID:28473536`
- `A1IGU5` -> `GO:0072583` clathrin-dependent endocytosis -> `PMID:30926623`
- `A6H8Y1` -> `GO:0005515` protein binding -> `PMID:16542149`

## Interpretation

The sample is a curated sequence-conditioned literature resource, not a full text-mined paper graph. The main paper claim should be that protein sequences can enter a reusable evidence DAG through classical sequence candidates, specialized protein embeddings, curated annotations, and PubMed references.

## CPU Path Sanity

The 50 generated protein-window queries were run through graph-oracle, k-mer
Jaccard, and batched BLAST candidate routes. At protein top-10 and paper top-50,
all three routes completed 50/50 expected parent-to-PMID paths. These are
in-index pipeline checks, not held-out homology results and not evidence that
k-mer retrieval is biologically competitive with BLAST.

On this CPU host, k-mer candidate generation averaged `91.7 ms/query`. Batched
BLAST against the full local Swiss-Prot database averaged `3.48 s/query`
including database search. These timings are implementation checks, not the
paper's final latency comparison; warm-cache and GPU vector timings remain to be
measured under a controlled protocol.

The Chroma POC contains all `1,185` exported documents. Its CPU hashing vectors
are explicitly a persistence/search smoke test; scientific sequence-to-paper
comparisons will use mean-pooled ProtT5, ESM-2, and OmniGene embeddings after the
GPU is opened.

## GPU Embedding Results

The three mean-pooled protein encoders were evaluated on a 96 GB RTX PRO 6000
using 1,275 overlapping protein windows (`128 aa`, stride `64`) with parent
collapse. ProtT5 reached protein Hit@1/MRR and paper Recall@50 of
`1.000/1.000/1.000`; ESM-2 reached `0.960/0.977/1.000`; OmniGene BF16 reached
`0.900/0.914/0.947`. End-to-end embedding plus NumPy lookup averaged `2.88 ms`,
`2.67 ms`, and `52.28 ms` per query, respectively.

These remain in-index path experiments because the queries are windows from
indexed parents. They establish the model integration and support a
modality-aware architecture, but they are not held-out homology evidence.
ProtT5 or ESM-2 should therefore be the default protein partition encoder;
OmniGene remains the unified sequence/text backbone for mixed agent contexts.

## Held-Out Function-to-Paper Pilot

The CPU pipeline was expanded to 2,000 proteins, 12,858 curated GOA
annotations, 4,304 PMIDs, and 63,651 graph edges. A deterministic held-out split
contains 99 query proteins and 1,901 index proteins with zero exact-accession or
full-sequence substring overlap. Labels use 132 GO terms with corpus frequency
2--10 and 377 index-side GOA-supported PMIDs; retrieval model outputs never
define relevance.

At protein top-10 / paper top-50, BLAST obtains candidate MRR `0.186` and paper
Recall `0.130`, versus k-mer Jaccard `0.110/0.087` and random `0/0`. At protein
top-50 / paper top-200, k-mer paper Hit rises to `0.313` (`95% CI 0.222--0.404`)
while random reaches `0.071`, whereas BLAST retains stronger candidate MRR.
This pilot supports complementary precise verification and broad candidate
discovery, but it is not yet a family-cluster-held-out benchmark.

### Held-Out GPU Encoders

ProtT5 and ESM-2 were then evaluated on the fixed 99-query split using 14,633
overlapping protein windows. At protein top-50 / paper top-200, ProtT5 obtains
candidate MRR `0.217`, paper Hit `0.465`, and paper Recall `0.248`; ESM-2 obtains
`0.172/0.364/0.203`; BLAST obtains `0.186/0.242/0.135`; and k-mer Jaccard obtains
`0.116/0.313/0.147`.

Paired bootstrap shows that ProtT5 improves paper Hit over BLAST by `0.222`
(`95% CI 0.141--0.303`) and paper Recall by `0.113` (`0.066--0.165`). The
candidate-MRR difference is `0.031` (`-0.008--0.075`) and therefore does not
support claiming significantly better candidate ranking. ProtT5 broadens
function-linked literature coverage while BLAST remains the alignment-grounded
verification route.

Simple ProtT5+BLAST reciprocal-rank fusion is a negative ablation: it reduces
paper Hit from `0.465` to `0.303`. Future combination should rerank the ProtT5
candidate pool with BLAST while retaining unaligned vector candidates, rather
than globally fusing independent ranks.
