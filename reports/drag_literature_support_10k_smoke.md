# DRAG Literature Support

This report maps DRAG graph communities to PubMed evidence through local NCBI Gene IDs and `gene2pubmed.gz`. It reports community-level shared literature structure, not proof of mechanism.

## Coverage and Top Shared Evidence

| Graph | Nodes | NCBI-mapped nodes | PubMed nodes | Unique PMIDs | Communities with shared PMIDs | Top shared PMID |
|---|---:|---:|---:|---:|---:|---|
| dna_hybrid | 579 | 197 | 196 | 1092 | 6 | PMID:20301403 (11/59, x3.322, q=0.000312) |
| protein_hybrid | 2623 | 63 | 63 | 5856 | 4 | PMID:27432908 (8/8, x4.5, q=0.000159) |

## Top Shared PMIDs By Graph

### dna_hybrid

| Community | PMID | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 1 | PMID:20301403 | 11/59 | 11/196 | 3.322 | 1e-06 | 0.000312 |
| 0 | PMID:814163 | 26/81 | 33/196 | 1.9065 | 2e-06 | 0.000312 |
| 0 | PMID:11955599 | 28/81 | 37/196 | 1.8312 | 3e-06 | 0.000312 |
| 2 | PMID:36774506 | 9/39 | 11/196 | 4.1119 | 9e-06 | 0.000579 |
| 0 | PMID:1249422 | 25/81 | 33/196 | 1.8331 | 1.3e-05 | 0.000579 |
| 1 | PMID:20301353 | 9/59 | 9/196 | 3.322 | 1.3e-05 | 0.000579 |
| 1 | PMID:28514442 | 9/59 | 9/196 | 3.322 | 1.3e-05 | 0.000579 |
| 1 | PMID:33961781 | 13/59 | 16/196 | 2.6992 | 1.5e-05 | 0.000585 |

### protein_hybrid

| Community | PMID | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 1 | PMID:27432908 | 8/8 | 14/63 | 4.5 | 1e-06 | 0.000159 |
| 1 | PMID:30575818 | 8/8 | 14/63 | 4.5 | 1e-06 | 0.000159 |
| 1 | PMID:31871319 | 7/8 | 9/63 | 6.125 | 1e-06 | 0.000159 |
| 1 | PMID:35235311 | 7/8 | 9/63 | 6.125 | 1e-06 | 0.000159 |
| 1 | PMID:25921289 | 8/8 | 15/63 | 4.2 | 2e-06 | 0.000159 |
| 1 | PMID:29395067 | 7/8 | 10/63 | 5.5125 | 2e-06 | 0.000159 |
| 1 | PMID:27684187 | 7/8 | 10/63 | 5.5125 | 2e-06 | 0.000159 |
| 1 | PMID:36526897 | 7/8 | 10/63 | 5.5125 | 2e-06 | 0.000159 |

## Interpretation Boundary

- Shared PubMed IDs are evidence anchors for community-level literature support, not causal biological proof.
- Coverage depends on HGNC/NCBI mappings; non-human protein entries may have limited NCBI Gene mapping through the current local graph.
- This layer complements GO/Reactome enrichment by showing that some graph communities also share literature evidence.
- Title/abstract resolution for top PMIDs is a useful next case-study step.
