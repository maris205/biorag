# DRAG Functional Enrichment

This report maps DRAG graph communities to GO and Reactome annotations through local UniProt, NCBI Gene, and HGNC cross-references. Enrichment is tested against annotated nodes within each graph/source, with Benjamini-Hochberg correction.

## Coverage and Top Signals

| Graph | Nodes | GO annotated | Reactome annotated | Top GO signal | Top Reactome signal |
|---|---:|---:|---:|---|---|
| dna_vector | 579 | 155 | 68 | GO:1902600 proton transmembrane transport (11/52, x2.9808, q=0.000113) | R-HSA-1430728 Metabolism (12/26, x2.6154, q=1.5e-05) |
| dna_blast | 579 | 155 | 68 | GO:0016064 immunoglobulin mediated immune response (11/11, x3.1633, q=1.9e-05) | - |
| dna_hybrid | 579 | 155 | 68 | GO:1902600 proton transmembrane transport (11/50, x3.1, q=8.8e-05) | R-HSA-1430728 Metabolism (12/26, x2.6154, q=1.5e-05) |
| protein_vector | 2623 | 63 | 213 | GO:0008104 intracellular protein localization (6/8, x6.75, q=0.000516) | R-MMU-196071 Metabolism of steroid hormones (6/26, x8.1923, q=0.000452) |
| protein_blast | 2623 | 63 | 213 | GO:0045211 postsynaptic membrane (5/5, x10.5, q=4.2e-05) | R-HSA-388396 GPCR downstream signalling (9/25, x5.4771, q=0.000126) |
| protein_hybrid | 2623 | 63 | 213 | GO:0005925 focal adhesion (5/8, x7.875, q=0.000539) | R-MMU-5628897 TP53 Regulates Metabolic Genes (7/42, x5.0714, q=0.000223) |

## Top Terms By Graph

### dna_vector

#### GO

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 0 | GO:1902600 proton transmembrane transport | 11/52 | 11/155 | 2.9808 | 3e-06 | 0.000113 |
| 3 | GO:0016064 immunoglobulin mediated immune response | 10/10 | 49/155 | 3.1633 | 5e-06 | 0.000113 |
| 0 | GO:0042776 proton motive force-driven mitochondrial ATP synthesis | 9/52 | 9/155 | 2.9808 | 3.3e-05 | 0.000495 |
| 0 | GO:0009060 aerobic respiration | 8/52 | 8/155 | 2.9808 | 0.000109 | 0.001226 |
| 0 | GO:0045271 respiratory chain complex I | 7/52 | 7/155 | 2.9808 | 0.00036 | 0.002025 |
| 0 | GO:0006120 mitochondrial electron transport, NADH to ubiquinone | 7/52 | 7/155 | 2.9808 | 0.00036 | 0.002025 |
| 0 | GO:0008137 NADH dehydrogenase (ubiquinone) activity | 7/52 | 7/155 | 2.9808 | 0.00036 | 0.002025 |
| 0 | GO:0016020 membrane | 7/52 | 7/155 | 2.9808 | 0.00036 | 0.002025 |

#### REACTOME

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 0 | R-HSA-1430728 Metabolism | 12/26 | 12/68 | 2.6154 | 1e-06 | 1.5e-05 |
| 0 | R-HSA-1428517 Aerobic respiration and respiratory electron transport | 12/26 | 12/68 | 2.6154 | 1e-06 | 1.5e-05 |
| 0 | R-HSA-611105 Respiratory electron transport | 10/26 | 10/68 | 2.6154 | 1.8e-05 | 0.00018 |
| 0 | R-HSA-9837999 Mitochondrial protein degradation | 7/26 | 7/68 | 2.6154 | 0.000679 | 0.005092 |
| 0 | R-HSA-6799198 Complex I biogenesis | 6/26 | 6/68 | 2.6154 | 0.002103 | 0.012618 |
| 0 | R-HSA-8953897 Cellular responses to stimuli | 3/26 | 3/68 | 2.6154 | 0.05188 | 0.10376 |
| 0 | R-HSA-9711123 Cellular response to chemical stress | 3/26 | 3/68 | 2.6154 | 0.05188 | 0.10376 |
| 0 | R-HSA-9864848 Complex IV assembly | 3/26 | 3/68 | 2.6154 | 0.05188 | 0.10376 |

