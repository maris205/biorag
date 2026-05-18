# BioRAG-DRAG: A Multimodal Biological Retrieval Layer for Local-First Biomedical Agents

## Abstract

Biomedical agents need reliable access to heterogeneous evidence: literature text, gene and pathway records, protein sequences, DNA/cDNA sequences, and structured biological relations. Classical sequence tools such as BLAST remain the right choice for alignment-grounded verification, but they are not a unified context interface for large language model agents. We present **BioRAG-DRAG**, a local-first multimodal retrieval layer that combines neural sequence-text retrieval, BLAST verification, and graph-based evidence packaging. OmniGene CPT embeddings provide a fast coarse retrieval layer over text and biological sequences; BLAST reranks or verifies sequence candidates; and DRAG graphs expose typed, traceable paths for downstream agents.

We introduce **BioRAG-Standard v0**, a partitioned benchmark/library with 257,886 retrievable records and 112 annotated tasks built from Open-Rosalind Standard biomedical records and sequence-window extensions. On a 100-query sequence subset, BLAST reaches biological Hit@10/MRR of 0.9899/0.9768. Vector retrieval alone reaches 0.8182/0.7088, while a lightweight sequence-aware reranker improves the vector route to 0.9293/0.9217. Vector-to-candidate-BLAST reranking reaches 0.9293/0.9293 with 200 vector candidates, showing that neural retrieval can provide useful candidate pools for alignment-labeled evidence. Indexed Chroma lookup over Standard text and 100k sequence-window collections takes 4.7-6.1 ms after query embedding, supporting an instant-response mode; BLAST and DRAG form a verified evidence mode. Finally, sequence DRAG graphs show enriched biological communities, including immunoglobulin-family modules, gene-symbol modules, GO/Reactome enrichment, and shared PubMed evidence. These results support a complementary architecture: vector retrieval supplies fast unified candidate context, while BLAST and DRAG provide biological verification and evidence attribution.

## 1. Introduction

Biomedical information retrieval is inherently multimodal. A single user question may involve a gene symbol, a DNA fragment, a protein sequence, a pathway description, a variant, a paper abstract, or a combination of these. Traditional bioinformatics systems expose these modalities through separate tools: BLAST for local alignment (Altschul et al., 1990), MMseqs2 or DIAMOND for high-throughput sequence search (Steinegger and Soeding, 2017; Buchfink et al., 2021), SQL or keyword search for database records, ontology lookup for GO terms, pathway databases for molecular processes, and graph traversal for relationships among entities. This division is scientifically useful, but it creates a practical gap for large language model (LLM) agents. Agents need a unified evidence interface that can retrieve, cite, and reason over heterogeneous local data without forcing the user or the model to manually choose a tool for each modality.

Retrieval-augmented generation (RAG) offers a natural interface for evidence grounding (Lewis et al., 2020), but ordinary text RAG is not sufficient for biological data. DNA and protein sequences are not just strings of natural language, and exact sequence similarity has established statistical and biological foundations. Therefore, a biological RAG system should not frame neural vector retrieval as a replacement for BLAST. Instead, vector retrieval should act as a fast, shared candidate layer, while classical tools provide verification where their assumptions fit the query.

We propose **BioRAG-DRAG**, a multimodal biological retrieval layer for local-first biomedical agents. The core design is:

```text
query / sequence / mixed input
  -> OmniGene vector retrieval for coarse candidates and instant context
  -> BLAST verification or reranking for sequence-level evidence
  -> DRAG graph expansion for typed evidence paths
  -> local-first agent answer with citations and retrieval traces
```

This design separates three roles. First, vector retrieval provides a unified representation layer over text, DNA/cDNA, protein, and mixed records. Second, BLAST remains the biological alignment route for verification and reranking. Third, DRAG turns retrieval results into graph evidence that an agent can inspect, cite, and expand. The system is therefore complementary to BLAST rather than competitive with it.

The strongest empirical result supports this division. On BioRAG-Standard v0, vector retrieval is not as strong as full-database BLAST for alignment-grounded sequence verification, but it recovers enough biologically equivalent candidates to make a practical two-stage route: vector coarse retrieval followed by BLAST reranking reaches biological Hit@10/MRR of 0.9293/0.9293 at a 200-candidate budget, while hybrid gated retrieval preserves BLAST-level biological recall and exposes graph evidence for agent use.

![Figure 1. BioRAG-DRAG architecture. Vector retrieval provides an instant multimodal candidate layer; BLAST supplies sequence verification and reranking; DRAG packages vector, alignment, text, and graph evidence into typed traces for a local biomedical agent.](figures/fig1_architecture.pdf)

This paper makes four contributions:

