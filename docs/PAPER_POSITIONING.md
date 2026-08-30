# Paper Positioning

## Core Claim

This project is a biological multimodal RAG system, not a BLAST replacement.

The central contribution is a unified local Bio-KB interface that can index and
retrieve literature text, DNA/cDNA sequences, protein sequences, mixed
English-sequence records, and later structure/image evidence through a shared
RAG/DRAG evidence layer. Classical biological search remains part of the system:
BLAST, SQL/FTS, and curated graph edges provide high-precision evidence where
their assumptions fit the query.

The strongest new direction is sequence-conditioned literature discovery. Plain
literature RAG and paper citation DAGs are already common; BioRAG-DRAG should
instead show that a protein sequence can be the entry point into literature
evidence. Sequence candidates connect to curated UniProt annotations,
GO/domain/family/pathway nodes, and PubMed references through an auditable
evidence-DAG view. This turns the graph from a generic paper DAG into a
biological sequence-to-literature resource that can be released and updated
publicly.

The current held-out application result makes this claim executable rather than
conceptual. A 2k Swiss-Prot/GOA/PubMed DAG yields 99 leakage-controlled queries;
Graph-IDF is tuned on 33 and frozen on 66, after which a local instruction model
produces citation-bounded GO/PMID answers. The main positive result is reliable
evidence execution and abstention, while the main negative result is that
retrieval and compact paper selection still limit answer recall. This should be
presented as a structured Agent evidence benchmark, not as free-form biological
reasoning or mechanism discovery.

The motivation is engineering-first: local biomedical agents need one evidence
interface that can retrieve across tools and modalities. The scientific question
comes after that engineering choice: once biological sequences, text, and later
structure/image evidence are placed into a shared RAG/DRAG substrate, do the
retrieved neighborhoods and graph paths expose biological structure that was not
explicitly encoded by hand?

## Why BLAST Is Not the Target to Replace

BLAST has explicit biological and statistical foundations: alignment scoring,
substitution matrices, gap penalties, and significance estimates. It should be
the primary baseline for exact sequence similarity and local alignment tasks.
The paper should treat BLAST as a strong biological tool, not as an outdated
component to remove.

The sequence-vector layer has a different role:

- provide a common representation space for sequence and text evidence
- retrieve representation-level neighborhoods that are useful for RAG context
- support mixed natural-language and biological-sequence queries
- seed DRAG graphs that can connect sequences to annotations, papers, entities,
  and later structures or images
- retrieve papers from raw protein sequences through curated
  sequence-to-annotation-to-literature evidence paths
- expose biological neighborhoods for agent workflows where exact alignment is
  only one part of the reasoning chain

For sequence-only exact-fragment tasks, matching BLAST within a reasonable gap is
enough to show the representation is usable. The stronger claim should come from
unified retrieval, cross-modal evidence assembly, and graph/agent improvements.

Existing held-out protein fragment results support a model-agnostic sequence
entry layer rather than an OmniGene-only claim: ProtT5 mean pooling reaches
protein biological Hit@10/MRR `0.7780/0.7158`, ESM-2 mean reaches
`0.6560/0.5764`, and OmniGene mean reaches `0.3120/0.2623`. This makes
specialized protein embeddings natural defaults for protein sequence partitions,
while OmniGene remains valuable as a unified biological-language backbone for
mixed sequence/text agent contexts.

## Engineering Performance Claim

It is reasonable to claim that RAG/DRAG has engineering advantages for agent
systems, especially when vectors are precomputed and approximate nearest-neighbor
search is batched or GPU-accelerated. The strongest version of this claim is not
that a Chroma POC is already faster than BLAST. The stronger and safer claim is:

- BLAST remains efficient and biologically grounded for exact sequence search.
- Vector RAG can reuse one retrieval substrate across text, DNA, protein, mixed
  sequence-language records, and later structure/image evidence.
- ANN indexes such as FAISS GPU can make large-scale vector search highly
  parallel and friendly to batched agent workloads.
- Milvus GPU can be used later as the production-scale vector service for very
  large indexes and high concurrency, while Chroma remains the POC database and
  FAISS remains the easiest local speed benchmark.
- DRAG can improve system-level utility by expanding from a retrieved sequence
  neighborhood to annotations, papers, entities, and graph paths.

Therefore latency should be evaluated in stages: cold model load, query
embedding, vector-index lookup, graph expansion, merge/rerank, and end-to-end
agent context construction. The current Chroma experiment supports representation
quality; a later FAISS GPU experiment should test the speed claim directly.

## Paper-Level Comparisons

The evaluation should separate single-tool quality from unified-system utility.

Single-view retrieval:

- SQL/FTS for entity, pathway, variant, and literature lookup
- BLAST/DIAMOND/MMseqs2 for exact or homologous sequence search
- OmniGene vector search for sequence/text representation neighborhoods
- DRAG graph expansion for multi-hop evidence paths

Unified BioRAG:

- route-gated hybrid retrieval using SQL/FTS, BLAST, vectors, and graph evidence
- modality-aware evidence merging across text, DNA, protein, and mixed records
- answer-context construction for local biomedical agents
- later extension to structure and image retrieval without changing the user
  interface

## DRAG Research Question

