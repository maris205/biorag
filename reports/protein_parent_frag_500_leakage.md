# Held-Out Benchmark Leakage Report

- Benchmark: `benchmarks/protein_parent_frag_500.jsonl`
- Index FASTA: `data/heldout/protein_parent_frag_500_index.fasta`
- Tasks: 500
- Index records: 483581
- Held-out accessions: 500
- Stop/go: **GO**

| Check | Count | Rate | Interpretation |
| --- | ---: | ---: | --- |
| Exact held-out parent accession present in index | 0 | 0.000000 | Must be 0 for held-out evaluation |
| Query exact substring present in indexed records | 74 | n/a | Near-duplicate/conserved-fragment warning, not automatic failure |

## Query Substring Warnings

- `protein_sequence_heldout_prefix_0004` (prefix, 105 aa/nt): `B8AX51`
- `protein_sequence_heldout_suffix_0020` (suffix, 96 aa/nt): `Q96EK5`
- `protein_sequence_heldout_middle_0021` (middle, 73 aa/nt): `P68971`
- `protein_sequence_heldout_middle_0023` (middle, 64 aa/nt): `Q5E992`, `Q9D0W5`
- `protein_sequence_heldout_suffix_0034` (suffix, 115 aa/nt): `A2XLM6`
- `protein_sequence_heldout_suffix_0040` (suffix, 74 aa/nt): `P28074`
- `protein_sequence_heldout_prefix_0053` (prefix, 81 aa/nt): `Q6LCW8`, `P50564`
- `protein_sequence_heldout_prefix_0054` (prefix, 87 aa/nt): `P0ACT2`
- `protein_sequence_heldout_middle_0063` (middle, 68 aa/nt): `B9KIJ7`, `B9KJ19`, `Q5PAA7`
- `protein_sequence_heldout_exact_fragment_0064` (exact_fragment, 114 aa/nt): `Q9XH35`
- `protein_sequence_heldout_exact_fragment_0066` (exact_fragment, 121 aa/nt): `P0A5M7`, `A1KIH4`, `A5U287`, `P9WIU2`, `P9WIU3`
- `protein_sequence_heldout_exact_fragment_0067` (exact_fragment, 122 aa/nt): `Q9BGT1`
- `protein_sequence_heldout_middle_0094` (middle, 97 aa/nt): `Q62084`
- `protein_sequence_heldout_middle_0095` (middle, 124 aa/nt): `P0CL68`
- `protein_sequence_heldout_suffix_0098` (suffix, 126 aa/nt): `P9WGB0`
- `protein_sequence_heldout_prefix_0110` (prefix, 99 aa/nt): `O64219`
- `protein_sequence_heldout_prefix_0115` (prefix, 125 aa/nt): `P65592`
- `protein_sequence_heldout_prefix_0141` (prefix, 123 aa/nt): `Q943K1`
- `protein_sequence_heldout_exact_fragment_0144` (exact_fragment, 79 aa/nt): `Q0P5I6`, `Q8NAV1`, `Q8HXH6`
- `protein_sequence_heldout_suffix_0149` (suffix, 93 aa/nt): `A3DA74`, `A9KW88`, `A9KWA0`, `Q8EK70`, `Q0HNT9`
- `protein_sequence_heldout_middle_0153` (middle, 116 aa/nt): `Q31T09`
- `protein_sequence_heldout_middle_0155` (middle, 82 aa/nt): `Q9H672`, `Q9BGT9`, `Q91ZU0`
- `protein_sequence_heldout_exact_fragment_0168` (exact_fragment, 79 aa/nt): `P9WHY3`
- `protein_sequence_heldout_suffix_0169` (suffix, 126 aa/nt): `Q8ILG2`
- `protein_sequence_heldout_suffix_0172` (suffix, 74 aa/nt): `P67097`, `P67095`
- `protein_sequence_heldout_exact_fragment_0175` (exact_fragment, 105 aa/nt): `P0A2X3`
- `protein_sequence_heldout_exact_fragment_0180` (exact_fragment, 116 aa/nt): `P64159`, `P9WNB8`
- `protein_sequence_heldout_prefix_0204` (prefix, 87 aa/nt): `P53099`
- `protein_sequence_heldout_prefix_0216` (prefix, 96 aa/nt): `P68143`, `O42161`
- `protein_sequence_heldout_exact_fragment_0244` (exact_fragment, 126 aa/nt): `Q14G67`, `A4IWL0`
- `protein_sequence_heldout_prefix_0249` (prefix, 119 aa/nt): `P9WMG5`, `P67742`
- `protein_sequence_heldout_suffix_0254` (suffix, 71 aa/nt): `O08584`, `O35819`
- `protein_sequence_heldout_suffix_0257` (suffix, 88 aa/nt): `P0CX32`
- `protein_sequence_heldout_prefix_0263` (prefix, 68 aa/nt): `P0CX29`, `P0CY40`, `P0CX30`, `Q6FLA8`, `Q6YIA3`
- `protein_sequence_heldout_prefix_0273` (prefix, 119 aa/nt): `Q92624`, `A5HK05`
- `protein_sequence_heldout_exact_fragment_0274` (exact_fragment, 100 aa/nt): `Q9JIR4`
- `protein_sequence_heldout_prefix_0284` (prefix, 85 aa/nt): `P64686`, `P9WM66`
- `protein_sequence_heldout_suffix_0285` (suffix, 78 aa/nt): `Q9Y5Q6`
- `protein_sequence_heldout_exact_fragment_0294` (exact_fragment, 76 aa/nt): `P58409`
- `protein_sequence_heldout_middle_0296` (middle, 85 aa/nt): `P0ADU9`, `P0ADU7`, `P0ADV0`
- `protein_sequence_heldout_middle_0305` (middle, 121 aa/nt): `Q8BGR2`
- `protein_sequence_heldout_middle_0306` (middle, 115 aa/nt): `A7ZMH0`, `B7US42`, `B7MAR4`, `B7L6H6`, `P0A8A6`
- `protein_sequence_heldout_middle_0311` (middle, 68 aa/nt): `P10995`, `P20399`, `P62739`, `P62736`, `P62737`
- `protein_sequence_heldout_middle_0314` (middle, 123 aa/nt): `Q56A27`
- `protein_sequence_heldout_prefix_0318` (prefix, 101 aa/nt): `P9WHZ8`
- `protein_sequence_heldout_exact_fragment_0329` (exact_fragment, 73 aa/nt): `P11234`, `Q5R4B8`, `P36860`
- `protein_sequence_heldout_prefix_0338` (prefix, 119 aa/nt): `P9WI21`
- `protein_sequence_heldout_middle_0346` (middle, 85 aa/nt): `P07893`
- `protein_sequence_heldout_suffix_0347` (suffix, 123 aa/nt): `A2Y931`
- `protein_sequence_heldout_suffix_0349` (suffix, 124 aa/nt): `B5F6R9`, `Q57JJ9`, `B5FHZ4`, `B5QZT8`, `B5REL6`

