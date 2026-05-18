# Roadmap

## MVP0: Initialized Scaffold

- Python package and CLI
- Standard KB config
- FTS wrapper
- graph builder
- vector-index scaffold
- hybrid evidence output
- smoke tests

## MVP1: Local Classical Baseline

- expand Standard SQLite index with NCBI Gene, ClinVar variants, PubMed sample, and UniProt text
- expose local gene, protein, pathway, variant, literature, and sequence search tools
- add benchmark JSONL tasks and scoring scripts

## MVP2: OmniGene Vector RAG

- build typed text, entity, and sequence embedding corpora
- generate OmniGene-4-CPT-v2-merged BF16 embeddings for the main paper runs
- keep 4-bit and GGUF builds as low-memory engineering baselines
- use Chroma as the RAG POC vector database with complete record CRUD
- compare mean pooling and EOS pooling
- add vector retrieval to hybrid search with evidence calibration

## MVP3: DRAG Graph

- package hybrid retrieval as a DRAG answer scaffold with citations and graph paths
- build DNA, protein, and mixed English/sequence graph views with a text-style evidence graph recipe first
- test whether biologically meaningful clusters and paths emerge before adding domain-specific graph rules
- scale pure vector-neighbor sequence view graphs from readable 1k figures to
  10k community analyses, keeping input window counts separate from collapsed
  biological entity nodes
- add same-node BLAST-neighbor graph ablations to show how alignment-derived
  local neighborhoods complement broader vector-neighbor DRAG structure
- build hybrid vector+BLAST DRAG graphs that preserve both edge types for
  agent retrieval and evidence attribution
- evaluate graph-context traces for vector-only, BLAST-only, and hybrid DRAG so
  agent evidence packs can distinguish representation similarity from alignment
  support
- add Reactome protein/gene pathway edges
- add NCBI gene2go and gene2pubmed edges
- add UniProt protein sequence nodes
- add BLAST-derived sequence similarity edges
- export graph paths in agent traces

## MVP4: Open-Rosalind Integration

- package `local.hybrid_bio_search` as an Open-Rosalind skill
- route sequence, gene, variant, pathway, and literature questions through local-first retrieval
- preserve public API fallback for long-tail misses
- add an instant/verified/deep retrieval policy for agent UX:
  vector-only instant context first, BLAST/hybrid DRAG verification second, and
  deeper pathway/domain/literature tools for long-running analysis

## MVP5: Paper Experiments

- run retrieval ablations
- run multi-hop agent benchmark
- compare single-tool baselines against route-gated Hybrid BioRAG without
  claiming that vector search replaces BLAST
- evaluate whether text-style DRAG graphs over sequence embeddings recover
  biologically meaningful neighborhoods before adding biological-rule edges
- extend the first vector-neighborhood enrichment result to GO/pathway/family
  enrichment and graph community analysis
- add a latency/throughput ablation that separates model load, query embedding,
  vector-index lookup, BLAST, graph expansion, and end-to-end agent context
  construction
- report instant vector-only latency separately from verified vector+BLAST+graph
  latency, making clear that the instant mode gives provisional multimodal
  context while verified mode supplies biological evidence attribution
- test FAISS GPU as the performance-oriented vector backend after the Chroma POC
- write Hybrid BioRAG paper around classical vs vector vs graph vs hybrid results