1. **A multimodal BioRAG dataset/library.** We build BioRAG-Standard v0 from Open-Rosalind Standard data and sequence-window extensions, yielding 257,886 corpus records and 112 annotated tasks with local positive evidence references.
2. **A local-first hybrid retrieval architecture.** We implement vector coarse retrieval, BLAST verification, and DRAG graph packaging over Standard biomedical text, protein windows, DNA/cDNA windows, and mixed records.
3. **A retrieval and engineering evaluation.** We compare BLAST, vector retrieval, vector reranking, and hybrid retrieval; we also decompose instant and verified-mode latency.
4. **A biological-structure analysis.** We analyze vector-only, BLAST-only, and hybrid sequence graphs, showing enriched community, functional, and literature-evidence structure that suggests sequence-vector graphs can serve as more than a search cache.

## 2. Related Work

**Classical sequence search.** BLAST remains a central tool for sequence similarity because it provides alignment-based scoring and interpretable statistical evidence (Altschul et al., 1990). Later systems such as MMseqs2 and DIAMOND improve speed and sensitivity at large scale, especially for protein and metagenomic workloads (Steinegger and Soeding, 2017; Buchfink et al., 2021). This line of work is not a weak baseline for BioRAG; it is the biological verification layer that BioRAG should preserve. Our question is different: whether a neural multimodal retriever can provide a fast, shared candidate and context layer that cooperates with alignment search rather than replacing it.

**Biomedical language models and biomedical RAG.** Domain-specific biomedical language models such as BioBERT, PubMedBERT, BioGPT, and BioMedLM improve biomedical text representation or generation by pretraining on biomedical corpora (Lee et al., 2020; Gu et al., 2022; Luo et al., 2022; Bolton et al., 2024). RAG systems then combine model generation with retrieved evidence to reduce reliance on parametric memory (Lewis et al., 2020). Clinical and biomedical RAG systems such as Almanac and recent medical GraphRAG variants show the value of retrieval and graph evidence for safer medical question answering (Zakka et al., 2023; Wu et al., 2024). BioRAG-DRAG is complementary to these systems: it focuses on local-first biological retrieval across text, DNA/cDNA, protein windows, and graph evidence, rather than on clinical QA alone.

**Biological foundation models.** Protein language models show that sequence-only pretraining can learn useful structure and function representations (Rives et al., 2021; Elnaggar et al., 2022; Lin et al., 2023). Dedicated protein-retrieval work such as PLMSearch further demonstrates that learned protein representations can support fast remote-homology search (Liu et al., 2024). Genomic language models, including DNABERT, DNABERT-2, Nucleotide Transformer, HyenaDNA, and Evo, similarly show that DNA-scale pretraining can produce transferable sequence representations (Ji et al., 2021; Zhou et al., 2023; Nguyen et al., 2023; Dalla-Torre et al., 2025; Nguyen et al., 2024). We use the OmniGene-4 CPT merged checkpoint as the main sequence-window embedding model because it includes biological sequence vocabulary and supports DNA/protein/text-style inputs. The model is used as a representation layer; answer generation remains a separate agent/model function.

**Vector databases and graph-augmented retrieval.** Dense vector retrieval has become a common substrate for RAG because approximate nearest-neighbor indexes can serve large precomputed embedding collections efficiently; FAISS is a representative GPU-capable system for billion-scale similarity search (Johnson et al., 2017). Graph-augmented RAG extends this substrate by organizing retrieved records and relations as paths or communities rather than isolated chunks; GraphRAG is one prominent recent example for text corpora (Edge et al., 2024). Biological data are naturally graph structured: retrieved sequences often need to connect to genes, proteins, annotations, pathways, variants, and literature. BioRAG-DRAG evaluates both method-agnostic vector-neighbor graphs and BLAST-enriched hybrid graphs, asking whether biological structure appears before explicit domain rules are added.

**Local biomedical agents and this work's lineage.** BioRAG-DRAG builds on two local prerequisites. Open-Rosalind defines the auditable biomedical-agent contract: tool-mediated evidence, trace completeness, and bounded workflows (Wang, 2026a). OmniGene-4 provides the biological sequence-text representation model: a Gemma-derived CPT model with expanded biological vocabulary for DNA, protein, structure tokens, and natural-language inputs (Wang, 2026b). This paper connects those two directions by turning the representation model into a retrieval substrate and by packaging retrieval results into the evidence traces expected by a local biomedical agent.

## 3. BioRAG-Standard v0

### 3.1 Corpus Construction

BioRAG-Standard v0 is built from the existing Open-Rosalind Standard index and local sequence-vector extensions. The exported dataset is stored under `data/biorag_standard_v0` and uses JSONL files for both corpus records and annotated tasks.

