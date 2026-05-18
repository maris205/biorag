# Held-Out Benchmark Leakage Report

- Benchmark: `benchmarks/dna_parent_frag_100.jsonl`
- Index FASTA: `data/heldout/dna_parent_frag_100_controlled20k_index.fasta`
- Tasks: 100
- Index records: 20000
- Held-out accessions: 100
- Stop/go: **GO**

| Check | Count | Rate | Interpretation |
| --- | ---: | ---: | --- |
| Exact held-out parent accession present in index | 0 | 0.000000 | Must be 0 for held-out evaluation |
| Query exact substring present in indexed records | 62 | n/a | Near-duplicate/conserved-fragment warning, not automatic failure |

## Query Substring Warnings

- `dna_sequence_heldout_suffix_0001` (suffix, 125 aa/nt): `ENST00000280612.9`
- `dna_sequence_heldout_suffix_0002` (suffix, 146 aa/nt): `ENST00000940492.1`, `ENST00000940495.1`, `ENST00000652337.1`, `ENST00000900028.1`, `ENST00000900023.1`
- `dna_sequence_heldout_exact_fragment_0003` (exact_fragment, 151 aa/nt): `ENST00000869330.1`, `ENST00000869329.1`, `ENST00000869331.1`, `ENST00000531510.1`, `ENST00000869333.1`
- `dna_sequence_heldout_suffix_0005` (suffix, 103 aa/nt): `ENST00000855996.1`, `ENST00000855999.1`, `ENST00000917799.1`, `ENST00000917800.1`, `ENST00000917801.1`
- `dna_sequence_heldout_suffix_0006` (suffix, 109 aa/nt): `ENST00000905074.1`, `ENST00000905075.1`, `ENST00000447096.1`
- `dna_sequence_heldout_middle_0007` (middle, 159 aa/nt): `ENST00000879830.1`, `ENST00000517551.2`, `ENST00000252512.14`, `ENST00000433566.8`, `ENST00000879833.1`
- `dna_sequence_heldout_prefix_0008` (prefix, 104 aa/nt): `ENST00000862062.1`
- `dna_sequence_heldout_prefix_0010` (prefix, 99 aa/nt): `ENST00000870168.1`, `ENST00000870165.1`, `ENST00000649755.1`, `ENST00000870162.1`, `ENST00000870161.1`
- `dna_sequence_heldout_suffix_0013` (suffix, 97 aa/nt): `ENST00000911265.1`
- `dna_sequence_heldout_prefix_0014` (prefix, 155 aa/nt): `ENST00000963408.1`, `ENST00000435556.8`, `ENST00000963403.1`, `ENST00000963407.1`, `ENST00000869531.1`
- `dna_sequence_heldout_exact_fragment_0015` (exact_fragment, 148 aa/nt): `ENST00000648616.1`, `ENST00000920425.1`, `ENST00000300091.5`, `ENST00000893216.1`, `ENST00000620105.5`
- `dna_sequence_heldout_suffix_0016` (suffix, 121 aa/nt): `ENST00000852226.1`, `ENST00000354955.5`, `ENST00000956462.1`
- `dna_sequence_heldout_suffix_0017` (suffix, 143 aa/nt): `ENST00000937999.1`, `ENST00000378392.6`, `ENST00000378380.4`
- `dna_sequence_heldout_prefix_0019` (prefix, 109 aa/nt): `ENST00000412155.6`, `ENST00000673754.1`, `ENST00000373979.6`, `ENST00000611141.4`, `ENST00000455706.7`
- `dna_sequence_heldout_middle_0020` (middle, 104 aa/nt): `ENST00000906853.1`, `ENST00000906851.1`, `ENST00000906846.1`, `ENST00000963050.1`, `ENST00000906847.1`
- `dna_sequence_heldout_prefix_0022` (prefix, 150 aa/nt): `ENST00000370081.6`, `ENST00000370089.6`, `ENST00000940717.1`
- `dna_sequence_heldout_middle_0024` (middle, 160 aa/nt): `ENST00000899699.1`, `ENST00000899703.1`, `ENST00000899698.1`, `ENST00000953148.1`, `ENST00000357736.9`
- `dna_sequence_heldout_prefix_0025` (prefix, 96 aa/nt): `ENST00000884845.1`, `ENST00000968474.1`, `ENST00000884847.1`, `ENST00000919841.1`, `ENST00000968495.1`
- `dna_sequence_heldout_suffix_0026` (suffix, 152 aa/nt): `ENST00000706588.1`, `ENST00000706582.1`, `ENST00000706584.1`, `ENST00000913925.1`, `ENST00000706592.1`
- `dna_sequence_heldout_middle_0027` (middle, 112 aa/nt): `ENST00000416347.1`, `ENST00000431574.1`, `ENST00000453205.1`, `ENST00000412044.1`
- `dna_sequence_heldout_suffix_0029` (suffix, 108 aa/nt): `ENST00000896523.1`, `ENST00000896527.1`, `ENST00000447402.7`, `ENST00000935723.1`, `ENST00000368868.10`
- `dna_sequence_heldout_middle_0031` (middle, 133 aa/nt): `ENST00000914651.1`, `ENST00000909936.1`, `ENST00000914648.1`, `ENST00000943621.1`, `ENST00000914654.1`
- `dna_sequence_heldout_suffix_0032` (suffix, 116 aa/nt): `ENST00000225550.4`
- `dna_sequence_heldout_prefix_0034` (prefix, 126 aa/nt): `ENST00000928243.1`, `ENST00000928244.1`, `ENST00000867920.1`, `ENST00000392521.7`, `ENST00000261833.11`
- `dna_sequence_heldout_exact_fragment_0035` (exact_fragment, 109 aa/nt): `ENST00000314574.5`, `ENST00000925080.1`, `ENST00000892687.1`, `ENST00000925074.1`, `ENST00000925076.1`
- `dna_sequence_heldout_exact_fragment_0036` (exact_fragment, 111 aa/nt): `ENST00000534880.1`
- `dna_sequence_heldout_suffix_0037` (suffix, 110 aa/nt): `ENST00000913805.1`, `ENST00000913806.1`, `ENST00000913804.1`
- `dna_sequence_heldout_exact_fragment_0038` (exact_fragment, 104 aa/nt): `ENST00000876670.1`, `ENST00000876669.1`, `ENST00000715465.1`, `ENST00000322428.10`, `ENST00000964348.1`
- `dna_sequence_heldout_exact_fragment_0039` (exact_fragment, 134 aa/nt): `ENST00000927422.1`, `ENST00000681891.1`, `ENST00000681449.1`, `ENST00000679478.1`, `ENST00000681300.1`
- `dna_sequence_heldout_exact_fragment_0040` (exact_fragment, 154 aa/nt): `ENST00000326139.7`, `ENST00000409316.5`, `ENST00000463164.1`, `ENST00000337750.9`, `ENST00000409904.7`
- `dna_sequence_heldout_middle_0041` (middle, 159 aa/nt): `ENST00000689459.1`
- `dna_sequence_heldout_exact_fragment_0043` (exact_fragment, 113 aa/nt): `ENST00000674114.2`, `ENST00000691421.1`, `ENST00000691855.1`, `ENST00000420124.4`, `ENST00000673918.2`
- `dna_sequence_heldout_exact_fragment_0044` (exact_fragment, 157 aa/nt): `ENST00000414910.1`, `ENST00000414947.1`, `ENST00000445685.1`, `ENST00000419323.1`, `ENST00000422651.1`
- `dna_sequence_heldout_exact_fragment_0046` (exact_fragment, 146 aa/nt): `ENST00000907822.1`, `ENST00000327674.8`, `ENST00000372563.2`, `ENST00000907821.1`
- `dna_sequence_heldout_exact_fragment_0047` (exact_fragment, 112 aa/nt): `ENST00000699469.1`, `ENST00000709545.1`, `ENST00000699470.1`, `ENST00000709541.1`, `ENST00000709542.1`
- `dna_sequence_heldout_exact_fragment_0048` (exact_fragment, 124 aa/nt): `ENST00000585530.1`, `ENST00000591658.5`, `ENST00000918348.1`, `ENST00000377540.6`
- `dna_sequence_heldout_suffix_0050` (suffix, 156 aa/nt): `ENST00000382461.8`
- `dna_sequence_heldout_prefix_0053` (prefix, 118 aa/nt): `ENST00000511503.1`
- `dna_sequence_heldout_suffix_0054` (suffix, 125 aa/nt): `ENST00000413592.5`, `ENST00000916433.1`, `ENST00000244217.6`
- `dna_sequence_heldout_prefix_0056` (prefix, 126 aa/nt): `ENST00000335351.8`, `ENST00000895008.1`, `ENST00000895007.1`
- `dna_sequence_heldout_prefix_0057` (prefix, 144 aa/nt): `ENST00000854058.1`, `ENST00000431561.7`, `ENST00000577015.1`, `ENST00000396870.8`, `ENST00000928466.1`
- `dna_sequence_heldout_middle_0059` (middle, 108 aa/nt): `ENST00000893377.1`, `ENST00000493055.1`, `ENST00000462551.1`, `ENST00000264093.9`, `ENST00000629438.2`
- `dna_sequence_heldout_prefix_0064` (prefix, 125 aa/nt): `ENST00000403099.5`, `ENST00000886889.1`, `ENST00000954982.1`, `ENST00000451385.6`, `ENST00000407364.8`
- `dna_sequence_heldout_prefix_0069` (prefix, 160 aa/nt): `ENST00000904286.1`, `ENST00000904287.1`, `ENST00000904289.1`
- `dna_sequence_heldout_prefix_0071` (prefix, 102 aa/nt): `ENST00000920866.1`, `ENST00000920865.1`, `ENST00000920867.1`, `ENST00000370952.4`
- `dna_sequence_heldout_middle_0072` (middle, 125 aa/nt): `ENST00000205194.5`, `ENST00000962965.1`, `ENST00000898441.1`
- `dna_sequence_heldout_exact_fragment_0074` (exact_fragment, 98 aa/nt): `ENST00000441020.7`, `ENST00000450366.7`, `ENST00000448951.6`, `ENST00000853654.1`, `ENST00000443314.5`
- `dna_sequence_heldout_middle_0075` (middle, 114 aa/nt): `ENST00000857631.1`, `ENST00000857633.1`, `ENST00000455891.5`, `ENST00000857638.1`, `ENST00000915985.1`
- `dna_sequence_heldout_middle_0076` (middle, 147 aa/nt): `ENST00000529960.5`
- `dna_sequence_heldout_middle_0077` (middle, 122 aa/nt): `ENST00000446294.6`, `ENST00000920638.1`, `ENST00000920637.1`, `ENST00000447165.6`, `ENST00000875803.1`

