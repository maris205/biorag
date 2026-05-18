# DRAG Biological Purity Analysis

This report summarizes community-level biological label purity for sequence-derived DRAG view graphs. It treats vector edges as representation evidence and BLAST edges as alignment evidence.

## Graph Comparison

| Graph | Nodes | Edges | Components | Communities | Modularity | Top biological signal |
|---|---:|---:|---:|---:|---:|---|
| dna_vector | 579 | 19344 | 2 | 9 | 0.1741 | biotype:IG_D_gene (4, x26.3182, p=2e-06) |
| dna_blast | 579 | 995 | 219 | 220 | 0.9383 | gene_id:ENSG00000288269.1 (3, x96.5, p=1e-06) |
| dna_hybrid | 579 | 19592 | 2 | 7 | 0.1739 | biotype:IG_D_gene (4, x26.3182, p=2e-06) |
| protein_vector | 2623 | 31794 | 2 | 16 | 0.3179 | gene_symbol:MGF (3, x45.75, p=1.6e-05) |
| protein_blast | 2623 | 7572 | 421 | 447 | 0.9721 | gene_symbol:ygfA (2, x874.3333, p=1e-06) |
| protein_hybrid | 2623 | 35549 | 1 | 12 | 0.3779 | gene_symbol:MGF (2, x69.0263, p=0.000296) |

## Top Communities

### dna_vector

- Target: `dna_sequence_window`
- Recipe: `text_style_vector_neighbors`
- Relation rows: `{'vector_neighbor': 25349}`

| Community | Size | Density | Dominant labels |
|---:|---:|---:|---|
| 6 | 4 | 1.0000 | gene_id:ENSG00000282396.1 (1/4, purity 0.2500, x144.75, p=0.006908); gene_symbol:IGHD3-22 (2/4, purity 0.5000, x144.75, p=3.6e-05); biotype:IG_D_gene (4/4, purity 1.0000, x26.3182, p=2e-06) |
| 7 | 4 | 0.6667 | gene_id:ENSG00000282065.1 (1/4, purity 0.2500, x144.75, p=0.006908); gene_symbol:IGHJ4 (2/4, purity 0.5000, x144.75, p=3.6e-05); biotype:IG_J_gene (4/4, purity 1.0000, x24.125, p=2e-06) |
| 0 | 240 | 0.2210 | gene_id:ENSG00000281449.2 (14/240, purity 0.0583, x2.4125, p=4e-06); gene_symbol:BCL2L14 (14/222, purity 0.0631, x2.4125, p=4e-06); gene_family:IGHV (56/64, purity 0.8750, x1.2745, p=0.006062); biotype:protein_coding (159/240, purity 0.6625, x1.3092, p=0.0) |
| 1 | 228 | 0.1759 | gene_id:ENSG00000291428.1 (14/228, purity 0.0614, x2.3702, p=1.6e-05); gene_symbol:BRSK2 (14/210, purity 0.0667, x2.3702, p=1.6e-05); gene_family:IGLV (31/75, purity 0.4133, x1.7494, p=3e-05); biotype:protein_coding (133/228, purity 0.5833, x1.1527, p=0.001766) |
| 5 | 6 | 0.8000 | gene_id:ENSG00000211918.1 (1/6, purity 0.1667, x96.5, p=0.010363); gene_symbol:IGHD2-15 (2/6, purity 0.3333, x96.5, p=9e-05); biotype:IG_D_gene (6/6, purity 1.0000, x26.3182, p=0.0) |
| 4 | 8 | 0.8571 | gene_id:ENSG00000211930.1 (1/8, purity 0.1250, x72.375, p=0.013817); gene_symbol:IGHD3-3 (2/8, purity 0.2500, x72.375, p=0.000167); biotype:IG_D_gene (8/8, purity 1.0000, x26.3182, p=0.0) |
| 3 | 21 | 0.6238 | gene_id:ENSG00000211962.2 (1/21, purity 0.0476, x27.5714, p=0.036269); gene_symbol:IGHV1-46 (2/19, purity 0.1053, x27.5714, p=0.001255); gene_family:IGHV (19/19, purity 1.0000, x4.942, p=0.0); biotype:IG_V_gene (21/21, purity 1.0000, x2.4957, p=0.0) |
| 2 | 66 | 0.2224 | gene_id:ENSG00000282811.1 (2/66, purity 0.0303, x8.7727, p=0.012819); gene_symbol:IGKV1-33 (3/65, purity 0.0462, x8.7727, p=0.001422); gene_family:IGKV (50/64, purity 0.7812, x6.178, p=0.0); biotype:IG_V_gene (65/66, purity 0.9848, x2.4579, p=0.0) |

### dna_blast

- Target: `dna_sequence_window`
- Recipe: `blast_sequence_neighbors`
- Relation rows: `{'blast_neighbor': 1645}`