| Corpus partition | Records | Source |
| --- | ---: | --- |
| Standard text | 57,856 | HGNC genes, GO terms, Reactome pathways, ClinVar gene summaries |
| Protein sequence windows | 100,000 | Swiss-Prot windows embedded with OmniGene CPT |
| DNA/cDNA sequence windows | 100,000 | Ensembl cDNA windows embedded with OmniGene CPT |
| Mixed POC records | 30 | mixed English/sequence examples |
| **Total** | **257,886** | text + protein + DNA/cDNA + mixed |

Each corpus row contains a stable dataset-local ID, source record ID, biological entity ID, source accession, modality, partition, retrievable text or sequence, extracted biological labels, and traceable metadata. Sequence-window records preserve parent accession, parent record ID, window offset, window size, stride, alphabet, and source FASTA header.

### 3.2 Annotated Tasks

The current task layer contains 112 retrieval tasks:

| Task family | Records |
| --- | ---: |
| Gene lookup | 5 |
| Pathway lookup | 3 |
| Protein sequence retrieval | 52 |
| DNA/cDNA sequence retrieval | 52 |
| **Total** | **112** |

All tasks have at least one `positive_corpus_refs` link in the full export, enabling evaluation by direct corpus references as well as by expected labels such as entity IDs, source IDs, accessions, symbols, and biological gene labels.

### 3.3 Role in the Study

The dataset is not just a static benchmark. It is the shared substrate for all retrieval conditions:

- text lookup over Standard records,
- vector search over Standard text and sequence windows,
- BLAST over sequence records,
- hybrid BioRAG with route-gated retrieval,
- DRAG graph construction and biological enrichment analysis.

This shared substrate makes ablations cleaner: removing DNA, protein, text, graph, or BLAST routes changes the retrieval view without changing the underlying evidence universe.

![Figure 2. BioRAG-Standard v0 composition. The benchmark/library contains 257,886 retrievable records across Standard text, protein windows, DNA/cDNA windows, and mixed records, with 112 annotated retrieval tasks.](figures/fig2_dataset.pdf)

## 4. Method

### 4.1 Typed Multimodal Records

Records are typed before embedding or indexing. Examples include Standard biomedical text, protein sequence windows, DNA/cDNA sequence windows, and mixed English/sequence records. For sequence-window retrieval, the document body is the biological sequence itself, while metadata carries the parent accession and source information. This avoids embedding long header-heavy FASTA records as single documents and improves fragment retrieval.

The main sequence-window indexes use the full merged OmniGene CPT model in BF16. Windows use a size of 128 and stride of 64. The Chroma collections contain 100,000 DNA/cDNA windows and 100,000 protein windows, each with 2816-dimensional embeddings. Standard text is also available in Chroma with 57,856 records.

### 4.2 Vector Coarse Retrieval

Vector retrieval serves two purposes:

1. **Instant mode.** It returns fast provisional context for interactive use.
2. **Candidate generation.** It produces top-N sequence/entity candidates for downstream biological verification.

For sequence-window queries, long inputs are split into query windows, then results are merged across windows. A lightweight sequence-aware reranker can optionally combine vector similarity with sequence overlap features. This reranker is not intended to replace BLAST; it is used to test whether simple local features can improve the vector candidate layer.

### 4.3 BLAST Verification and Reranking

For sequence inputs, BLASTP or BLASTN is used as the alignment-grounded verification route. In the current implementation, BLAST is run against local Swiss-Prot and Ensembl cDNA databases. The intended pipeline is:

```text
vector top-N candidates
  -> BLAST fine scoring or full-database fallback
  -> reranked evidence with alignment metadata
```

We evaluate both full-database BLAST and candidate-subset BLAST. In the candidate-subset condition, vector retrieval first selects top-N parent accessions, `blastdbcmd` extracts those candidates from the local BLAST database, and BLASTP/BLASTN reranks only that candidate FASTA. This condition measures whether vector retrieval can supply a useful candidate set for verified BioRAG, while full-database BLAST remains the reference verification route.

### 4.4 DRAG Evidence Graphs

DRAG graphs convert retrieved records and relations into graph evidence. We build three sequence-window graph views:

- **vector-only graph:** edges are nearest-neighbor vector relations;
- **BLAST-only graph:** edges are alignment-derived sequence neighbors;
- **hybrid graph:** vector and BLAST edges are merged while preserving edge types.

The vector-only graph deliberately follows a method-agnostic text-RAG recipe: records become nodes, nearest-neighbor retrieval creates edges, and biological labels are used only for downstream analysis. This lets us test whether biological structure emerges before explicit biological rules are added.

