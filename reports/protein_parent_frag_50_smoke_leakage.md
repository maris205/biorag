# Held-Out Benchmark Leakage Report

- Benchmark: `benchmarks/protein_parent_frag_50_smoke.jsonl`
- Index FASTA: `data/heldout/protein_parent_frag_50_smoke_index.fasta`
- Tasks: 50
- Index records: 484031
- Held-out accessions: 50
- Stop/go: **GO**

| Check | Count | Rate | Interpretation |
| --- | ---: | ---: | --- |
| Exact held-out parent accession present in index | 0 | 0.000000 | Must be 0 for held-out evaluation |
| Query exact substring present in indexed records | 5 | n/a | Near-duplicate/conserved-fragment warning, not automatic failure |

## Query Substring Warnings

- `protein_sequence_heldout_exact_fragment_0004` (exact_fragment, 122 aa/nt): `B8AX51`
- `protein_sequence_heldout_exact_fragment_0021` (exact_fragment, 114 aa/nt): `P68971`
- `protein_sequence_heldout_suffix_0023` (suffix, 88 aa/nt): `Q5E992`
- `protein_sequence_heldout_suffix_0040` (suffix, 111 aa/nt): `P28074`
- `protein_sequence_heldout_middle_0048` (middle, 116 aa/nt): `Q9NYS7`, `O54929`

