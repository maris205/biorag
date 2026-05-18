# BioRAG-Standard v0 Dataset

Date: 2026-05-15

Purpose: turn the Open-Rosalind Standard data plus sequence/vector extensions
into a reusable annotated BioRAG dataset. This gives the paper a clear data
contribution in addition to the retrieval and DRAG method.

## Build Command

```bash
python scripts/build_biorag_dataset.py \
  --config configs/standard.yaml \
  --output data/biorag_standard_v0 \
  --reset \
  --standard-limit 0 \
  --chroma-targets protein_sequence_window,dna_sequence_window,mixed \
  --chroma-limit 0 \
  --tasks benchmarks/basic_search.jsonl,benchmarks/sequence_search_100_seed20260516_bio.jsonl \
  --task-split-policy all_test
```

Schema: `data/biorag_standard_v0/SCHEMA.md`

Manifest: `data/biorag_standard_v0/manifest.json`

## Dataset Layout

```text
data/biorag_standard_v0/
  manifest.json
  SCHEMA.md
  corpus/
    standard_text.jsonl
    protein_sequence_window.jsonl
    dna_sequence_window.jsonl
    mixed.jsonl
  tasks/
    rag_tasks.jsonl
```

## Corpus Partitions

| Corpus file | Records | Partitions / source |
| --- | ---: | --- |
| `standard_text.jsonl` | 57,856 | HGNC genes 44,986; GO terms 5,000; Reactome pathways 2,870; ClinVar gene summaries 5,000 |
| `protein_sequence_window.jsonl` | 100,000 | Swiss-Prot protein windows, OmniGene BF16 embedding target |
| `dna_sequence_window.jsonl` | 100,000 | Ensembl cDNA windows, OmniGene BF16 embedding target |
| `mixed.jsonl` | 30 | small mixed English/sequence POC partition |
| **Total corpus** | **257,886** | text + protein sequence + DNA/cDNA sequence + mixed |

Each corpus row stores `id`, `record_id`, `entity_id`, `source_id`, `accession`,
`modality`, `partition`, retrievable `text`, extracted biological `labels`, and
traceable source metadata.

## Annotated Tasks

| Task family | Records |
| --- | ---: |
| gene lookup | 5 |
| pathway lookup | 3 |
| protein sequence | 52 |
| DNA/cDNA sequence | 52 |
| **Total tasks** | **112** |

All 112 tasks have at least one `positive_corpus_refs` link in the full export.
This means retrieval results can be evaluated either by expected labels
(`entity_ids`, `source_ids`, `accessions`, `symbols`, biological labels) or by
direct corpus-row references.

## Why This Is Useful For The Paper

BioRAG-Standard v0 makes the experimental story cleaner:

1. The same dataset backs text lookup, sequence retrieval, instant vector
   search, BLAST verification, and DRAG graph analysis.
2. The corpus is partitioned by modality, so ablations can remove DNA, protein,
   text, graph, or mixed views cleanly.
3. The task layer records expected evidence labels, so evaluation is not just a
   demo query list.
4. Positive corpus references support agent-grounding metrics: an answer can be
   judged by whether it cited the correct local evidence rows.

## Research Framing

The dataset supports a staged paper narrative:

- **Data:** build a multimodal BioRAG benchmark/library from Standard biomedical
  records plus sequence windows.
- **Representation:** use OmniGene CPT embeddings over DNA/cDNA, protein, and
  text/mixed records.
- **Retrieval:** compare BLAST, vector-only, vector rerank, and hybrid
  vector+BLAST conditions.
- **System:** evaluate instant vector context and verified BLAST/DRAG evidence
  modes.
- **Biological structure:** test whether sequence-vector DRAG graphs show
  gene/family/community enrichment before and after adding BLAST edges.

This is stronger than a pure engineering paper because the dataset, evaluation
tasks, retrieval stack, and graph-biological analysis all use the same local
evidence substrate.

## Current Limitations

- v0 task labels are still focused on exact lookup and sequence-fragment
  retrieval. The next version should add multi-hop natural-language questions
  that require sequence-to-gene-to-pathway or protein-to-literature reasoning.
- GO/pathway labels are present in Standard text and graph nodes, but sequence
  windows are not yet deeply linked to GO/pathway annotations. This is the next
  layer for biological significance analysis.
- The mixed partition is still a small POC. It should be expanded with paper
  abstracts, UniProt function text, pathway descriptions, and sequence snippets.
