# Held-Out Benchmark Leakage Report

- Benchmark: `benchmarks/protein_parent_frag_500_window_target.jsonl`
- Index FASTA: `data/heldout/protein_parent_frag_500_controlled20k_index.fasta`
- Tasks: 500
- Index records: 20000
- Held-out accessions: 500
- Stop/go: **GO**

| Check | Count | Rate | Interpretation |
| --- | ---: | ---: | --- |
| Exact held-out parent accession present in index | 0 | 0.000000 | Must be 0 for held-out evaluation |
| Query exact substring present in indexed records | 69 | n/a | Near-duplicate/conserved-fragment warning, not automatic failure |

## Query Substring Warnings

- `protein_sequence_heldout_prefix_0004` (prefix, 105 aa/nt): `B8AX51`
- `protein_sequence_heldout_suffix_0020` (suffix, 96 aa/nt): `Q96EK5`
- `protein_sequence_heldout_middle_0021` (middle, 73 aa/nt): `P68971`
- `protein_sequence_heldout_middle_0023` (middle, 64 aa/nt): `Q5E992`, `Q9D0W5`
- `protein_sequence_heldout_suffix_0034` (suffix, 115 aa/nt): `A2XLM6`
- `protein_sequence_heldout_suffix_0040` (suffix, 74 aa/nt): `P28074`
- `protein_sequence_heldout_prefix_0054` (prefix, 87 aa/nt): `P0ACT2`
- `protein_sequence_heldout_middle_0063` (middle, 68 aa/nt): `B9KIJ7`
- `protein_sequence_heldout_exact_fragment_0064` (exact_fragment, 114 aa/nt): `Q9XH35`
- `protein_sequence_heldout_exact_fragment_0066` (exact_fragment, 121 aa/nt): `P9WIU2`, `A5U287`, `P0A5M7`, `A1KIH4`, `P9WIU3`
- `protein_sequence_heldout_exact_fragment_0067` (exact_fragment, 122 aa/nt): `Q9BGT1`
- `protein_sequence_heldout_middle_0094` (middle, 97 aa/nt): `Q62084`
- `protein_sequence_heldout_middle_0095` (middle, 124 aa/nt): `P0CL68`
- `protein_sequence_heldout_suffix_0098` (suffix, 126 aa/nt): `P9WGB0`
- `protein_sequence_heldout_prefix_0115` (prefix, 125 aa/nt): `P65592`
- `protein_sequence_heldout_prefix_0141` (prefix, 123 aa/nt): `Q943K1`
- `protein_sequence_heldout_exact_fragment_0144` (exact_fragment, 79 aa/nt): `Q0P5I6`, `Q8NAV1`, `Q8HXH6`
- `protein_sequence_heldout_suffix_0149` (suffix, 93 aa/nt): `Q0HNT9`, `Q8EK70`, `A9KWA0`, `Q0I0A7`
- `protein_sequence_heldout_middle_0153` (middle, 116 aa/nt): `Q31T09`
- `protein_sequence_heldout_middle_0155` (middle, 82 aa/nt): `Q9H672`, `Q9BGT9`, `Q91ZU0`
- `protein_sequence_heldout_exact_fragment_0168` (exact_fragment, 79 aa/nt): `P9WHY3`
- `protein_sequence_heldout_suffix_0169` (suffix, 126 aa/nt): `Q8ILG2`
- `protein_sequence_heldout_suffix_0172` (suffix, 74 aa/nt): `P67095`, `P67097`
- `protein_sequence_heldout_exact_fragment_0175` (exact_fragment, 105 aa/nt): `P0A2X3`
- `protein_sequence_heldout_exact_fragment_0180` (exact_fragment, 116 aa/nt): `P9WNB8`, `P64159`
- `protein_sequence_heldout_prefix_0204` (prefix, 87 aa/nt): `P53099`
- `protein_sequence_heldout_exact_fragment_0244` (exact_fragment, 126 aa/nt): `A4IWL0`, `Q14G67`
- `protein_sequence_heldout_prefix_0249` (prefix, 119 aa/nt): `P9WMG5`
- `protein_sequence_heldout_suffix_0254` (suffix, 71 aa/nt): `O08584`, `O35819`
- `protein_sequence_heldout_prefix_0263` (prefix, 68 aa/nt): `Q6YIA3`, `P0CX29`
- `protein_sequence_heldout_prefix_0273` (prefix, 119 aa/nt): `Q92624`, `A5HK05`
- `protein_sequence_heldout_exact_fragment_0274` (exact_fragment, 100 aa/nt): `Q9JIR4`
- `protein_sequence_heldout_prefix_0284` (prefix, 85 aa/nt): `P64686`, `P9WM66`
- `protein_sequence_heldout_suffix_0285` (suffix, 78 aa/nt): `Q9Y5Q6`
- `protein_sequence_heldout_exact_fragment_0294` (exact_fragment, 76 aa/nt): `P58409`
- `protein_sequence_heldout_middle_0296` (middle, 85 aa/nt): `P0ADU9`, `P0ADU7`, `P0ADV0`
- `protein_sequence_heldout_middle_0305` (middle, 121 aa/nt): `Q8BGR2`
- `protein_sequence_heldout_middle_0306` (middle, 115 aa/nt): `P0A8A6`, `P0A8A7`, `B1LE27`, `B7MAR4`, `B7L6H6`
- `protein_sequence_heldout_middle_0311` (middle, 68 aa/nt): `P68137`, `P68134`, `P68133`, `Q90X97`, `P68135`
- `protein_sequence_heldout_middle_0314` (middle, 123 aa/nt): `Q56A27`
- `protein_sequence_heldout_prefix_0318` (prefix, 101 aa/nt): `P9WHZ8`
- `protein_sequence_heldout_exact_fragment_0329` (exact_fragment, 73 aa/nt): `Q5R4B8`, `P36860`, `P11234`
- `protein_sequence_heldout_prefix_0338` (prefix, 119 aa/nt): `P9WI21`
- `protein_sequence_heldout_middle_0346` (middle, 85 aa/nt): `P07893`
- `protein_sequence_heldout_suffix_0347` (suffix, 123 aa/nt): `A2Y931`
- `protein_sequence_heldout_suffix_0349` (suffix, 124 aa/nt): `B5F6R9`, `B5QZT8`, `B5REL6`, `C0PZ34`, `B4TWC0`
- `protein_sequence_heldout_middle_0353` (middle, 67 aa/nt): `A0A482ASA5`
- `protein_sequence_heldout_middle_0355` (middle, 128 aa/nt): `Q4FZV3`, `Q4R3K5`
- `protein_sequence_heldout_suffix_0364` (suffix, 87 aa/nt): `Q02XA5`
- `protein_sequence_heldout_suffix_0367` (suffix, 124 aa/nt): `Q8BZM0`