## 5. Experiments

### 5.1 Retrieval Conditions

We evaluate:

- **BLAST:** local BLASTP/BLASTN sequence retrieval;
- **Vector:** OmniGene vector retrieval over sequence-window Chroma collections;
- **Vector + sequence rerank:** vector retrieval plus lightweight sequence-overlap reranking;
- **Vector -> candidate BLAST rerank:** vector top-N parent accessions followed by BLAST scoring on the candidate FASTA subset;
- **Hybrid gated:** route-gated BioRAG using BLAST and vector for sequence queries, and FTS/graph/vector for text queries.

Metrics include Hit@k, MRR, biological Hit@k, biological MRR, average latency, route coverage, and retrieval traces.

### 5.2 Engineering Latency

Latency is decomposed into:

- vector-index lookup,
- BLAST route time,
- graph expansion,
- verified-mode median sum,
- FAISS CPU lookup.

All vector lookup measurements exclude model cold start, query embedding generation, LLM generation, and network calls. This isolates the indexed retrieval stage after a resident embedding service has produced the query vector.

### 5.3 Graph Biological Structure

We evaluate whether sequence-vector graphs contain biological structure by measuring:

- neighborhood enrichment against random baselines,
- community enrichment for gene symbols, gene families, and biotypes,
- functional enrichment against GO and Reactome annotations through local UniProt/NCBI/HGNC cross-references,
- graph-level structure in vector-only, BLAST-only, and hybrid graphs.

## 6. Results

### 6.1 Retrieval Quality

On the 100-query BioRAG-Standard sequence subset, the retrieval results are:

| Condition | Exact Hit@10 | Exact MRR | Biological Hit@10 | Biological MRR | Scope |
| --- | ---: | ---: | ---: | ---: | --- |
| BLAST | 0.73 | 0.5425 | 0.9899 | 0.9768 | full local BLAST database |
| Vector | 0.50 | 0.4063 | 0.8182 | 0.7088 | OmniGene/Chroma |
| Vector + sequence rerank | 0.70 | 0.5987 | 0.9293 | 0.9217 | vector plus sequence-overlap features |
| Vector -> candidate BLAST rerank, N=50 | 0.57 | 0.4898 | 0.8687 | 0.8687 | candidate FASTA BLAST |
| Vector -> candidate BLAST rerank, N=200 | 0.65 | 0.5377 | 0.9293 | 0.9293 | candidate-budget sweep |
| Hybrid gated | 0.73 | 0.5516 | 0.9899 | 0.9775 | route-gated BLAST/vector/graph |

BLAST remains the strongest verification route. Vector-only retrieval is weaker on exact parent-ID recovery, but it recovers biologically related neighborhoods often enough to serve as a useful coarse-retrieval layer. The sequence-aware reranker narrows much of the gap, improving biological Hit@10 from 0.8182 to 0.9293. Candidate-subset BLAST converts vector candidates into alignment-labeled evidence; increasing the candidate pool from 50 to 200 improves biological Hit@10/MRR from 0.8687/0.8687 to 0.9293/0.9293, with candidate biological recall rising to 0.9596. By modality, DNA/cDNA reaches biological Hit@10 0.9600 and candidate biological recall 1.0000 at 200 candidates, while protein plateaus at biological Hit@10 0.8980 and candidate biological recall 0.9184. This identifies protein-side candidate generation as the main remaining retrieval bottleneck. Hybrid gated retrieval preserves BLAST-level biological recall while retaining vector neighborhoods and route traces for agent use.

The interpretation is therefore not "vector beats BLAST." The result supports a two-stage strategy: vector retrieval supplies fast candidates and instant context; BLAST supplies alignment-grounded verification.

![Figure 3. Retrieval quality on the 100-query sequence subset. BLAST remains the strongest alignment-grounded verifier, while vector retrieval provides useful candidate pools; candidate BLAST improves as the vector overfetch budget increases.](figures/fig3_retrieval_quality.pdf)

### 6.2 Engineering Latency

Standard text and 100k BF16 sequence-window indexes give the following lookup and verification times:

| Component | Text / Standard | DNA/cDNA | Protein | Notes |
| --- | ---: | ---: | ---: | --- |
| Chroma instant lookup, top-10 | 4.6924 ms | 5.9630 ms | 6.0948 ms | query embedding excluded |
| BLAST top-10 | n/a | 294.5684 ms | 1081.9300 ms | local BLAST |
| Hybrid graph expansion | n/a | 0.3540 ms | 0.3254 ms | SQLite graph expansion |
| Verified vector+BLAST+graph | n/a | 300.8221 ms | 1088.8706 ms | median route-latency sum |
| FAISS CPU lookup, IndexFlatIP | 8.3346 ms | 15.4626 ms | 15.6090 ms | flat top-10 lookup |