### dna_blast

#### GO

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 1 | GO:0016064 immunoglobulin mediated immune response | 11/11 | 49/155 | 3.1633 | 1e-06 | 1.9e-05 |
| 3 | GO:0016064 immunoglobulin mediated immune response | 7/7 | 49/155 | 3.1633 | 0.000231 | 0.000954 |
| 26 | GO:0042105 alpha-beta T cell receptor complex | 2/2 | 3/155 | 51.6667 | 0.000251 | 0.000954 |
| 26 | GO:0046631 alpha-beta T cell activation | 2/2 | 3/155 | 51.6667 | 0.000251 | 0.000954 |
| 26 | GO:0042101 T cell receptor complex | 2/2 | 3/155 | 51.6667 | 0.000251 | 0.000954 |
| 26 | GO:0050852 T cell receptor signaling pathway | 2/2 | 6/155 | 25.8333 | 0.001257 | 0.003412 |
| 26 | GO:0002250 adaptive immune response | 2/2 | 6/155 | 25.8333 | 0.001257 | 0.003412 |
| 11 | GO:0016064 immunoglobulin mediated immune response | 4/4 | 49/155 | 3.1633 | 0.00916 | 0.021755 |

#### REACTOME

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| - | no mapped enrichment | 0 | 0 | 0 | 1 | 1 |

### dna_hybrid

#### GO

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 1 | GO:1902600 proton transmembrane transport | 11/50 | 11/155 | 3.1 | 2e-06 | 8.8e-05 |
| 1 | GO:0042776 proton motive force-driven mitochondrial ATP synthesis | 9/50 | 9/155 | 3.1 | 2.2e-05 | 0.000484 |
| 1 | GO:0009060 aerobic respiration | 8/50 | 8/155 | 3.1 | 7.8e-05 | 0.001144 |
| 1 | GO:0045271 respiratory chain complex I | 7/50 | 7/155 | 3.1 | 0.000269 | 0.001691 |
| 1 | GO:0006120 mitochondrial electron transport, NADH to ubiquinone | 7/50 | 7/155 | 3.1 | 0.000269 | 0.001691 |
| 1 | GO:0008137 NADH dehydrogenase (ubiquinone) activity | 7/50 | 7/155 | 3.1 | 0.000269 | 0.001691 |
| 1 | GO:0016020 membrane | 7/50 | 7/155 | 3.1 | 0.000269 | 0.001691 |
| 1 | GO:0005515 protein binding | 8/50 | 9/155 | 2.7556 | 0.000524 | 0.002882 |

#### REACTOME

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 1 | R-HSA-1430728 Metabolism | 12/26 | 12/68 | 2.6154 | 1e-06 | 1.5e-05 |
| 1 | R-HSA-1428517 Aerobic respiration and respiratory electron transport | 12/26 | 12/68 | 2.6154 | 1e-06 | 1.5e-05 |
| 1 | R-HSA-611105 Respiratory electron transport | 10/26 | 10/68 | 2.6154 | 1.8e-05 | 0.00018 |
| 1 | R-HSA-9837999 Mitochondrial protein degradation | 7/26 | 7/68 | 2.6154 | 0.000679 | 0.005092 |
| 1 | R-HSA-6799198 Complex I biogenesis | 6/26 | 6/68 | 2.6154 | 0.002103 | 0.012618 |
| 1 | R-HSA-8953897 Cellular responses to stimuli | 3/26 | 3/68 | 2.6154 | 0.05188 | 0.10376 |
| 1 | R-HSA-9711123 Cellular response to chemical stress | 3/26 | 3/68 | 2.6154 | 0.05188 | 0.10376 |
| 1 | R-HSA-9864848 Complex IV assembly | 3/26 | 3/68 | 2.6154 | 0.05188 | 0.10376 |

