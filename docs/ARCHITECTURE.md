# Architecture

`dnarag` follows the MVP5 design in `init.md`: one logical Local Bio-KB, multiple retrieval views.

## Upstream Ideas

Open-Rosalind contributes the agent contract:

- factual claims should come from tools, not model memory
- every answer should expose evidence and a replayable trace
- workflows should be bounded and auditable

OmniGene-4 contributes the representation layer:

- CPT is treated as the preferred sequence/text embedding checkpoint
- the main configured full merged CPT model is Gemma-4 based and includes biological sequence vocabulary for DNA, protein, 3Di, and DSSP tokens
- SFT or chat models remain responsible for routing, synthesis, and final answers
- typed prompts are used so the model sees whether an item is a paper, protein, pathway, or sequence

## Runtime Flow

```text
User query
  -> query classifier
  -> Local Bio-KB router
  -> FTS / SQL
  -> BLAST sequence search
  -> OmniGene vector search
  -> DRAG graph expansion
  -> evidence merge
  -> Open-Rosalind-style trace + summary context
```

The package currently implements the retrieval and evidence layer. It does not replace the upstream Open-Rosalind agent; it gives that agent a local-first `hybrid_bio_search` tool surface.

## Retrieval Policy

The agent-facing system should expose three operating modes:

- **Instant:** vector-only retrieval over the unified multimodal index. This
  mode gives a fast provisional answer context for DNA sequences, protein
  sequences, and mixed English biomedical text after a resident embedding model
  produces the query vector.
- **Verified:** vector retrieval plus BLAST and hybrid DRAG graph expansion.
  This mode is used when the answer needs biological grounding and evidence
  attribution.
- **Deep:** verified retrieval plus slower domain, pathway, literature, and
  future structure/image tools. This is the paper-analysis and multi-step agent
  mode.

This is a complementary architecture, not a replacement claim. Vector search is
the unified candidate layer; BLAST and biological graph edges are the
verification layer.

For sequence queries, the preferred route is vector-coarse retrieval followed by
BLAST fine reranking or verification:

```text
OmniGene vector search
  -> instant context and top-N candidate IDs
  -> BLAST fine reranking / verification
  -> hybrid DRAG context pack
```

This keeps BLAST inside the RAG pipeline instead of treating it only as an
external baseline. It also fits large-model agents: the agent receives a fast
initial context, then a verified evidence update with explicit route labels.

## Logical Schema

The canonical KB schema lives in `dnarag/localdb/schema.sql` and uses these core tables:

- `entities`: genes, proteins, sequences, papers, pathways, GO terms, variants, diseases, organisms
- `aliases`: symbols, names, accessions, and cross references
- `text_chunks`: paper abstracts, UniProt functions, pathway descriptions, GO definitions
- `sequences`: protein, DNA, RNA, peptide, cDNA, 3Di, and DSSP records
- `relations`: graph edges with evidence and metadata
- `retrieval_evidence`: normalized retrieval hits from FTS, BLAST, vector, and graph routes

## Retrieval Views

FTS / SQL:
Uses the existing Open-Rosalind Standard SQLite index when present.

BLAST:
Uses the Swiss-Prot BLAST database under the Standard KB index directory.

Vector:
Uses a pluggable embedding backend. OmniGene-4 CPT is available for unified biological sequence/text and agent-facing contexts, while public encoder backends such as ESM-2 and ProtT5 can be used for protein-only partitions. The transformer embedders take the last hidden layer and apply attention-mask mean pooling over token hidden states, followed by L2 normalization; they do not use next-token logits. A `last`/`eos` pooling option uses the last valid token hidden state and should be treated as a pooling ablation. A deterministic hashing backend exists only for development smoke tests.
Vector inputs are typed before tokenization, for example `[TYPE=protein_sequence]`, `[TYPE=paper]`, `[TYPE=protein]`, and `[TYPE=pathway]`. This is intentional: the OmniGene CPT tokenizer has biological sequence tokens, and the type prefix keeps sequence/text/entity records comparable without hiding what modality each item came from.
For the RAG POC, vectors are imported into a local persistent Chroma store under `indexes/standard/vector/chroma/`.
The Chroma adapter supports record-level add, upsert, update, delete, get, and query operations.
The older SQLite/NumPy vector store remains as a simple fallback, and FAISS can be added later for local performance.

DRAG graph:
Builds a graph from Standard index documents and structured xrefs. First-pass graph nodes include HGNC genes, GO terms, Reactome pathways, ClinVar summaries, UniProt xrefs, NCBI Gene xrefs, and Ensembl xrefs. Generated graph artifacts are repo-local by default under `indexes/standard/graph`.

Multi-view DRAG:
The first experiment should build DNA, protein, and mixed English/sequence views with the same text-style evidence graph recipe used for ordinary RAG: typed records, nearest-neighbor evidence, aliases, co-retrieved entities, and graph expansion. Biological rules such as BLAST-derived homology, motif calling, or domain databases can be added later as explicit ablations. Keeping the first graph mostly method-agnostic lets the paper ask a cleaner question: whether biological meaning emerges from a unified representation and evidence graph rather than from hand-coded biology.

`python -m dnarag.cli build-view-graph` implements the first POC of that idea. It samples a Chroma collection, turns records into graph nodes, and adds `vector_neighbor` edges from cosine nearest neighbors. The graph metadata marks the recipe as `text_style_vector_neighbors` and `biological_rules_used=false` so later rule-enriched graphs can be compared cleanly.

In the paper framing, these views are not just search accelerators. A sequence-derived graph can become a biological representation layer: DNA records connect to transcripts, proteins, variants, and annotations; protein records connect to function, pathway, and literature evidence; mixed English records connect claims and entity descriptions back into the same local Bio-KB. The system can therefore compare text-only RAG, sequence-vector RAG, single-view DRAG, and unified multi-view DRAG on both retrieval quality and traceable biological paths.

## Output Contract

The core search API returns:

- `answer_context`: compact context blocks for a downstream agent or model
- `evidence`: source-bound retrieval hits
- `retrieval_trace`: route, input, output count, and status for each retrieval step
- `local_coverage`: estimated local evidence coverage
- `fallback_used`: whether public APIs were needed

This keeps the project aligned with Open-Rosalind's trace-first design.

`python -m dnarag.cli answer` adds an answer-facing DRAG package on top of the same retrieval contract:

- `answer`: extractive local scaffold, suitable for inspection when no generator is running
- `citations`: compact evidence blocks with stable IDs such as `E1`
- `graph_paths`: relation paths surfaced from graph expansion
- `modality_views`: counts and routing information for text, DNA/protein sequence, and graph evidence
- `generation_prompt`: a prompt-ready evidence pack for a local Gemma/Open-Rosalind answer model