These results support an **instant/verified** product design. In instant mode, vector retrieval returns a provisional multimodal context in a few milliseconds after embedding. In verified mode, BLAST and DRAG add biological grounding and evidence attribution. The current FAISS GPU wheel detects the RTX PRO 6000 Blackwell GPU but lacks compatible `sm_120` kernels; GPU lookup is therefore left as an engineering follow-up rather than a reported result.

![Figure 4. Instant and verified retrieval latency. Vector lookup is measured after query embedding and supports an instant mode; BLAST dominates verified-mode latency, while graph expansion is negligible.](figures/fig4_latency.pdf)

### 6.3 DRAG Graph Structure

The 10k sequence-window graph analyses show complementary structure:

| Modality | Graph | Nodes | Edges | Components | Communities | Modularity | Key biological signal |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| DNA/cDNA | vector-only | 579 | 19,344 | 2 | 9 | 0.1741 | IGKV community: 50/66, enrichment x6.178 |
| DNA/cDNA | BLAST-only | 579 | 995 | 219 | 220 | 0.9383 | compact IGHV/IGKV/IGLV alignment modules |
| DNA/cDNA | hybrid | 579 | 19,592 | 2 | 7 | 0.1739 | IGKV 51/60, enrichment x6.9317; IG_J_gene and IG_D_gene modules |
| Protein | vector-only | 2,623 | 31,794 | 2 | 16 | 0.3179 | pgl 51/306 x4.4158; yfbR 42/226 x11.6062 |
| Protein | BLAST-only | 2,623 | 7,572 | 421 | 447 | 0.9721 | compact but fragmented alignment components |
| Protein | hybrid | 2,623 | 35,549 | 1 | 12 | 0.3779 | pgl 71/519 x3.6245; yfbR 42/63 x41.6349 |

BLAST-only graphs are precise and modular but highly fragmented. Vector-only graphs provide broad connectivity and enriched neighborhoods. Hybrid graphs preserve vector reachability while injecting alignment-supported local edges. This is useful for agent context construction because the downstream model can distinguish representation similarity from alignment evidence.

### 6.4 Neighborhood Enrichment

A rule-free vector-neighborhood enrichment experiment compares vector neighbors against random neighbors from the same collection:

| Target | Match | Vector Hit@10 | Random Hit@10 | Vector P@10 | Random P@10 |
| --- | --- | ---: | ---: | ---: | ---: |
| Protein windows | `GN=` / gene symbol | 0.4300 | 0.0200 | 0.1710 | 0.0020 |
| DNA/cDNA windows | gene ID | 0.6900 | 0.0600 | 0.2460 | 0.0060 |
| DNA/cDNA windows | gene symbol | 0.7188 | 0.0625 | 0.2563 | 0.0063 |
| DNA/cDNA windows | any identity | 0.7100 | 0.0600 | 0.2570 | 0.0060 |

This does not prove a biological mechanism. It does show that a method-agnostic vector-neighbor graph contains non-random biological label structure before BLAST, domain, or pathway rules are added.

### 6.5 Community Purity

Community-level purity analysis further supports the biological-structure claim. In DNA/cDNA graphs, vector-only communities recover IG-family and IG-biotype structure: for example, an IGKV vector community contains 50/64 labeled IGKV nodes within a 66-node community, and compact IG_D/IG_J modules reach 1.0 labeled purity. The hybrid DNA/cDNA graph keeps this structure while adding BLAST edges, including an IGKV community with 51/58 labeled IGKV nodes and compact IG_D/IG_J communities.

Protein graphs show the same pattern with gene-symbol modules. Vector-only protein communities include a `pgl` module with 51/251 labeled nodes inside a 306-node community, while the hybrid graph contains `pgl` 71/467 and `yfbR` 42/62 labeled-neighbor modules. BLAST-only graphs are highly modular and often label-pure, but they fragment into many components. These results are best interpreted as hypothesis-generating biological structure in DRAG graphs, not as proof that vector edges have BLAST-like statistical meaning.

### 6.6 Functional Enrichment

We next connect graph communities to curated biological vocabularies. Nodes are mapped through local HGNC, UniProt, NCBI Gene, GOA human, NCBI gene2go, and Reactome mapping files. Enrichment is tested against annotated nodes within each graph/source and corrected with Benjamini-Hochberg adjustment.