### protein_vector

#### GO

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 3 | GO:0008104 intracellular protein localization | 6/8 | 7/63 | 6.75 | 3e-06 | 0.000516 |
| 3 | GO:0140311 protein sequestering activity | 5/8 | 5/63 | 7.875 | 8e-06 | 0.000688 |
| 3 | GO:0019904 protein domain specific binding | 5/8 | 6/63 | 6.5625 | 4.6e-05 | 0.002637 |
| 3 | GO:0050815 phosphoserine residue binding | 4/8 | 4/63 | 7.875 | 0.000118 | 0.005074 |
| 3 | GO:0005925 focal adhesion | 4/8 | 5/63 | 6.3 | 0.000556 | 0.012957 |
| 3 | GO:0042802 identical protein binding | 6/8 | 13/63 | 3.6346 | 0.000565 | 0.012957 |
| 3 | GO:0070062 extracellular exosome | 6/8 | 13/63 | 3.6346 | 0.000565 | 0.012957 |
| 1 | GO:0000159 protein phosphatase type 2A complex | 11/35 | 11/63 | 1.8 | 0.000678 | 0.012957 |

#### REACTOME

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 2 | R-MMU-196071 Metabolism of steroid hormones | 6/26 | 6/213 | 8.1923 | 2e-06 | 0.000452 |
| 2 | R-MMU-193048 Androgen biosynthesis | 6/26 | 6/213 | 8.1923 | 2e-06 | 0.000452 |
| 2 | R-MMU-194002 Glucocorticoid biosynthesis | 6/26 | 6/213 | 8.1923 | 2e-06 | 0.000452 |
| 2 | R-MMU-193993 Mineralocorticoid biosynthesis | 6/26 | 6/213 | 8.1923 | 2e-06 | 0.000452 |
| 2 | R-MMU-8957322 Metabolism of steroids | 6/26 | 7/213 | 7.022 | 1.2e-05 | 0.00181 |
| 2 | R-MMU-556833 Metabolism of lipids | 6/26 | 7/213 | 7.022 | 1.2e-05 | 0.00181 |
| 2 | R-RNO-193048 Androgen biosynthesis | 4/26 | 4/213 | 8.1923 | 0.000179 | 0.005327 |
| 2 | R-RNO-196071 Metabolism of steroid hormones | 4/26 | 4/213 | 8.1923 | 0.000179 | 0.005327 |

### protein_blast

#### GO

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 68 | GO:0045211 postsynaptic membrane | 5/5 | 6/63 | 10.5 | 1e-06 | 4.2e-05 |
| 68 | GO:0043005 neuron projection | 5/5 | 6/63 | 10.5 | 1e-06 | 4.2e-05 |
| 68 | GO:0006816 calcium ion transport | 5/5 | 6/63 | 10.5 | 1e-06 | 4.2e-05 |
| 50 | GO:0072542 protein phosphatase activator activity | 4/4 | 5/63 | 12.6 | 8e-06 | 0.000254 |
| 68 | GO:0007210 serotonin receptor signaling pathway | 5/5 | 9/63 | 7.0 | 1.8e-05 | 0.000265 |
| 15 | GO:0003854 3-beta-hydroxy-Delta5-steroid dehydrogenase (NAD+) activity | 3/3 | 3/63 | 21.0 | 2.5e-05 | 0.000265 |
| 15 | GO:0006694 steroid biosynthetic process | 3/3 | 3/63 | 21.0 | 2.5e-05 | 0.000265 |
| 15 | GO:0005789 endoplasmic reticulum membrane | 3/3 | 3/63 | 21.0 | 2.5e-05 | 0.000265 |

