# DRAG Biological Significance Plan

Date: 2026-05-16

Purpose: keep the paper focused on the biological meaning of DRAG graphs, not
only on retrieval engineering. The central question is whether sequence-derived
RAG graphs expose biologically meaningful structure before and after adding
classical biological evidence such as BLAST.

## Core Question

Can a graph built from biological sequence representations recover meaningful
biological neighborhoods, such as gene families, homologous modules, functional
groups, or pathway-related communities?

This should be framed carefully:

- Vector-neighbor edges are representation evidence, not alignment evidence.
- BLAST-neighbor edges are alignment evidence, not multimodal evidence.
- Hybrid DRAG preserves both edge types, allowing an agent to distinguish broad
  representation similarity from local biological alignment.

## Current Evidence

### Neighborhood Enrichment

Pure vector neighborhoods, with same-parent windows excluded and parent records
deduplicated, are enriched over random baselines:

| Target | Match | Vector Hit@10 | Random Hit@10 | Vector P@10 | Random P@10 |
| --- | --- | ---: | ---: | ---: | ---: |
| Protein windows | `GN=` / gene symbol | 0.4300 | 0.0200 | 0.1710 | 0.0020 |
| DNA/cDNA windows | gene ID | 0.6900 | 0.0600 | 0.2460 | 0.0060 |
| DNA/cDNA windows | gene symbol | 0.7188 | 0.0625 | 0.2563 | 0.0063 |
| DNA/cDNA windows | any identity | 0.7100 | 0.0600 | 0.2570 | 0.0060 |

Interpretation: even before BLAST/domain/pathway rules are added, vector
neighborhoods recover biological labels far above random. This is the first
evidence that DRAG sequence graphs are not arbitrary nearest-neighbor caches.

### Community Structure

10k view graph analyses show complementary behavior:

| Modality | Graph | Biological signal |
| --- | --- | --- |
| DNA/cDNA vector-only | IGKV 50/66, enrichment x6.178; IGHV and IG_D/J modules also appear |
| DNA/cDNA BLAST-only | compact IGHV/IGKV/IGLV alignment modules, but 219 connected components |
| DNA/cDNA hybrid | IGKV 51/60, enrichment x6.9317; IG_J_gene and IG_D_gene compact modules |
| Protein vector-only | pgl 51/306 x4.4158; yfbR 42/226 x11.6062 |
| Protein BLAST-only | compact but fragmented alignment components |
| Protein hybrid | fully connected graph; yfbR 42/63 x41.6349; pgl 71/519 x3.6245 |

Interpretation: BLAST graphs are precise but fragmented; vector graphs provide
global connectivity; hybrid graphs preserve reachability while injecting
alignment-supported local structure.

### Community Purity

The first community-purity report is now available:

- `scripts/evaluate_drag_biological_purity.py`
- `reports/drag_gene_family_purity_10k.json`
- `reports/drag_gene_family_purity_10k.md`

Key signals:

| Graph | Purity signal |
| --- | --- |
| DNA/cDNA vector-only | IGKV 50/64 labeled nodes in a 66-node community; IG_D and IG_J compact modules reach 1.0 labeled purity |
| DNA/cDNA BLAST-only | IGHV/IGKV/IGLV BLAST modules reach 1.0 family purity, but the graph has 219 connected components |
| DNA/cDNA hybrid | IGKV 51/58 labeled nodes in a 60-node community; IG_D/IG_J modules are preserved |
| Protein vector-only | `pgl` 51/251 labeled nodes in a 306-node community; smaller gene-symbol modules are significantly enriched |
| Protein BLAST-only | many compact local modules are highly label-pure, but the graph has 421 connected components |
| Protein hybrid | `pgl` 71/467 and `yfbR` 42/62 labeled-neighbor modules while preserving a single connected graph |

Interpretation: purity analysis strengthens the biological-meaning claim
because it evaluates community composition rather than only retrieval hit rate.
It also clarifies the complementarity: BLAST forms compact alignment modules;
vector graphs provide broader reachability; hybrid graphs keep both properties.

### Functional Enrichment

GO/Reactome enrichment is now implemented:

- `scripts/evaluate_drag_functional_enrichment.py`
- `reports/drag_functional_enrichment_10k.json`
- `reports/drag_functional_enrichment_10k.md`

The script maps DRAG graph nodes through local HGNC/UniProt/NCBI cross-references,
then uses local GOA human, NCBI `gene2go`, UniProt2Reactome, and NCBI2Reactome
files. Enrichment is tested against annotated graph nodes and corrected with
Benjamini-Hochberg.