| Community | Size | Density | Dominant labels |
|---:|---:|---:|---|
| 3 | 18 | 0.3660 | gene_id:ENSG00000282726.1 (1/18, purity 0.0556, x32.1667, p=0.031088); gene_symbol:IGHV4-28 (2/15, purity 0.1333, x32.1667, p=0.000914); gene_family:IGHV (15/15, purity 1.0000, x4.5519, p=0.0); biotype:IG_V_gene (17/18, purity 0.9444, x2.357, p=1e-06) |
| 4 | 15 | 0.3810 | gene_id:ENSG00000273737.3 (1/15, purity 0.0667, x38.6, p=0.025907); gene_symbol:IGLV1-36 (2/15, purity 0.1333, x38.6, p=0.000627); gene_family:IGLV (15/15, purity 1.0000, x12.8667, p=0.0); biotype:IG_V_gene (15/15, purity 1.0000, x2.4957, p=1e-06) |
| 5 | 15 | 0.4286 | gene_id:ENSG00000282182.1 (2/15, purity 0.1333, x38.6, p=0.000627); gene_symbol:IGKV2-40 (3/15, purity 0.2000, x38.6, p=1.4e-05); gene_family:IGKV (15/15, purity 1.0000, x8.1549, p=0.0); biotype:IG_V_gene (15/15, purity 1.0000, x2.4957, p=1e-06) |
| 36 | 3 | 1.0000 | gene_id:ENSG00000288269.1 (3/3, purity 1.0000, x96.5, p=1e-06); gene_symbol:GCGR (3/3, purity 1.0000, x96.5, p=1e-06); biotype:protein_coding (3/3, purity 1.0000, x1.9761, p=0.128932) |
| 38 | 3 | 1.0000 | gene_id:ENSG00000291381.1 (3/3, purity 1.0000, x96.5, p=1e-06); gene_symbol:ARHGEF19 (3/3, purity 1.0000, x96.5, p=1e-06); biotype:protein_coding (3/3, purity 1.0000, x1.9761, p=0.128932) |
| 39 | 3 | 1.0000 | gene_id:ENSG00000291401.1 (3/3, purity 1.0000, x96.5, p=1e-06); gene_symbol:SPATA21 (3/3, purity 1.0000, x96.5, p=1e-06); biotype:protein_coding (3/3, purity 1.0000, x1.9761, p=0.128932) |
| 25 | 4 | 1.0000 | gene_id:ENSG00000211595.2 (1/4, purity 0.2500, x144.75, p=0.006908); gene_symbol:IGKJ3 (1/4, purity 0.2500, x144.75, p=0.006908); biotype:IG_J_gene (4/4, purity 1.0000, x24.125, p=2e-06) |
| 40 | 3 | 1.0000 | gene_id:ENSG00000291470.1 (3/3, purity 1.0000, x72.375, p=2e-06); gene_symbol:PTP4A3 (3/3, purity 1.0000, x72.375, p=2e-06); biotype:protein_coding (3/3, purity 1.0000, x1.9761, p=0.128932) |

### dna_hybrid

- Target: `dna_sequence_window`
- Recipe: `hybrid_vector_blast_neighbors`
- Relation rows: `{'blast_neighbor': 1645, 'vector_neighbor': 25349}`

| Community | Size | Density | Dominant labels |
|---:|---:|---:|---|
| 1 | 234 | 0.2338 | gene_id:ENSG00000281449.2 (14/234, purity 0.0598, x2.4744, p=2e-06); gene_symbol:BCL2L14 (14/216, purity 0.0648, x2.4744, p=2e-06); gene_family:IGHV (56/63, purity 0.8889, x1.3072, p=0.00295); biotype:protein_coding (159/234, purity 0.6795, x1.3427, p=0.0) |
| 5 | 4 | 1.0000 | gene_id:ENSG00000211595.2 (1/4, purity 0.2500, x144.75, p=0.006908); gene_symbol:IGKJ3 (1/4, purity 0.2500, x144.75, p=0.006908); biotype:IG_J_gene (4/4, purity 1.0000, x24.125, p=2e-06) |
| 6 | 4 | 1.0000 | gene_id:ENSG00000282396.1 (1/4, purity 0.2500, x144.75, p=0.006908); gene_symbol:IGHD3-22 (2/4, purity 0.5000, x144.75, p=3.6e-05); biotype:IG_D_gene (4/4, purity 1.0000, x26.3182, p=2e-06) |
| 0 | 257 | 0.1563 | gene_id:ENSG00000291428.1 (14/257, purity 0.0545, x2.1027, p=8.5e-05); gene_symbol:BRSK2 (14/237, purity 0.0591, x2.1027, p=8.5e-05); gene_family:IGHV (50/101, purity 0.4950, x1.0627, p=0.297521); biotype:protein_coding (133/257, purity 0.5175, x1.0227, p=0.34119) |
| 4 | 8 | 0.8571 | gene_id:ENSG00000211930.1 (1/8, purity 0.1250, x72.375, p=0.013817); gene_symbol:IGHD3-3 (2/8, purity 0.2500, x72.375, p=0.000167); biotype:IG_D_gene (8/8, purity 1.0000, x26.3182, p=0.0) |
| 3 | 12 | 0.5152 | gene_id:ENSG00000282797.1 (1/12, purity 0.0833, x48.25, p=0.020725); gene_symbol:IGHJ6 (2/12, purity 0.1667, x48.25, p=0.000394); biotype:IG_J_gene (12/12, purity 1.0000, x24.125, p=0.0) |
| 2 | 60 | 0.2774 | gene_id:ENSG00000282811.1 (2/60, purity 0.0333, x9.65, p=0.010578); gene_symbol:IGKV1-33 (3/59, purity 0.0508, x9.65, p=0.001063); gene_family:IGKV (51/58, purity 0.8793, x6.9317, p=0.0); biotype:IG_V_gene (59/60, purity 0.9833, x2.4541, p=0.0) |

