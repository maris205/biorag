# Experiment Tracker

| Run ID | Milestone | Purpose | System / Variant | Split | Metrics | Priority | Status | Notes |
|--------|-----------|---------|------------------|-------|---------|----------|--------|-------|
| R001 | M0 | DNA header parsing | Ensembl cDNA metadata extraction | local | gene_symbol coverage | MUST | DONE | 100/100 DNA held-out queries have gene_symbol |
| R002 | M0 | DNA held-out split | Ensembl cDNA parent-fragment 100 | held-out transcript | leakage, label coverage | MUST | DONE | `benchmarks/dna_parent_frag_100.jsonl` |
| R003 | M0 | DNA BLAST DB | held-out cDNA index | held-out transcript | build status | MUST | DONE | `data/heldout/blast/dna_parent_frag_100_index` |
| R004 | M1 | DNA alignment baseline | BLASTN controlled20k | DNA held-out 100 | Bio Hit@10 0.91, Bio MRR 0.91 | MUST | DONE | `reports/dna_parent_frag_100_controlled20k_blast_eval.json` |
| R005 | M1 | DNA dense baseline | OmniGene mean Chroma | DNA held-out 100 | Bio Hit@10 0.10, Bio MRR 0.0795 | MUST | DONE | controlled20k 20k-window gate |
| R006 | M1 | DNA public dense baseline | DNABERT-2 or Nucleotide Transformer | DNA held-out 100 | Bio Hit@10, Bio MRR | SHOULD | TODO | depends on model download/load |
| R007 | M2 | Candidate verification curve | vector top-N + candidate BLAST | sequence-window 100 | Bio Hit@10 0.9192 at N=200 | MUST | DONE | `reports/vector_candidate_budget_sweep_100query_eval.json` |
| R008 | M3 | Lookup/verified latency | Chroma/FAISS CPU if available | 100k/300k/full | lookup-only, verified latency | MUST | TODO | GPU optional |
| R009 | M4 | Parent-collapsed DRAG | vector/blast/hybrid graphs | 10k views | purity/enrichment | MUST | TODO | collapse transcript/window parents |
| R010 | M4 | DRAG null controls | k-mer NN + degree-preserving null | 10k views | empirical p/z score | MUST | TODO | main 2Q biology gate |
| R011 | M5 | Paper integration | LaTeX tables/figures | paper | compile PDF | MUST | TODO | after R004-R010 |