| Graph | GO annotated nodes | Reactome annotated nodes | Top GO signal | Top Reactome signal |
| --- | ---: | ---: | --- | --- |
| DNA/cDNA vector-only | 155 | 68 | proton transmembrane transport, 11/52, q=0.000113 | Metabolism, 12/26, q=0.000015 |
| DNA/cDNA BLAST-only | 155 | 68 | immunoglobulin mediated immune response, 11/11, q=0.000019 | no mapped top term |
| DNA/cDNA hybrid | 155 | 68 | proton transmembrane transport, 11/50, q=0.000088 | Metabolism, 12/26, q=0.000015 |
| Protein vector-only | 63 | 213 | intracellular protein localization, 6/8, q=0.000516 | metabolism of steroid hormones, 6/26, q=0.000452 |
| Protein BLAST-only | 63 | 213 | postsynaptic membrane, 5/5, q=0.000042 | GPCR downstream signalling, 9/25, q=0.000126 |
| Protein hybrid | 63 | 213 | focal adhesion, 5/8, q=0.000539 | TP53 regulates metabolic genes, 7/42, q=0.000223 |

Interpretation: this is currently the strongest biological-significance layer.
It shows that DRAG communities are not only label-pure; they can also connect
to curated functional vocabularies. The claim remains bounded: enrichment is a
hypothesis-generating community signal, not proof of causal mechanism.

### Literature Support

PubMed support via local NCBI `gene2pubmed.gz` is now implemented:

- `scripts/evaluate_drag_literature_support.py`
- `reports/drag_literature_support_10k.json`
- `reports/drag_literature_support_10k.md`

The script maps graph nodes through HGNC/NCBI cross-references and then tests
whether communities share PubMed evidence anchors.

| Graph | PubMed nodes | Unique PMIDs | Shared-PMID communities | Top shared PMID |
| --- | ---: | ---: | ---: | --- |
| DNA/cDNA vector-only | 196 | 1,092 | 7 | PMID:19050702, 12/63, q=0.000314 |
| DNA/cDNA BLAST-only | 196 | 1,092 | 20 | PMID:8490662, 9/24, q=0.000596 |
| DNA/cDNA hybrid | 196 | 1,092 | 6 | PMID:20301403, 11/59, q=0.000312 |
| Protein vector-only | 63 | 5,856 | 4 | PMID:11697890, 6/8, q=0.000146 |
| Protein BLAST-only | 63 | 5,856 | 13 | PMID:25402006, 4/4, q=0.000682 |
| Protein hybrid | 63 | 5,856 | 4 | PMID:27432908, 8/8, q=0.000159 |

Interpretation: shared PubMed IDs provide an evidence-attribution layer for
DRAG communities. This complements GO/Reactome enrichment and is useful for
agent-facing citations and case studies. It remains a literature-support
signal, not proof of mechanism.

## Biological Meaning Claim Boundary

Safe claim:

> Sequence-vector DRAG graphs contain label-enriched biological neighborhoods
> and can serve as a hypothesis-generating representation layer for agents.

Do not claim yet:

- vector edges prove homology;
- graph communities prove biological mechanism;
- DRAG replaces BLAST or curated pathway databases;
- current gene-symbol enrichment is enough for functional interpretation.

## Next Biological Analyses

### 1. GO and Reactome Enrichment

Goal: connect sequence/protein communities to functional annotations.

Status: first pass complete.

Implemented output:

- `reports/drag_functional_enrichment_10k.json`
- `reports/drag_functional_enrichment_10k.md`

Next improvements:

1. Add Pfam/domain mapping once a local Pfam/InterPro source is added.
2. Resolve top shared PMIDs to title/abstract case studies.
3. Separate high-level pathway terms from specific pathway terms in the paper
   table.

### 2. Gene-Family and Biotype Purity

Goal: make DNA/cDNA graph interpretation stronger.

Status: first pass complete.

Implemented output:

- `reports/drag_gene_family_purity_10k.json`
- `reports/drag_gene_family_purity_10k.md`

Next improvements:

1. Add multiple-testing correction to community enrichment p-values.
2. Separate large-community signals from tiny high-purity modules in the main
   paper table.
3. Treat coarse biotype as supporting context, not a headline metric.

### 3. Agent Evidence Case Studies

Goal: show why graph structure matters for agent use.

Case study format:

```text
query sequence
  -> vector neighbors
  -> BLAST-supported local edges
  -> graph expansion to gene/protein/pathway annotations
  -> route-labeled citations
```

Use examples with clear module labels:

- DNA/cDNA immunoglobulin variable-region query.
- Protein `pgl` or `yfbR` module query.
- A text query that retrieves a gene/pathway and then expands to sequence
  evidence.

Expected output:

- `reports/drag_agent_case_studies.md`
- figure-ready JSON traces under `reports/traces/`

## Paper Placement

This should become a central Results subsection:

1. **Rule-free vector graph enrichment:** proves representation neighborhoods
   have non-random biological structure.
2. **BLAST ablation:** proves alignment edges sharpen local modules but fragment
   the graph.
3. **Hybrid DRAG:** gives the agent both global multimodal reachability and
   alignment-supported local evidence.
4. **Functional/pathway enrichment:** now provides the strongest bridge from
   engineering contribution to biological insight.

## Working Thesis

BioRAG/DRAG begins as an engineering solution for multimodal local retrieval,
but the sequence-derived graph can also become a biological representation
object. Its communities and paths may reveal gene-family, homology, pathway, or
functional structure that is useful for agent reasoning and hypothesis
generation.
