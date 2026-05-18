# DRAG Literature Support

This report maps DRAG graph communities to PubMed evidence through local NCBI Gene IDs and `gene2pubmed.gz`. It reports community-level shared literature structure, not proof of mechanism.

## Coverage and Top Shared Evidence

| Graph | Nodes | NCBI-mapped nodes | PubMed nodes | Unique PMIDs | Communities with shared PMIDs | Top shared PMID |
|---|---:|---:|---:|---:|---:|---|
| dna_vector | 579 | 197 | 196 | 1092 | 7 | PMID:19050702 (12/63, x3.1111, q=0.000314) |
| dna_blast | 579 | 197 | 196 | 1092 | 20 | PMID:8490662 (9/24, x4.5938, q=0.000596) |
| dna_hybrid | 579 | 197 | 196 | 1092 | 6 | PMID:20301403 (11/59, x3.322, q=0.000312) |
| protein_vector | 2623 | 63 | 63 | 5856 | 4 | PMID:11697890 (6/8, x6.75, q=0.000146) |
| protein_blast | 2623 | 63 | 63 | 5856 | 13 | PMID:25402006 (4/4, x15.75, q=0.000682) |
| protein_hybrid | 2623 | 63 | 63 | 5856 | 4 | PMID:27432908 (8/8, x4.5, q=0.000159) |

## Top Shared PMIDs By Graph

### dna_vector

| Community | PMID | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 0 | PMID:19050702 | 12/63 | 12/196 | 3.1111 | 1e-06 | 0.000314 |
| 0 | PMID:20301403 | 11/63 | 11/196 | 3.1111 | 2e-06 | 0.000314 |
| 2 | PMID:36774506 | 9/41 | 11/196 | 3.9113 | 1.4e-05 | 0.000942 |
| 2 | PMID:36950384 | 9/41 | 11/196 | 3.9113 | 1.4e-05 | 0.000942 |
| 1 | PMID:11955599 | 24/66 | 37/196 | 1.9263 | 1.6e-05 | 0.000942 |
| 1 | PMID:814163 | 22/66 | 33/196 | 1.9798 | 2.2e-05 | 0.000942 |
| 0 | PMID:20301353 | 9/63 | 9/196 | 3.1111 | 2.4e-05 | 0.000942 |
| 0 | PMID:28514442 | 9/63 | 9/196 | 3.1111 | 2.4e-05 | 0.000942 |

### dna_blast

| Community | PMID | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 0 | PMID:8490662 | 9/24 | 16/196 | 4.5938 | 9e-06 | 0.000596 |
| 15 | PMID:9074928 | 7/7 | 43/196 | 4.5581 | 1.6e-05 | 0.000596 |
| 6 | PMID:9074928 | 8/9 | 43/196 | 4.0517 | 2.3e-05 | 0.000596 |
| 6 | PMID:8951372 | 7/9 | 29/196 | 5.2567 | 2.3e-05 | 0.000596 |
| 4 | PMID:814163 | 8/11 | 33/196 | 4.3196 | 3.4e-05 | 0.000596 |
| 4 | PMID:1249422 | 8/11 | 33/196 | 4.3196 | 3.4e-05 | 0.000596 |
| 0 | PMID:7951227 | 6/24 | 8/196 | 6.125 | 4.4e-05 | 0.000596 |
| 3 | PMID:8454861 | 3/8 | 3/196 | 24.5 | 4.5e-05 | 0.000596 |

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

### protein_vector

| Community | PMID | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 3 | PMID:11697890 | 6/8 | 7/63 | 6.75 | 3e-06 | 0.000146 |
| 3 | PMID:33761321 | 6/8 | 7/63 | 6.75 | 3e-06 | 0.000146 |
| 3 | PMID:15791647 | 6/8 | 7/63 | 6.75 | 3e-06 | 0.000146 |
| 3 | PMID:20618440 | 6/8 | 7/63 | 6.75 | 3e-06 | 0.000146 |
| 3 | PMID:12433946 | 6/8 | 7/63 | 6.75 | 3e-06 | 0.000146 |
| 3 | PMID:19172738 | 6/8 | 7/63 | 6.75 | 3e-06 | 0.000146 |
| 3 | PMID:12438239 | 6/8 | 7/63 | 6.75 | 3e-06 | 0.000146 |
| 3 | PMID:16045749 | 6/8 | 7/63 | 6.75 | 3e-06 | 0.000146 |

### protein_blast

| Community | PMID | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 8 | PMID:25402006 | 4/4 | 4/63 | 15.75 | 2e-06 | 0.000682 |
| 8 | PMID:24658140 | 4/4 | 4/63 | 15.75 | 2e-06 | 0.000682 |
| 8 | PMID:24510904 | 4/4 | 4/63 | 15.75 | 2e-06 | 0.000682 |
| 7 | PMID:18577758 | 7/9 | 10/63 | 4.9 | 7e-06 | 0.000682 |
| 7 | PMID:12627464 | 6/9 | 7/63 | 6.0 | 8e-06 | 0.000682 |
| 7 | PMID:11916537 | 6/9 | 7/63 | 6.0 | 8e-06 | 0.000682 |
| 68 | PMID:20538960 | 5/5 | 8/63 | 7.875 | 8e-06 | 0.000682 |
| 8 | PMID:35864588 | 4/4 | 5/63 | 12.6 | 8e-06 | 0.000682 |

### protein_hybrid

| Community | PMID | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 1 | PMID:27432908 | 8/8 | 14/63 | 4.5 | 1e-06 | 0.000159 |
| 1 | PMID:30575818 | 8/8 | 14/63 | 4.5 | 1e-06 | 0.000159 |
| 1 | PMID:31871319 | 7/8 | 9/63 | 6.125 | 1e-06 | 0.000159 |
| 1 | PMID:35235311 | 7/8 | 9/63 | 6.125 | 1e-06 | 0.000159 |
| 1 | PMID:25921289 | 8/8 | 15/63 | 4.2 | 2e-06 | 0.000159 |
| 1 | PMID:29395067 | 7/8 | 10/63 | 5.5125 | 2e-06 | 0.000159 |
| 1 | PMID:36736316 | 7/8 | 10/63 | 5.5125 | 2e-06 | 0.000159 |
| 1 | PMID:36526897 | 7/8 | 10/63 | 5.5125 | 2e-06 | 0.000159 |

## Interpretation Boundary

- Shared PubMed IDs are evidence anchors for community-level literature support, not causal biological proof.
- Coverage depends on HGNC/NCBI mappings; non-human protein entries may have limited NCBI Gene mapping through the current local graph.
- This layer complements GO/Reactome enrichment by showing that some graph communities also share literature evidence.
- Title/abstract resolution for top PMIDs is a useful next case-study step.
