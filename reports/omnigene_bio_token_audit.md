# OmniGene Biological Token Activation Audit

## Result

The tokenizer contains a biological BPE vocabulary, but the current raw sequence input path does not activate it.
This audit distinguishes vocabulary presence from runtime or CPT-data use; it does not evaluate model quality.

| Check | DNA | Protein |
|---|---:|---:|
| Added BPE entries | 19,994 | 7,974 |
| Raw-input biological token hits | 0 | 0 |
| Raw-input token fraction | 0.000000 | 0.000000 |
| Raw-input residues/token | 2.270 | 1.932 |
| Intended standalone BPE residues/token | 5.997 | 2.633 |

## CPT Binary Sample

| Part | Sampled uint32 values | DNA BPE IDs | Protein BPE IDs | Max value |
|---|---:|---:|---:|---:|
| `part_dna.bin` | 10,000,000 | 0 | 0 | 236823 |
| `part_prot1.bin` | 10,000,000 | 0 | 0 | 236935 |
| `part_prot2.bin` | 10,000,000 | 0 | 0 | 236953 |

## Interpretation

- The added entries are literal prefixed tokens (`▶...` for DNA and `◆...` for protein). Plain sequences do not contain those prefixes.
- The inspected CPT preprocessing code sends plain sequence strings directly to the merged tokenizer.
- The sampled DNA and protein CPT binary parts contain no DNA/protein BPE token IDs.
- Consequently, current token-semantic analysis must label the standalone BPE segmentation as an intended/frequency-derived vocabulary, not a CPT-learned token representation.
- A corrected model experiment needs a modality-aware pretokenization step followed by CPT; merely prefixing a whole sequence is insufficient.

## Safe Paper Claim

Current BioRAG results demonstrate sequence CPT through the base tokenizer, but do not yet isolate a gain or biological semantics from the expanded BPE entries.
