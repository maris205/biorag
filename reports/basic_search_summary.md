# Basic Search Evaluation

Benchmark: `benchmarks/basic_search.jsonl`

Date: 2026-05-15 UTC

Tasks: 12

- 5 gene lookup tasks
- 3 pathway lookup tasks
- 2 protein sequence tasks
- 2 DNA/cDNA sequence tasks

## Conditions

| Condition | Routes |
| --- | --- |
| `fts` | SQLite FTS |
| `blast` | Swiss-Prot BLASTP + Ensembl cDNA BLASTN |
| `classical` | FTS + BLAST |
| `vector` | OmniGene GGUF embeddings + Chroma |
| `drag` | FTS + graph expansion |
| `hybrid` | FTS + BLAST + graph + vector |

## Summary

| Condition | Hit@1 | Hit@5 | Hit@10 | MRR | Avg latency ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `fts` | 0.6667 | 0.6667 | 0.6667 | 0.6667 | 78.128 |
| `blast` | 0.2500 | 0.3333 | 0.3333 | 0.2917 | 356.531 |
| `classical` | 0.9167 | 1.0000 | 1.0000 | 0.9583 | 419.446 |
| `vector` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1482.673 |
| `drag` | 0.6667 | 0.6667 | 0.6667 | 0.6667 | 4049.735 |
| `hybrid` | 0.9167 | 1.0000 | 1.0000 | 0.9583 | 5592.487 |

## By Category

| Condition | Category | Hit@10 | MRR |
| --- | --- | ---: | ---: |
| `fts` | gene_lookup | 5/5 | 1.0000 |
| `fts` | pathway_lookup | 3/3 | 1.0000 |
| `fts` | protein_sequence | 0/2 | 0.0000 |
| `fts` | dna_sequence | 0/2 | 0.0000 |
| `blast` | gene_lookup | 0/5 | 0.0000 |
| `blast` | pathway_lookup | 0/3 | 0.0000 |
| `blast` | protein_sequence | 2/2 | 1.0000 |
| `blast` | dna_sequence | 2/2 | 0.7500 |
| `classical` | gene_lookup | 5/5 | 1.0000 |
| `classical` | pathway_lookup | 3/3 | 1.0000 |
| `classical` | protein_sequence | 2/2 | 1.0000 |
| `classical` | dna_sequence | 2/2 | 0.7500 |
| `drag` | gene_lookup | 5/5 | 1.0000 |
| `drag` | pathway_lookup | 3/3 | 1.0000 |
| `drag` | protein_sequence | 0/2 | 0.0000 |
| `drag` | dna_sequence | 0/2 | 0.0000 |
| `vector` | all categories | 0/12 | 0.0000 |
| `hybrid` | gene_lookup | 5/5 | 1.0000 |
| `hybrid` | pathway_lookup | 3/3 | 1.0000 |
| `hybrid` | protein_sequence | 2/2 | 1.0000 |
| `hybrid` | dna_sequence | 2/2 | 0.7500 |

## Notes

- Classical retrieval is the strongest baseline on exact-ID tasks after adding Ensembl cDNA BLASTN.
- Hybrid matches classical recall but is slower because routes run serially and graph/vector are not gated.
- Vector-only currently fails this exact-ID benchmark. The returned neighbors are semantically plausible in some cases, but they do not recover the known entity/accession within top 10.
- The next retrieval iteration should add route gating and separate vector evaluation tasks for semantic neighbor quality, not only exact-ID lookup.

Full machine-readable results: `reports/basic_search_eval.json`.