| Graph | GO annotated nodes | Reactome annotated nodes | Top GO signal | Top Reactome signal |
| --- | ---: | ---: | --- | --- |
| DNA/cDNA vector-only | 155 | 68 | proton transmembrane transport, 11/52, q=0.000113 | Metabolism, 12/26, q=0.000015 |
| DNA/cDNA BLAST-only | 155 | 68 | immunoglobulin mediated immune response, 11/11, q=0.000019 | no mapped top term |
| DNA/cDNA hybrid | 155 | 68 | proton transmembrane transport, 11/50, q=0.000088 | Metabolism, 12/26, q=0.000015 |
| Protein vector-only | 63 | 213 | intracellular protein localization, 6/8, q=0.000516 | metabolism of steroid hormones, 6/26, q=0.000452 |
| Protein BLAST-only | 63 | 213 | postsynaptic membrane, 5/5, q=0.000042 | GPCR downstream signalling, 9/25, q=0.000126 |
| Protein hybrid | 63 | 213 | focal adhesion, 5/8, q=0.000539 | TP53 regulates metabolic genes, 7/42, q=0.000223 |

These results move the DRAG analysis beyond label purity. Communities formed from vector and hybrid sequence-neighbor graphs can be linked to curated functional annotations, supporting the use of DRAG as a hypothesis-generating biological representation layer. The claim remains bounded: enrichment indicates annotation coherence in graph communities, not causal mechanism.

### 6.7 Literature Evidence Support

We also test whether graph communities share literature evidence. Nodes are mapped to NCBI Gene IDs through the local graph cross-reference layer, then to PubMed IDs through `gene2pubmed.gz`. This analysis does not use article text; it tests whether communities contain shared PubMed evidence anchors.

| Graph | NCBI-mapped nodes | PubMed nodes | Unique PMIDs | Communities with shared PMIDs | Top shared PMID signal |
| --- | ---: | ---: | ---: | ---: | --- |
| DNA/cDNA vector-only | 197 | 196 | 1,092 | 7 | PMID:19050702, 12/63, q=0.000314 |
| DNA/cDNA BLAST-only | 197 | 196 | 1,092 | 20 | PMID:8490662, 9/24, q=0.000596 |
| DNA/cDNA hybrid | 197 | 196 | 1,092 | 6 | PMID:20301403, 11/59, q=0.000312 |
| Protein vector-only | 63 | 63 | 5,856 | 4 | PMID:11697890, 6/8, q=0.000146 |
| Protein BLAST-only | 63 | 63 | 5,856 | 13 | PMID:25402006, 4/4, q=0.000682 |
| Protein hybrid | 63 | 63 | 5,856 | 4 | PMID:27432908, 8/8, q=0.000159 |

This adds a literature-evidence layer to the biological-meaning argument. BLAST graphs produce many compact shared-literature modules, while vector and hybrid graphs still retain shared PubMed evidence in broader communities. Together with GO/Reactome enrichment, this supports the claim that DRAG communities can be inspected as biological evidence structures, not only as retrieval neighborhoods.

![Figure 5. DRAG biological-structure analysis. Vector, BLAST, and hybrid graphs expose different graph connectivity, functional enrichment, and literature-sharing patterns; these signals support hypothesis-generating biological evidence organization.](figures/fig5_drag_biology.pdf)

## 7. Discussion

### 7.1 Why Vector Retrieval Matters Even When BLAST Is Stronger

BLAST is stronger for alignment-grounded verification and should remain the baseline for exact sequence similarity. However, agent systems need more than exact sequence matching. They need a unified evidence interface that can retrieve text, sequences, annotations, and graph paths, then package them into prompt-ready citations. Vector retrieval provides this shared substrate. The right comparison is not vector versus BLAST as mutually exclusive tools, but vector as coarse candidate generation and BLAST as fine verification.

### 7.2 Instant and Verified Retrieval Modes

The latency results motivate two operating modes. Instant mode returns vector-only context quickly enough for interactive use. Verified mode runs BLAST and DRAG expansion to attach biologically grounded evidence. This design fits biomedical agents: the user can receive a provisional answer immediately, while the system appends verified evidence when the slower routes finish.

### 7.3 DRAG as a Biological Representation Probe

The graph results suggest that sequence-vector neighborhoods can contain biological structure, not just retrieval convenience. DNA/cDNA graphs recover immunoglobulin family modules, and protein graphs show gene-symbol enriched communities. Hybrid graphs improve evidence attribution by preserving both vector and BLAST edge types. The community purity, GO/Reactome enrichment, and shared PubMed evidence results are especially important for the paper thesis: a graph built using a generic RAG-style nearest-neighbor recipe can still expose non-random biological labels, functional annotations, and literature-supported communities. This supports a broader research question: can multimodal BioRAG graphs become useful biological representation layers?

