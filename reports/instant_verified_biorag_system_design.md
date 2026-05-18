# Instant and Verified BioRAG Engineering Design

Date: 2026-05-15

Purpose: define the engineering application value of BioRAG/DRAG beyond
retrieval accuracy. The central design is a layered retrieval service: use
vector RAG for immediate multimodal context, then add BLAST and graph evidence
for verification and deeper biological grounding.

## System Modes

| Mode | Retrieval routes | User-facing behavior | Best use |
| --- | --- | --- | --- |
| Instant | vector only | Return a fast provisional reference answer from a unified multimodal index. | Interactive chat, exploratory sequence/text lookup, agent first-pass planning. |
| Verified | vector + BLAST + hybrid DRAG graph | Update or annotate the answer with alignment-supported and graph-supported evidence. | Biological claims, sequence similarity justification, citation-heavy answers. |
| Deep | vector + BLAST + graph + domain/pathway/literature tools | Run a multi-step agent workflow with typed evidence paths and cross-modal expansion. | Paper-level analysis, mechanistic hypotheses, pathway/GO/domain interpretation. |

This framing does not claim that vector search replaces BLAST. BLAST remains
the biologically grounded alignment baseline. The BioRAG contribution is that
sequence, text, graph, and later structure/image evidence can share one
agent-facing retrieval layer.

## Latency Decomposition

Command:

```bash
python scripts/benchmark_instant_verified_latency.py \
  --config configs/standard.yaml \
  --output reports/instant_verified_latency_benchmark.json
```

Scope:

- measured Chroma lookup, local BLAST, and SQLite graph expansion
- excluded model cold start, query embedding generation, LLM generation, and
  network calls
- vector lookup used sampled existing Chroma embeddings as query vectors, which
  approximates online lookup after a resident GPU embedding service has already
  produced the query vector

## Current Result

Standard text and 100k BF16 OmniGene sequence-window Chroma collections:

| Component | Text / Standard | DNA/cDNA | Protein | Notes |
| --- | ---: | ---: | ---: | --- |
| Chroma vector lookup, top-10 | 4.6924 ms | 5.9630 ms | 6.0948 ms | 50 sampled query embeddings per modality |
| BLAST top-10 | n/a | 294.5684 ms | 1081.9300 ms | 20 benchmark queries per modality |
| Hybrid graph expansion | n/a | 0.3540 ms | 0.3254 ms | 100 seed nodes, limit 12 edges |
| Instant profile | 4.6924 ms | 5.9630 ms | 6.0948 ms | vector only, after embedding |
| Verified profile | n/a | 300.8221 ms | 1088.8706 ms | vector + BLAST + graph median sum |

Full output: `reports/instant_verified_latency_benchmark.json`.
Text/vector-only output: `reports/chroma_lookup_text_sequence_100k_benchmark.json`.

## Application Claim

The practical application value is a progressive answer pipeline:

1. **Instant response:** use the unified vector index to produce immediate
   reference context for DNA sequences, protein sequences, and mixed English
   biomedical text. This is useful in chat and agent systems because the user
   can receive a first answer while heavier tools run.
2. **Verified update:** run BLAST and hybrid DRAG graph expansion to attach
   biologically grounded evidence. In the current benchmark, BLAST dominates
   verified-mode latency, while graph expansion is sub-millisecond to
   low-millisecond.
3. **Deep analysis:** add pathway, GO, domain, literature, and later
   structure/image routes. The same evidence contract can expose which claims
   came from representation similarity, alignment evidence, graph relations, or
   curated biological annotations.

This gives the paper an engineering thesis that is realistic: vector RAG is the
fast unified candidate layer, BLAST is the precise biological verification
layer, and DRAG turns both into typed evidence paths for agent use.

## Vector Coarse Retrieval + BLAST Rerank

The main engineering route should be a two-stage sequence retrieval strategy:
vector retrieval does coarse candidate selection, then BLAST performs fine
reranking and verification.

```text
sequence / text / mixed query
  -> OmniGene vector retrieval over the unified BioRAG index
  -> top-N candidate sequence/entity set + instant answer context
  -> BLAST fine scoring on candidate set, or BLAST fallback on the full local DB
  -> verified reranking with alignment evidence
  -> DRAG evidence graph for agent citations and follow-up reasoning
```

This makes the relationship with BLAST cooperative:

- vector search supplies fast cross-modal coarse candidates and an immediate
  answer context
- BLAST reranks or verifies those candidates with interpretable alignment
  evidence, falling back to full-database BLAST when needed
- hybrid DRAG keeps both evidence types so an agent can cite whether a claim is
  based on representation similarity, alignment support, or graph context

For user-facing systems, this enables a streaming interaction pattern: return an
instant reference answer first, then attach BLAST/DRAG verification when it
finishes. For paper evaluation, this motivates comparing the full pipeline
against BLAST-only and vector-only ablations without claiming that either route
subsumes the other.

## Why This Matters For Multimodal BioRAG

Classical sequence tools are excellent at their own objective, but they are not
designed as a unified context interface for LLM agents. BioRAG is valuable
because it can index and retrieve across:

- DNA/cDNA sequence windows
- protein sequence windows
- literature and annotation text
- graph relations
- future structure tokens, images, and other modalities

The instant mode is therefore not merely a faster BLAST substitute. It is a
general multimodal retrieval layer that can provide useful candidate context
before the system asks slower specialized tools for confirmation.

## Paper Framing

Recommended wording:

- "Vector-only instant mode provides fast provisional multimodal BioRAG context."
- "The primary sequence route is vector coarse retrieval followed by BLAST
  reranking or verification."
- "BLAST and hybrid DRAG provide biologically grounded verification and evidence
  attribution."
- "The system is complementary to BLAST: vector retrieval supplies a unified
  candidate layer, while BLAST supplies alignment-based support."
- "Hybrid DRAG preserves vector connectivity while injecting alignment-supported
  local evidence."

Avoid wording that says vector search replaces BLAST or that vector similarity
has the same statistical interpretation as alignment e-values.

## Next Engineering Experiments

- Measure warm query embedding latency with the BF16 OmniGene model kept
  resident on a 96 GB GPU.
- Use FAISS CPU lookup as the current local baseline: 100k sequence-window
  vectors, 5k queries, top-10 search gives about 15.5 ms/query for both DNA/cDNA
  and protein windows; Standard text gives about 8.3 ms/query for 57,856
  vectors and 2k queries.
- Re-run FAISS GPU lookup with a Blackwell-compatible FAISS build/container.
  The current `faiss-gpu-cu12` wheel imports and detects the RTX PRO 6000, but
  aborts with CUDA error 209 because the wheel lacks the needed `sm_120` kernel
  image.
- Add streaming answer behavior: emit instant citations first, then append
  verified BLAST/DRAG citations when ready.
- Scale latency tests from 100k windows to larger sequence/text collections and
  report throughput under concurrent queries.
