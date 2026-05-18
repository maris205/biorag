# DNA Held-Out Parent-Fragment Results

Benchmark: `benchmarks/dna_parent_frag_100.jsonl`. Exact held-out transcript accessions are excluded. Biological matching uses shared `gene_symbol` labels.

| Setting | Route | Tasks | Bio Hit@10 | Bio MRR | Avg latency ms |
|---|---|---:|---:|---:|---:|
| BLASTN controlled20k | blast | 100 | 0.9100 | 0.9100 | 94.7 |
| OmniGene BF16 mean controlled20k 20k windows | vector | 100 | 0.1000 | 0.0795 | 1049.0 |
| Nucleotide Transformer 500M mean full controlled20k windows | vector | 100 | 0.0100 | 0.0021 | 992.5 |
| Nucleotide Transformer 500M CLS controlled20k 20k-window smoke | vector | 100 | 0.0300 | 0.0090 | 896.3 |
| BLASTN full cDNA held-out | blast | 100 | 0.9100 | 0.9100 | 328.3 |
| OmniGene BF16 mean sequential 20k windows | vector | 100 | 0.0000 | 0.0000 | 1015.1 |

Interpretation:
- BLASTN remains the alignment-grounded reference for DNA/cDNA fragments.
- The sequential 20k vector subset is not interpretable because many same-gene candidates are absent.
- The controlled20k subset includes same-gene non-parent candidates for all 100 tasks, but OmniGene BF16 mean remains weak on this DNA-only transcript retrieval task.
- Off-the-shelf Nucleotide Transformer 500M pooling did not improve this cDNA transcript-fragment retrieval task. Mean pooling on the full controlled20k window index reached only 0.0100/0.0021 Bio Hit@10/MRR; CLS pooling in a 20k-window smoke run reached 0.0300/0.0090.
- DNABERT-2 was attempted but is blocked in the current environment by custom-model compatibility issues under the installed Transformers/Torch stack; rerun in a pinned Transformers 4.x environment before treating it as a missing scientific baseline.
- This supports the model-agnostic BioRAG framing: DNA partitions need retrieval-specific DNA encoders, fine-tuning, or alignment verification rather than assuming that any genomic foundation model is a strong dense retriever out of the box. OmniGene remains useful for unified biological-language/agent contexts, not as the current strongest DNA-only retriever.