## 8. Limitations

BioRAG-Standard v0 is still a first version. The current tasks emphasize lookup and sequence-fragment retrieval. Multi-hop sequence-to-function, sequence-to-pathway, and literature-grounded tasks are needed for stronger agent evaluation. The mixed partition is small and should be expanded with abstracts, UniProt function text, pathway descriptions, and sequence snippets.

The current vector reranker is lightweight, and candidate-subset BLAST reranking is limited by whether the vector candidate pool contains the correct or biologically equivalent parent sequence. A preliminary graph-expanded retrieval ablation used 10k view graphs rather than a full 100k or complete sequence graph; it added graph candidates but did not improve recall beyond the vector seed pool, so it is treated as a coverage-limited result rather than a central claim. FAISS GPU lookup is not reported because the available wheel lacks Blackwell-compatible kernels on the current RTX PRO 6000 machine. Functional and literature enrichment coverage depends on local UniProt/NCBI/HGNC mappings; Pfam or InterPro domain enrichment and title-level literature case studies would strengthen biological interpretation.

The biological-meaning analysis should also be interpreted carefully. Community purity, GO/Reactome enrichment, and shared PubMed IDs show that DRAG neighborhoods are non-random and inspectable, but they do not prove causal mechanisms or validate novel wet-lab hypotheses. The appropriate use is hypothesis generation, evidence organization, and agent grounding. Biological claims that affect experimental design, diagnosis, treatment, or safety-critical decisions should still be verified by domain experts and specialized tools.

## 9. Reproducibility and Use Scope

The implementation is local-first. The benchmark export lives under `data/biorag_standard_v0`; retrieval and graph reports are stored under `reports/`; and the main evaluation scripts are in `scripts/`. The sequence-vector experiments use the full OmniGene-4 CPT merged model in BF16, not the GGUF or 4-bit quantized variants, for paper-facing results. The vector store is Chroma for the POC because it supports simple CRUD and collection management, while FAISS CPU is used as a lightweight lookup-speed reference. BLAST runs against local Swiss-Prot and Ensembl cDNA databases.

The main reported commands are documented in `docs/EVALUATION.md` and `reports/biorag_research_matrix.md`, including vector candidate-budget sweeps, vector-to-BLAST reranking, instant/verified latency decomposition, DRAG graph construction, functional enrichment, and literature support analysis. The reported vector lookup timings exclude model cold start, query embedding generation, LLM generation, and network calls. This choice isolates the indexed retrieval stage after embeddings are resident or precomputed.

BioRAG-DRAG is intended for research and evidence organization, not autonomous biomedical decision-making. The system can help retrieve, rank, and package evidence for a human or an auditable agent workflow, but it should not be used as a standalone clinical or experimental authority. The design deliberately keeps BLAST, curated annotations, graph evidence, and literature traces visible so that downstream users can inspect which route supported each claim.

## 10. Conclusion

BioRAG-DRAG provides a unified local retrieval layer for biomedical agents by combining neural sequence-text retrieval, classical biological verification, and evidence graph expansion. The current results show that vector retrieval is fast and biologically meaningful enough to serve as a coarse multimodal candidate layer, while BLAST remains essential for alignment-grounded verification. Hybrid DRAG graphs preserve broad vector connectivity and add typed biological evidence paths, making the system better suited to agent workflows than any single retrieval route alone. This positions BioRAG-DRAG as a practical and scientifically interpretable direction for local-first multimodal biomedical agents.

## References

Altschul, S. F., Gish, W., Miller, W., Myers, E. W., and Lipman, D. J. (1990). Basic local alignment search tool. *Journal of Molecular Biology*, 215(3), 403-410.

Bolton, E., Venigalla, A., Yasunaga, M., Hall, D., Xiong, B., Lee, T., Daneshjou, R., Frankle, J., Liang, P., Carbin, M., and Manning, C. D. (2024). BioMedLM: A 2.7B parameter language model trained on biomedical text. arXiv:2403.18421.

Buchfink, B., Reuter, K., and Drost, H.-G. (2021). Sensitive protein alignments at tree-of-life scale using DIAMOND. *Nature Methods*, 18, 366-368.

Dalla-Torre, H., Gonzalez, L., Mendoza-Revilla, J., Lopez Carranza, N., Grzywaczewski, A. H., Oteri, F., Dallago, C., Trop, E., de Almeida, B. P., Sirelkhatim, H., and others. (2025). Nucleotide Transformer: building and evaluating robust foundation models for human genomics. *Nature Methods*, 22, 287-297.