### protein_vector

- Target: `protein_sequence_window`
- Recipe: `text_style_vector_neighbors`
- Relation rows: `{'vector_neighbor': 37371}`

| Community | Size | Density | Dominant labels |
|---:|---:|---:|---|
| 6 | 43 | 0.1019 | gene_symbol:MGF (3/43, purity 0.0698, x45.75, p=1.6e-05) |
| 12 | 6 | 0.8000 | gene_symbol:BA71V-020 (1/5, purity 0.2000, x437.1667, p=0.002287) |
| 11 | 7 | 1.0000 | gene_symbol:CLB_1293 (1/7, purity 0.1429, x374.7143, p=0.002669) |
| 9 | 8 | 0.9286 | gene_symbol:BruAb2_0497 (1/8, purity 0.1250, x327.875, p=0.00305) |
| 10 | 8 | 0.7143 | gene_symbol:RPR_06885 (1/8, purity 0.1250, x327.875, p=0.00305) |
| 7 | 19 | 0.4678 | gene_symbol:SaurJH1_2414 (1/18, purity 0.0556, x138.0526, p=0.007244) |
| 5 | 47 | 0.0999 | gene_symbol:IIV3-119R (1/3, purity 0.3333, x55.8085, p=0.017918) |
| 2 | 306 | 0.0353 | gene_symbol:pgl (51/251, purity 0.2032, x4.4158, p=0.0) |

### protein_blast

- Target: `protein_sequence_window`
- Recipe: `blast_sequence_neighbors`
- Relation rows: `{'blast_neighbor': 10921}`

| Community | Size | Density | Dominant labels |
|---:|---:|---:|---|
| 111 | 3 | 1.0000 | gene_symbol:ygfA (2/3, purity 0.6667, x874.3333, p=1e-06) |
| 112 | 3 | 1.0000 | gene_symbol:Mpg (2/3, purity 0.6667, x874.3333, p=1e-06) |
| 120 | 3 | 1.0000 | gene_symbol:Sh3bp1 (2/3, purity 0.6667, x874.3333, p=1e-06) |
| 105 | 4 | 1.0000 | gene_symbol:SLC3A2 (2/4, purity 0.5000, x655.75, p=2e-06) |
| 99 | 5 | 1.0000 | gene_symbol:kstD (2/3, purity 0.6667, x524.6, p=3e-06) |
| 24 | 28 | 0.2302 | gene_symbol:MGF (3/28, purity 0.1071, x70.2589, p=4e-06) |
| 97 | 6 | 1.0000 | gene_symbol:EAS (2/3, purity 0.6667, x437.1667, p=4e-06) |
| 68 | 10 | 0.6889 | gene_symbol:Htr3b (2/10, purity 0.2000, x262.3, p=1.3e-05) |

### protein_hybrid

- Target: `protein_sequence_window`
- Recipe: `hybrid_vector_blast_neighbors`
- Relation rows: `{'blast_neighbor': 10921, 'vector_neighbor': 37371}`

| Community | Size | Density | Dominant labels |
|---:|---:|---:|---|
| 7 | 19 | 0.4035 | gene_symbol:MGF (2/19, purity 0.1053, x69.0263, p=0.000296) |
| 10 | 9 | 0.9167 | gene_symbol:BruAb2_0497 (1/9, purity 0.1111, x291.4444, p=0.003431) |
| 8 | 15 | 0.8952 | gene_symbol:SSP0561 (1/15, purity 0.0667, x174.8667, p=0.005719) |
| 3 | 513 | 0.0214 | gene_symbol:WNTX10 (1/6, purity 0.1667, x5.1131, p=0.195578) |
| 0 | 851 | 0.0363 | gene_symbol:pgl (23/792, purity 0.0290, x0.7161, p=0.98446) |
| 2 | 519 | 0.0293 | gene_symbol:pgl (71/467, purity 0.1520, x3.6245, p=0.0) |
| 4 | 63 | 0.2622 | gene_symbol:yfbR (42/62, purity 0.6774, x41.6349, p=0.0) |
| 1 | 539 | 0.0280 | gene_symbol:gnd (23/489, purity 0.0470, x3.0251, p=0.0) |

## Interpretation Boundary

- A high-purity vector community is evidence of non-random biological structure in the representation graph, not proof of homology or mechanism.
- A BLAST community supplies alignment-grounded local evidence, but can fragment the global graph.
- Hybrid DRAG is useful because it keeps broad vector reachability while preserving typed BLAST evidence for agents.
