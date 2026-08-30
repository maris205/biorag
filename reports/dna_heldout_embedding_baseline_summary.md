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
- DNABERT-2 is now loaded through an explicit compatibility backend using its official custom `BertConfig`/`BertModel` classes. With the full checkpoint preserved, mean pooling reaches `0.2500/0.2347` with 256/128 windows and `0.1700/0.1481` with 128/64 windows, while last pooling reaches only `0.0200/0.0171`.
- This supports the model-agnostic BioRAG framing: DNA partitions need retrieval-specific DNA encoders, fine-tuning, or alignment verification rather than assuming that any genomic foundation model is a strong dense retriever out of the box. OmniGene remains useful for unified biological-language/agent contexts, not as the current strongest DNA-only retriever.

## Completed Matrix

The controlled matrix has now been run for DNABERT-S, DNABERT-2, and the
quantized OmniGene control. The primary comparison rows use 100 queries, 20k
windows, and top-200 parent collapse; the DNABERT-2 window/strand rows are
explicit ablations:

| Model | Pooling | Bio Hit@10 | Bio MRR | Query embed ms | Lookup ms | E2E ms | Peak GiB |
|---|---|---:|---:|---:|---:|---:|---:|
| DNABERT-2 117M | mean, 256/128 | **0.2500** | **0.2347** | 0.6 | 10.38 | 10.9 | 0.67 |
| DNABERT-2 117M | mean, 128/64 | **0.1700** | **0.1481** | 0.5 | 6.90 | 7.4 | 0.56 |
| DNABERT-2 117M | mean + RC average, 128/64 | 0.1500 | 0.1438 | 1.2 | 12.67 | 13.8 | 0.56 |
| DNABERT-S | mean + RC average | 0.1200 | 0.1090 | n/r | n/r | n/r | n/r |
| DNABERT-S | mean | 0.1200 | 0.1020 | 0.6 | 12.06 | 12.6 | 0.57 |
| OmniGene-4-CPT 4-bit | mean | 0.0900 | 0.0688 | 324.7 | 16.60 | 341.3 | 27.75 |
| DNABERT-S | last | 0.0300 | 0.0244 | n/r | n/r | n/r | n/r |
| DNABERT-2 117M | last | 0.0200 | 0.0171 | 0.5 | 11.41 | 11.9 | 0.56 |

The generated detailed report is `reports/dna_embedding_matrix.md` and the
machine-readable runs are under `reports/results/`.

The evaluation runner is in `scripts/eval_dna_embedding_matrix.py` and
`docs/DNA_EMBEDDING_EVALUATION_PLAN.md`. It keeps the held-out parent split and
controlled20k index fixed while comparing DNABERT-S, DNABERT-2, Nucleotide
Transformer v2, and OmniGene across mean/last/CLS pooling, 128/64 versus
256/128 windows, and forward-only versus forward/reverse-complement averaging.
The runner reports exact-parent and gene-level metrics separately, plus query
embedding, lookup-only, warm end-to-end latency, and peak GPU memory. The
current matrix is sufficient to select DNABERT-2 mean with 256/128 windows as
the primary DNA dense encoder for the next hybrid retrieval experiment.

The matrix also includes `dnagpt/OmniGene-4-CPT-v2-4bit` as a deployable
unified-backbone control. It was compared on both retrieval quality and cost,
but is not expected to beat DNA-specialized encoders on DNA-only retrieval.
Full BF16 OmniGene remains excluded from the 32 GB deployment run.

## Quantized OmniGene Result

The 4-bit OmniGene run completed on an RTX 4080 SUPER 32 GB GPU using the same
100-query, 20k-window controlled evaluation:

| Setting | Bio Hit@10 | Bio MRR | Query embedding ms | Lookup ms | E2E ms | Peak GiB |
|---|---:|---:|---:|---:|---:|---:|
| OmniGene BF16 mean | 0.1000 | 0.0795 | n/r | n/r | 1049.0* | n/r |
| OmniGene 4-bit mean | 0.0900 | 0.0688 | 324.7 | 16.6 | 341.3 | 27.75 |

\* The BF16 number comes from the earlier Chroma-based evaluator and is not a
strict latency comparison with the direct matrix lookup runner. The quality
comparison uses the same held-out query/index protocol and top-200 parent
collapse. Query-type Bio Hit@10 for 4-bit OmniGene was 0.10 on exact fragments,
0.05 on middle fragments, 0.10 on mutated fragments, 0.10 on prefixes, and
0.10 on suffixes.

The result supports using quantized OmniGene as a low-memory unified
sequence/text deployment control, but not as evidence that it is the best
DNA-specific encoder. The artifact is
`reports/results/dna_omnigene_4bit_mean20k.json`.