Edge, D., Trinh, H., Cheng, N., Bradley, J., Chao, A., Mody, A., Truitt, S., Metropolitansky, D., Ness, R. O., and Larson, J. (2024). From local to global: a graph RAG approach to query-focused summarization. arXiv:2404.16130.

Elnaggar, A., Heinzinger, M., Dallago, C., Rehawi, G., Wang, Y., Jones, L., Gibbs, T., Feher, T., Angerer, C., Steinegger, M., Bhowmik, D., and Rost, B. (2022). ProtTrans: toward understanding the language of life through self-supervised learning. *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 44(10), 7112-7127.

Gu, Y., Tinn, R., Cheng, H., Lucas, M., Usuyama, N., Liu, X., Naumann, T., Gao, J., and Poon, H. (2022). Domain-specific language model pretraining for biomedical natural language processing. *ACM Transactions on Computing for Healthcare*, 3(1), 1-23.

Ji, Y., Zhou, Z., Liu, H., and Davuluri, R. V. (2021). DNABERT: pre-trained Bidirectional Encoder Representations from Transformers model for DNA-language in genome. *Bioinformatics*, 37(15), 2112-2120.

Johnson, J., Douze, M., and Jegou, H. (2017). Billion-scale similarity search with GPUs. arXiv:1702.08734.

Lee, J., Yoon, W., Kim, S., Kim, D., Kim, S., So, C. H., and Kang, J. (2020). BioBERT: a pre-trained biomedical language representation model for biomedical text mining. *Bioinformatics*, 36(4), 1234-1240.

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Kuttler, H., Lewis, M., Yih, W.-t., Rocktaschel, T., Riedel, S., and Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems*.

Lin, Z., Akin, H., Rao, R., Hie, B., Zhu, Z., Lu, W., Smetanin, N., Verkuil, R., Kabeli, O., Shmueli, Y., and others. (2023). Evolutionary-scale prediction of atomic-level protein structure with a language model. *Science*, 379(6637), 1123-1130.

Liu, W., Wang, Z., You, R., Xie, C., Wei, H., Xiong, Y., Yang, J., and Zhu, S. (2024). PLMSearch: protein language model powers accurate and fast search for remote homology. *Nature Communications*, 15, 2775.

Luo, R., Sun, L., Xia, Y., Qin, T., Zhang, S., Poon, H., and Liu, T.-Y. (2022). BioGPT: generative pre-trained transformer for biomedical text generation and mining. *Briefings in Bioinformatics*, 23(6), bbac409.

Nguyen, E., Poli, M., Faizi, M., Thomas, A., Birch-Sykes, C., Wornow, M., Patel, A., Rabideau, C., Massaroli, S., Bengio, Y., Ermon, S., Baccus, S. A., and Re, C. (2023). HyenaDNA: long-range genomic sequence modeling at single nucleotide resolution. *Advances in Neural Information Processing Systems*.

Nguyen, E., Poli, M., Durrant, M. G., Kang, B., Katrekar, D., Li, D. B., Bartie, L. J., Thomas, A. W., King, S. H., Brixi, G., and others. (2024). Sequence modeling and design from molecular to genome scale with Evo. *Science*.

Rives, A., Meier, J., Sercu, T., Goyal, S., Lin, Z., Liu, J., Guo, D., Ott, M., Zitnick, C. L., Ma, J., and Fergus, R. (2021). Biological structure and function emerge from scaling unsupervised learning to 250 million protein sequences. *Proceedings of the National Academy of Sciences*, 118(15), e2016239118.

Steinegger, M., and Soeding, J. (2017). MMseqs2 enables sensitive protein sequence searching for the analysis of massive data sets. *Nature Biotechnology*, 35, 1026-1028.

Wang, L. (2026a). Open-Rosalind: tool-first biomedical LLM agents with process-aware benchmarking. Manuscript.

Wang, L. (2026b). OmniGene-4: a unified bio-language MoE model with router-level interpretability. Manuscript.

Wu, J., Zhu, J., Qi, Y., Chen, J., Xu, M., Menolascina, F., and Grau, V. (2024). Medical Graph RAG: towards safe medical large language model via graph retrieval-augmented generation. arXiv:2408.04187.

Zakka, C., Chaurasia, A., Shad, R., Dalal, A. R., Kim, J. L., Moor, M., Alexander, K., Ashley, E., Boyd, J., Boyd, K., Hirsch, K., Langlotz, C., Nelson, J., and Hiesinger, W. (2023). Almanac: retrieval-augmented language models for clinical medicine. arXiv:2303.01229.

Zhou, Z., Ji, Y., Li, W., Dutta, P., Davuluri, R. V., and Liu, H. (2023). DNABERT-2: efficient foundation model and benchmark for multi-species genome. arXiv:2306.15006.