#### REACTOME

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 7 | R-HSA-388396 GPCR downstream signalling | 9/25 | 14/213 | 5.4771 | 1e-06 | 0.000126 |
| 7 | R-RNO-390666 Serotonin receptors | 8/25 | 11/213 | 6.1964 | 2e-06 | 0.000126 |
| 7 | R-RNO-500792 GPCR ligand binding | 8/25 | 11/213 | 6.1964 | 2e-06 | 0.000126 |
| 7 | R-RNO-375280 Amine ligand-binding receptors | 8/25 | 11/213 | 6.1964 | 2e-06 | 0.000126 |
| 7 | R-RNO-373076 Class A/1 (Rhodopsin-like receptors) | 8/25 | 11/213 | 6.1964 | 2e-06 | 0.000126 |
| 7 | R-MMU-500792 GPCR ligand binding | 8/25 | 11/213 | 6.1964 | 2e-06 | 0.000126 |
| 7 | R-MMU-375280 Amine ligand-binding receptors | 8/25 | 11/213 | 6.1964 | 2e-06 | 0.000126 |
| 7 | R-MMU-390666 Serotonin receptors | 8/25 | 11/213 | 6.1964 | 2e-06 | 0.000126 |

### protein_hybrid

#### GO

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 1 | GO:0005925 focal adhesion | 5/8 | 5/63 | 7.875 | 8e-06 | 0.000539 |
| 1 | GO:0140311 protein sequestering activity | 5/8 | 5/63 | 7.875 | 8e-06 | 0.000539 |
| 1 | GO:0042802 identical protein binding | 7/8 | 13/63 | 4.2404 | 2.2e-05 | 0.000539 |
| 1 | GO:0070062 extracellular exosome | 7/8 | 13/63 | 4.2404 | 2.2e-05 | 0.000539 |
| 7 | GO:0045947 negative regulation of translational initiation | 3/3 | 3/63 | 21.0 | 2.5e-05 | 0.000539 |
| 7 | GO:0008190 eukaryotic initiation factor 4E binding | 3/3 | 3/63 | 21.0 | 2.5e-05 | 0.000539 |
| 7 | GO:0030371 translation repressor activity | 3/3 | 3/63 | 21.0 | 2.5e-05 | 0.000539 |
| 1 | GO:0007165 signal transduction | 7/8 | 15/63 | 3.675 | 8.1e-05 | 0.001529 |

#### REACTOME

| Community | Term | Observed | Global | Enrichment | p | q |
|---:|---|---:|---:|---:|---:|---:|
| 1 | R-MMU-5628897 TP53 Regulates Metabolic Genes | 7/42 | 7/213 | 5.0714 | 8e-06 | 0.000223 |
| 1 | R-MMU-109606 Intrinsic Pathway for Apoptosis | 7/42 | 7/213 | 5.0714 | 8e-06 | 0.000223 |
| 1 | R-MMU-75035 Chk1/Chk2(Cds1) mediated inactivation of Cyclin B:Cdk1 complex | 7/42 | 7/213 | 5.0714 | 8e-06 | 0.000223 |
| 1 | R-MMU-5625740 RHO GTPases activate PKNs | 7/42 | 7/213 | 5.0714 | 8e-06 | 0.000223 |
| 1 | R-MMU-5357801 Programmed Cell Death | 7/42 | 7/213 | 5.0714 | 8e-06 | 0.000223 |
| 1 | R-MMU-69473 G2/M DNA damage checkpoint | 7/42 | 7/213 | 5.0714 | 8e-06 | 0.000223 |
| 1 | R-MMU-111447 Activation of BAD and translocation to mitochondria  | 7/42 | 7/213 | 5.0714 | 8e-06 | 0.000223 |
| 1 | R-MMU-69481 G2/M Checkpoints | 7/42 | 7/213 | 5.0714 | 8e-06 | 0.000223 |

## Interpretation Boundary

- These are community-level functional annotation signals, not proof of mechanism.
- Reactome mappings use local UniProt2Reactome and NCBI2Reactome files.
- GO mappings use local GOA human and NCBI gene2go files; coverage depends on whether graph nodes map to UniProt or NCBI Gene IDs.
- The strongest paper claim is that DRAG communities can be connected to curated biological vocabularies, enabling hypothesis-generating analysis for agents.
