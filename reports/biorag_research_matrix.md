# BioRAG Research Matrix

Date: 2026-05-15

Purpose: connect the dataset, retrieval results, engineering latency, and DRAG
biological-structure analysis into one research logic.

## Central Hypothesis

A biological multimodal RAG system should not replace BLAST. It should use
OmniGene vector retrieval as the fast, unified coarse-retrieval layer, then use
BLAST and DRAG as verification, reranking, and evidence-attribution layers for
LLM agents.

## Research Stack

| Layer | Artifact | Current status | Paper role |
| --- | --- | --- | --- |
| Dataset | `data/biorag_standard_v0` | 257,886 corpus rows; 112 annotated tasks; all tasks linked to positive corpus refs | Dataset/benchmark contribution |
| Vector RAG | Chroma 100k DNA + 100k protein BF16 window indexes | built with full OmniGene CPT merged model | multimodal coarse retrieval |
| Classical baseline | BLASTP Swiss-Prot + BLASTN Ensembl cDNA | available locally | biological verification baseline |
| Candidate rerank | vector top-N parent accessions + candidate-subset BLAST | implemented and evaluated | verified two-stage sequence route |
| Hybrid retrieval | vector + BLAST + graph evidence | implemented as route-gated BioRAG | agent-facing evidence layer |
| DRAG graph | vector-only, BLAST-only, and hybrid 10k view graphs | generated and analyzed | biological-structure analysis |
| Functional enrichment | GO/Reactome enrichment over DRAG communities | implemented from local GOA/gene2go/Reactome mappings | biological-significance analysis |
| Engineering | instant/verified latency decomposition | measured for Chroma, BLAST, graph | system application value |

## Retrieval Results

100-query BioRAG-Standard sequence subset, BF16 OmniGene sequence-window index:

| Condition | Exact Hit@10 | Exact MRR | Biological Hit@10 | Biological MRR | Avg latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| BLAST | 0.73 | 0.5425 | 0.9899 | 0.9768 | 763.29 ms |
| Vector | 0.50 | 0.4063 | 0.8182 | 0.7088 | 430.59 ms |
| Vector + sequence rerank | 0.70 | 0.5987 | 0.9293 | 0.9217 | 748.72 ms |
| Vector -> candidate BLAST rerank | 0.57 | 0.4898 | 0.8687 | 0.8687 | 823.40 ms |
| Hybrid gated | 0.73 | 0.5516 | 0.9899 | 0.9775 | 1016.32 ms |

Interpretation:

- BLAST remains the strongest biological verification route.
- Vector-only is weaker on exact ID recovery but useful enough for coarse
  retrieval and instant context.
- Sequence-aware reranking closes much of the gap.
- Candidate-subset BLAST reranking is now implemented. It reaches biological
  Hit@10/MRR 0.8687, with candidate-pool biological recall 0.8788; therefore
  the next retrieval bottleneck is vector candidate-pool recall, not BLAST
  scoring inside the candidate subset.
- Candidate-budget sweep improves the candidate-subset route to biological
  Hit@10/MRR 0.9293 at 200 candidates, with candidate biological recall 0.9596.
  DNA/cDNA reaches candidate biological recall 1.0000 at 200 candidates, while
  protein plateaus at biological Hit@10 0.8980 and candidate recall 0.9184.
- A first vector+10k-DRAG-expanded candidate ablation adds many graph neighbors
  but does not improve biological recall beyond the vector seed pool
  (0.8788 -> 0.8788). This should be treated as coverage-limited evidence that
  the full-scale DRAG graph is needed for retrieval gains.
- Hybrid gated keeps BLAST-level biological recall while packaging evidence for
  downstream RAG/agent use.

Candidate-subset BLAST by modality:

| Category | Tasks | Exact Hit@10 | Exact MRR | Biological Hit@10 | Biological MRR | Candidate Bio Recall@50 | Avg latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DNA/cDNA | 50 | 0.5400 | 0.4167 | 0.8600 | 0.8600 | 0.8600 | 655.46 ms |
| Protein | 50 | 0.6000 | 0.5629 | 0.8776 | 0.8776 | 0.8980 | 991.35 ms |

Candidate-budget sweep:

| Budget | Exact Hit@10 | Exact MRR | Biological Hit@10 | Biological MRR | Candidate Bio Recall@N |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 0.5700 | 0.4898 | 0.8687 | 0.8687 | 0.8788 |
| 100 | 0.6100 | 0.5151 | 0.8990 | 0.8990 | 0.9293 |
| 200 | 0.6500 | 0.5377 | 0.9293 | 0.9293 | 0.9596 |

DRAG-expanded candidate ablation:

| Condition | Exact Hit@10 | Exact MRR | Biological Hit@10 | Biological MRR | Seed Bio Recall | Expanded Bio Recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vector(50) + 10k DRAG expand -> BLAST | 0.5800 | 0.4912 | 0.8687 | 0.8687 | 0.8788 | 0.8788 |

## Engineering Table

Standard text and 100k BF16 sequence-window indexes:

| Profile / component | Text / Standard | DNA/cDNA | Protein | Status |
| --- | ---: | ---: | ---: | --- |
| Chroma instant lookup, top-10 | 4.6924 ms | 5.9630 ms | 6.0948 ms | measured; query embedding excluded |
| BLAST top-10 | n/a | 294.5684 ms | 1081.9300 ms | measured |
| Hybrid graph expansion | n/a | 0.3540 ms | 0.3254 ms | measured |
| Verified vector+BLAST+graph | n/a | 300.8221 ms | 1088.8706 ms | measured median sum |
| FAISS CPU lookup, IndexFlatIP | 8.3346 ms | 15.4626 ms | 15.6090 ms | measured; top-10 |
| FAISS GPU lookup | blocked | blocked | blocked | `faiss-gpu-cu12` imports and sees 1 GPU, but wheel lacks Blackwell `sm_120` kernels |

FAISS CPU commands:

```bash
python scripts/benchmark_faiss_lookup.py \
  --config configs/standard.yaml \
  --target text \
  --limit 57856 \
  --queries 2000 \
  --top-k 10 \
  --batch-size 256 \
  --fetch-batch-size 5000 \
  --output reports/faiss_cpu_lookup_standard_text_57856.json

python scripts/benchmark_faiss_lookup.py \
  --config configs/standard.yaml \
  --target dna_sequence_window \
  --limit 100000 \
  --queries 5000 \
  --top-k 10 \
  --batch-size 256 \
  --fetch-batch-size 5000 \
  --output reports/faiss_cpu_lookup_dna_sequence_window_100k.json

python scripts/benchmark_faiss_lookup.py \
  --config configs/standard.yaml \
  --target protein_sequence_window \
  --limit 100000 \
  --queries 5000 \
  --top-k 10 \
  --batch-size 256 \
  --fetch-batch-size 5000 \
  --output reports/faiss_cpu_lookup_protein_sequence_window_100k.json
```

FAISS GPU reproduction command after installing a Blackwell-compatible build:

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

Current machine: NVIDIA RTX PRO 6000 Blackwell Server Edition, 97,887 MiB VRAM,
compute capability 12.0. The pip package `faiss-gpu-cu12==1.14.1.post1`
installed successfully and `faiss.get_num_gpus()` returns 1, but even a small
GPU search aborts with `CUDA error 209 no kernel image is available for
execution on the device`. The benchmark script now guards this case and asks for
a Blackwell-compatible FAISS build/container.

## DRAG Biological-Structure Results

10k sequence-window graph analyses:

| Modality | Graph | Nodes | Edges | Components | Communities | Modularity | Key biological signal |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| DNA/cDNA | vector-only | 579 | 19,344 | 2 | 9 | 0.1741 | IGKV community: 50/66, enrichment x6.178; IGHV/IGLV communities also visible |
| DNA/cDNA | BLAST-only | 579 | 995 | 219 | 220 | 0.9383 | compact IGHV/IGKV/IGLV alignment modules |
| DNA/cDNA | hybrid | 579 | 19,592 | 2 | 7 | 0.1739 | IGKV 51/60, enrichment x6.9317; IG_J_gene and IG_D_gene compact modules |
| Protein | vector-only | 2,623 | 31,794 | 2 | 16 | 0.3179 | pgl 51/306 x4.4158; yfbR 42/226 x11.6062 |
| Protein | BLAST-only | 2,623 | 7,572 | 421 | 447 | 0.9721 | compact alignment components, fragmented global graph |
| Protein | hybrid | 2,623 | 35,549 | 1 | 12 | 0.3779 | pgl 71/519 x3.6245; yfbR 42/63 x41.6349; qutE previously observed as compact enriched module |

Neighborhood enrichment also supports the biological-structure claim:

| Target | Match | Vector Hit@10 | Random Hit@10 | Vector P@10 | Random P@10 |
| --- | --- | ---: | ---: | ---: | ---: |
| protein windows | `GN=` / gene symbol | 0.4300 | 0.0200 | 0.1710 | 0.0020 |
| DNA/cDNA windows | gene ID | 0.6900 | 0.0600 | 0.2460 | 0.0060 |
| DNA/cDNA windows | gene symbol | 0.7188 | 0.0625 | 0.2563 | 0.0063 |
| DNA/cDNA windows | any identity | 0.7100 | 0.0600 | 0.2570 | 0.0060 |

Community purity analysis provides a stricter biological-meaning check:

| Graph | Purity signal |
| --- | --- |
| DNA/cDNA vector-only | IGKV 50/64 labeled nodes in a 66-node community; IG_D and IG_J compact modules reach 1.0 labeled purity |
| DNA/cDNA BLAST-only | compact IGHV/IGKV/IGLV modules reach 1.0 family purity but graph fragments into 219 components |
| DNA/cDNA hybrid | IGKV 51/58 labeled nodes in a 60-node community; IG_D/IG_J compact modules preserved |
| Protein vector-only | `pgl` 51/251 labeled nodes in a 306-node community; `yfbR` 42/226 in prior community analysis |
| Protein BLAST-only | many compact, label-pure local modules but 421 connected components |
| Protein hybrid | `pgl` 71/467 and `yfbR` 42/62 labeled-neighbor modules while retaining one connected graph |

GO/Reactome functional enrichment now connects DRAG communities to curated
biological vocabularies:

| Graph | GO annotated nodes | Reactome annotated nodes | Top GO signal | Top Reactome signal |
| --- | ---: | ---: | --- | --- |
| DNA/cDNA vector-only | 155 | 68 | proton transmembrane transport, 11/52, q=0.000113 | Metabolism, 12/26, q=0.000015 |
| DNA/cDNA BLAST-only | 155 | 68 | immunoglobulin mediated immune response, 11/11, q=0.000019 | no mapped top term |
| DNA/cDNA hybrid | 155 | 68 | proton transmembrane transport, 11/50, q=0.000088 | Metabolism, 12/26, q=0.000015 |
| Protein vector-only | 63 | 213 | intracellular protein localization, 6/8, q=0.000516 | metabolism of steroid hormones, 6/26, q=0.000452 |
| Protein BLAST-only | 63 | 213 | postsynaptic membrane, 5/5, q=0.000042 | GPCR downstream signalling, 9/25, q=0.000126 |
| Protein hybrid | 63 | 213 | focal adhesion, 5/8, q=0.000539 | TP53 regulates metabolic genes, 7/42, q=0.000223 |

Literature support via local NCBI gene2pubmed adds a second evidence layer:

| Graph | NCBI-mapped nodes | PubMed nodes | Unique PMIDs | Communities with shared PMIDs | Top shared PMID |
| --- | ---: | ---: | ---: | ---: | --- |
| DNA/cDNA vector-only | 197 | 196 | 1,092 | 7 | PMID:19050702, 12/63, q=0.000314 |
| DNA/cDNA BLAST-only | 197 | 196 | 1,092 | 20 | PMID:8490662, 9/24, q=0.000596 |
| DNA/cDNA hybrid | 197 | 196 | 1,092 | 6 | PMID:20301403, 11/59, q=0.000312 |
| Protein vector-only | 63 | 63 | 5,856 | 4 | PMID:11697890, 6/8, q=0.000146 |
| Protein BLAST-only | 63 | 63 | 5,856 | 13 | PMID:25402006, 4/4, q=0.000682 |
| Protein hybrid | 63 | 63 | 5,856 | 4 | PMID:27432908, 8/8, q=0.000159 |

Interpretation:

- Vector DRAG provides broad connectivity and enriched biological neighborhoods
  even before explicit BLAST/domain/pathway rules.
- BLAST DRAG provides precise local alignment modules but fragments heavily.
- Hybrid DRAG preserves vector reachability while injecting alignment-supported
  local evidence, which is better for agent context construction.
- Shared PubMed IDs show that some DRAG communities also concentrate literature
  evidence. This supports evidence attribution and case-study generation, but
  remains a community-level support signal rather than proof of mechanism.

## Paper Logic

1. **Problem:** existing biological tools are powerful but modality-specific;
   LLM agents need unified, traceable evidence retrieval.
2. **Dataset:** BioRAG-Standard v0 provides a partitioned multimodal corpus and
   annotated retrieval tasks from Standard biomedical data plus sequence-vector
   extensions.
3. **Method:** vector coarse retrieval over a unified BioRAG index, BLAST fine
   reranking/verification, and DRAG evidence graph packaging.
4. **Results:** vector retrieval is fast and sufficiently useful for coarse
   retrieval; BLAST remains strongest for verification; hybrid DRAG gives better
   evidence structure.
5. **Biological analysis:** vector and hybrid sequence graphs show enriched
   gene/family/community, functional, and literature-evidence structure,
   suggesting that the representation graph is not merely an engineering cache.

## Next Experiments

- Improve vector candidate-pool recall for candidate-subset BLAST: larger
  overfetch, graph expansion, and calibrated reranking.
- Build or install a Blackwell-compatible FAISS GPU package/container and fill
  the GPU lookup row.
- Expand BioRAG-Standard tasks with multi-hop sequence-to-function,
  sequence-to-pathway, and literature-grounded questions.
- Add Pfam/domain enrichment and resolve top shared PMIDs to title/abstract
  case studies.
