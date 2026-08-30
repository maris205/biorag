# Sequence Token Biological-Semantics Pilot

## Scope

This is an exploratory association analysis over parent-level Swiss-Prot proteins. A token is not assumed to be a motif, and a statistically associated edge is not curated biological evidence.
The intended OmniGene protein BPE vocabulary is analyzed independently of the current merged tokenizer activation issue documented in `reports/omnigene_bio_token_audit.md`.

## Controlled Comparison

| Tokenization | Eligible tokens | GO terms | Significant token-GO pairs | Significant tokens | Null mean/max | Empirical p |
|---|---:|---:|---:|---:|---:|---:|
| intended_protein_bpe | 4,342 | 46 | 15 | 13 | 0.12/2 | 0.0099 |
| current_runtime_tokens | 1,465 | 46 | 15 | 14 | 0.09/2 | 0.0099 |
| overlapping_fixed_3mer | 7,915 | 46 | 57 | 53 | 0.06/2 | 0.0099 |

## Top Intended-BPE Associations

| Token | Length | GO term | Support | Token df | GO df | Odds ratio | q |
|---|---:|---|---:|---:|---:|---:|---:|
| `HRD` | 3 | GO:0004674 protein serine/threonine kinase activity | 11 | 37 | 31 | 41.14 | 2.27e-07 |
| `KK` | 2 | GO:0003723 RNA binding | 81 | 880 | 110 | 3.77 | 8.97e-06 |
| `WFQ` | 3 | GO:0001228 DNA-binding transcription activator activity, RNA polymerase II-specific | 9 | 32 | 30 | 36.62 | 1.55e-05 |
| `WFQ` | 3 | GO:1990837 sequence-specific double-stranded DNA binding | 9 | 32 | 31 | 34.97 | 1.62e-05 |
| `MEY` | 3 | GO:0004674 protein serine/threonine kinase activity | 8 | 23 | 31 | 45.61 | 2.11e-05 |
| `ELL` | 3 | GO:0004674 protein serine/threonine kinase activity | 18 | 310 | 31 | 7.86 | 1.69e-03 |
| `IGKG` | 4 | GO:0004674 protein serine/threonine kinase activity | 5 | 10 | 31 | 74.13 | 4.36e-03 |
| `TGEK` | 4 | GO:0000978 RNA polymerase II cis-regulatory region sequence-specific DNA binding | 7 | 26 | 37 | 24.52 | 5.23e-03 |
| `TGEK` | 4 | GO:0000122 negative regulation of transcription by RNA polymerase II | 5 | 26 | 14 | 52.93 | 1.02e-02 |
| `DKK` | 3 | GO:0003723 RNA binding | 16 | 74 | 110 | 5.47 | 2.21e-02 |
| `LKP` | 3 | GO:0004674 protein serine/threonine kinase activity | 10 | 105 | 31 | 9.59 | 2.90e-02 |
| `GGP` | 3 | GO:1990837 sequence-specific double-stranded DNA binding | 11 | 132 | 31 | 8.53 | 2.90e-02 |
| `KQ` | 2 | GO:0003723 RNA binding | 59 | 649 | 110 | 2.54 | 2.90e-02 |
| `FGV` | 3 | GO:0004674 protein serine/threonine kinase activity | 9 | 83 | 31 | 10.74 | 3.23e-02 |
| `EI` | 2 | GO:0004674 protein serine/threonine kinase activity | 24 | 725 | 31 | 5.91 | 3.95e-02 |

## Interpretation Boundary

- A positive result means token occurrence is associated with curated GO labels more often than expected after length-stratified label permutation.
- It does not show that a token is a known motif, that the association is independent of homology, or that CPT learned the token semantics.
- The fixed 3-mer and current runtime-token conditions indicate how much of the signal can be explained by ordinary local sequence composition.
- Paper-grade motif claims require PROSITE/Pfam coordinate overlap and a UniRef50 family-held-out control.