The first DRAG graph should deliberately follow the ordinary text-RAG recipe:
records become nodes, nearest-neighbor retrieval creates edges, and graph
expansion surfaces context. Biological rules such as BLAST homology, motif
calling, domains, curated pathways, and structure similarity should be added
later as ablations.

This gives the paper a cleaner question:

Can a text-style graph built from biological-sequence representations recover
biologically meaningful neighborhoods before explicit biological rules are
added?

This turns RAG from only an engineering module into an experimental probe. The
system starts with a practical agent need, then uses ablation and enrichment
analysis to ask whether unified retrieval produces interpretable biology:
families, functional clusters, pathway neighborhoods, sequence-to-literature
paths, and cross-view DNA/protein/text alignment.

Useful measurements include GO/Reactome/family enrichment, sequence-to-annotation
path completeness, cross-view alignment between DNA/protein/text nodes, and
agent answer grounding with and without each view.

## Claims To Avoid

- Vector search replaces BLAST.
- A small smoke benchmark is SOTA.
- Better exact sequence rank alone proves biological reasoning.
- Graph edges are biologically meaningful before enrichment or path analysis is
  measured.

## Claims To Test

- Sequence-window OmniGene vectors can approach BLAST on basic sequence retrieval
  while providing a modality-compatible RAG representation.
- Hybrid BioRAG keeps classical precision and adds cross-modal recall.
- Text-style DRAG over sequence embeddings forms non-random biological
  neighborhoods.
- Sequence-conditioned evidence DAGs can retrieve curated literature from raw
  protein sequences through protein, annotation, and paper paths.
- Multi-view DRAG improves agent evidence grounding and multi-hop biological
  reasoning compared with single-view RAG.
- GPU-backed ANN search improves batched retrieval throughput for agent
  workloads after embeddings are precomputed.

## Current Evidence

The BF16 10k sequence-window baseline supports the engineering premise: BLAST
and OmniGene vector retrieval both reach Hit@10 `1.0000`, while BLAST remains
better on rank quality.

The BF16 100k sequence-window run is more realistic. BLAST reaches Hit@10
`1.0000` and MRR `0.8750`; vector-only reaches Hit@10 `0.7500` and MRR
`0.7500`; route-gated Hybrid BioRAG recovers BLAST-level Hit@10 `1.0000` and
MRR `0.8750` while retaining vector neighborhoods for RAG/DRAG context.

A larger generated 100-query strict-ID benchmark gives a more nuanced picture.
Across two random seeds, BLAST reaches strict Hit@10 `0.7550`, vector-only
reaches strict Hit@10 `0.5350`, and route-gated Hybrid BioRAG reaches strict
Hit@10 `0.7550`. Protein and DNA behave very differently, and vector retrieval
is much stronger for full-window/prefix queries than for suffix or short
internal fragments. This supports a cautious claim: the current sequence-vector
view is promising but not yet a SOTA exact sequence-search method by itself.

The biological-equivalence view is stronger and more relevant for the paper
claim. On the `_bio` benchmark variants, BLAST reaches bio Hit@10 `0.9898`,
vector-only reaches bio Hit@10 `0.7751`, and route-gated Hybrid BioRAG reaches
bio Hit@10 `0.9898`. A lightweight sequence-aware reranker improves the vector
layer to strict Hit@10 `0.6950` and bio Hit@10 `0.8822` without changing the
embedding model.

Split by modality, the reranked vector layer reaches DNA/cDNA bio Hit@10
`0.9500` and protein bio Hit@10 `0.8102`. This is exactly the kind of result the
paper should frame carefully: vector search is not replacing BLAST, but it is
recovering biologically meaningful neighborhoods often enough to justify a
unified BioRAG/DRAG substrate.

The combined number should be treated as a smoke summary only. Paper tables
should separate protein and DNA/cDNA, and distinguish strict parent-ID recovery
from biological-equivalence recovery. The biological claims now include explicit
community, GO/Reactome, and DRAG path analysis; domain and literature enrichment
remain future work.

The first DRAG-facing enrichment check is now positive. A pure vector-neighbor
recipe was evaluated before adding BLAST/domain/pathway rules, with same-parent
windows excluded and parent records deduplicated. On 100 anchors per target,
protein sequence windows recover same `GN=` labels at vector Hit@10 `0.4300`
versus random `0.0200`; DNA/cDNA windows recover same gene ID at vector Hit@10
`0.6900` versus random `0.0600`, and same gene symbol at vector Hit@10 `0.7188`
versus random `0.0625`. This does not prove biological mechanism, but it is a
strong first signal that the method-agnostic vector graph contains biological
structure.

The first graph visualization supports the same direction. A 1k DNA/cDNA
text-style vector-neighbor DRAG graph forms three communities with modularity
`0.3052`; the dominant community labels separate `IGLV` and `IGHV`
neighborhoods without BLAST or curated biological-rule edges. A 1k protein graph
forms seven communities with modularity `0.3621`, including a `YWHAB`-enriched
community. These are figure candidates for the paper, provided they are framed
as label-enriched graph modules rather than mechanistic biological proof.

This validates the paper framing: vector search is a useful sequence view in a
unified BioRAG substrate, but exact sequence evidence should still be routed
through BLAST. The next claims should be tested on mixed text/sequence
retrieval, route-gated Hybrid BioRAG, DRAG graph enrichment, FAISS/Milvus speed
experiments, and agent evidence grounding.
