# Vector-Neighborhood Biological Enrichment

Date: 2026-05-15

Model/index: `dnagpt/OmniGene-4-CPT-v2-merged` BF16 sequence-window Chroma
collections.

Purpose: test whether a text-style vector-neighbor recipe, before adding
BLAST/domain/pathway biological rules, produces neighborhoods enriched for
biological labels.

## Protocol

Command:

```bash
python scripts/evaluate_vector_neighborhood_enrichment.py \
  --config configs/standard.yaml \
  --targets protein_sequence_window,dna_sequence_window \
  --anchor-count 100 \
  --top-k 10 \
  --query-results 1000 \
  --metadata-limit 100000 \
  --summary-only \
  --output reports/vector_neighborhood_enrichment_100anchors.json
```

Settings:

- Anchors: 100 labeled windows per target.
- Vector neighbors: Chroma top candidates, then same-parent windows excluded.
- Parent deduplication: enabled, so repeated windows from the same source record
  do not inflate the metric.
- Random baseline: random records from the same loaded collection, with the same
  same-parent exclusion and parent deduplication.
- Biological labels: protein `GN=` names; DNA/cDNA Ensembl `gene:`,
  `gene_symbol:`, gene/transcript biotypes, and immune gene-family prefixes.

Pure DRAG view graphs were also built with the same method-agnostic recipe:

```bash
python -m dnarag.cli build-view-graph \
  --config configs/standard.yaml \
  --target protein_sequence_window \
  --limit 1000 \
  --neighbors 5 \
  --output indexes/standard/graph/views/protein_sequence_window_1k.sqlite

python -m dnarag.cli build-view-graph \
  --config configs/standard.yaml \
  --target dna_sequence_window \
  --limit 1000 \
  --neighbors 5 \
  --output indexes/standard/graph/views/dna_sequence_window_1k.sqlite
```

The generated edges carry `graph_recipe=text_style_vector_neighbors` and
`biological_rules_used=false`.

## Results

Protein sequence windows:

| Match | Vector Hit@1 | Random Hit@1 | Vector Hit@10 | Random Hit@10 | Vector P@10 | Random P@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `GN=` / gene symbol | 0.3400 | 0.0000 | 0.4300 | 0.0200 | 0.1710 | 0.0020 |
| any identity | 0.3400 | 0.0000 | 0.4300 | 0.0200 | 0.1710 | 0.0020 |

DNA/cDNA sequence windows:

| Match | Vector Hit@1 | Random Hit@1 | Vector Hit@10 | Random Hit@10 | Vector P@10 | Random P@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gene ID | 0.6100 | 0.0100 | 0.6900 | 0.0600 | 0.2460 | 0.0060 |
| gene symbol | 0.6562 | 0.0104 | 0.7188 | 0.0625 | 0.2563 | 0.0063 |
| gene family | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5500 | 0.0000 |
| biotype | 0.9900 | 0.9600 | 1.0000 | 0.9900 | 0.9780 | 0.9680 |
| any identity | 0.6300 | 0.0100 | 0.7100 | 0.0600 | 0.2570 | 0.0060 |

## Interpretation

- The signal is strongest for DNA/cDNA: excluding same-parent windows, vector
  neighborhoods recover same-gene or same-symbol records far above random
  baseline.
- Protein windows also show enrichment for the `GN=` label, though the effect is
  weaker than DNA/cDNA in this 100-anchor run.
- Biotype is not a strong result because the random baseline is already high;
  it is too coarse for a headline claim.
- This is the first DRAG-facing evidence that a method-agnostic vector graph can
  contain biological structure before adding explicit biological-rule edges.
- The result should be framed as neighborhood enrichment, not proof of
  functional mechanism. Follow-up layers now include community purity and
  GO/Reactome functional enrichment; Pfam/domain, literature enrichment, and
  stronger BLAST/domain-rule ablations remain open.

Machine-readable output:
`reports/vector_neighborhood_enrichment_100anchors.json`.
