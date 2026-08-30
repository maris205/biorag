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
- add a sequence-conditioned literature evidence DAG that links protein
  sequences to curated UniProt annotations, GO/domain/family/pathway nodes, and
  PubMed papers; keep the full biological graph heterogeneous while exposing a
  DAG-shaped evidence view for agent retrieval
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
- publish a versioned BioRAG-SeqLit-DAG sample/full dataset on Hugging Face with
  schema, manifest, graph tables, Chroma-ready documents, and rebuild scripts

## MVP4: Open-Rosalind Integration

- package `local.hybrid_bio_search` as an Open-Rosalind skill
- route sequence, gene, variant, pathway, and literature questions through local-first retrieval
- preserve public API fallback for long-tail misses
- add an instant/verified/deep retrieval policy for agent UX:
  vector-only instant context first, BLAST/hybrid DRAG verification second, and
  deeper pathway/domain/literature tools for long-running analysis

## MVP5: Paper Experiments

- [completed] run the controlled DNA embedding matrix in
  `docs/DNA_EMBEDDING_EVALUATION_PLAN.md`, including DNABERT-S, DNABERT-2,
  Nucleotide Transformer v2, OmniGene, mean/last/CLS pooling, and
  reverse-complement averaging before scaling beyond controlled20k; DNABERT-2
  mean with 256/128 windows is the selected DNA dense candidate encoder
- [completed pilot] implement and train a DNA-ESM2-style encoder on the local
  DNA corpus, including MLM, reverse-complement augmentation, and gene-aware
  contrastive fine-tuning; the first pilots remain below DNABERT-2 and are
  retained as feasibility ablations
- [completed second pilot] train a 117M DNA encoder with 1M DNA records and
  10k MLM steps; mean pooling is best among mean/last/CLS but remains below
  DNABERT-2 on the fixed 20k control
- [completed] select the protein partition encoder from matched held-out
  controls: ProtT5-XL-UniRef50 mean pooling is the default dense encoder, ESM-2
  650M mean is the lightweight alternative, and OmniGene mean remains the
  unified mixed-modality backbone
- [completed for v1] close the DNA embedding improvement pass: DNABERT-2 mean
  with 256/128 windows is retained as the primary DNA candidate encoder, while
  DNABERT-S, Nucleotide Transformer, quantized OmniGene, and the 117M
  DNA-ESM2-style MLM model are recorded as comparison/negative ablations;
  further domain-adaptive or hard-negative training is deferred until after
  first-round review
- [completed for v1] run retrieval ablations, including matched top-50 protein
  candidates and top-20 literature evidence packs
- [completed for v1] run the held-out sequence-to-literature Agent benchmark:
  deterministic 33/66 selector split, accession-masked prompts, structured
  GO/PMID correctness, typed citation entailment, and mechanism abstention
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
- [completed for controlled20k DNA lookup] test FAISS GPU as the
  performance-oriented vector backend after the Chroma POC; the resident
  `IndexFlatIP` microbenchmark is retained as lookup-only evidence, with
  end-to-end embedding, BLAST, concurrency, and larger-scale serving still
  pending
- write Hybrid BioRAG paper around classical vs vector vs graph vs hybrid results
- [next] publish the compact SeqLit-DAG split/results and prepare the first
  submission/review package; defer learned paper selection, free-form expert
  evaluation, new model training, and larger graph scale until first-round
  feedback
- extend the completed protein encoder comparison to a full Swiss-Prot dense
  scale curve before making full-corpus model claims
