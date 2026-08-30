# Sequence-Token Biological Semantics

## Research question

Do frequency-derived DNA/protein tokenization units carry reproducible biological associations, even though they were not designed as motifs?

The defensible hypothesis is not `token = motif`. It is:

> Variable-length sequence tokens or short token compositions may be statistically associated with curated biological entities more strongly than matched local-sequence baselines, and may provide an interpretable exploratory layer between a raw sequence and the SeqLit evidence DAG.

## Tokenizer activation prerequisite

OmniGene's merged tokenizer contains literal `▶...` DNA and `◆...` protein BPE entries. Current raw sequence inputs contain neither prefix. The current CPT preprocessing script also tokenized raw sequence strings directly. Therefore:

- the merged model still received sequence CPT through the base Gemma tokenizer;
- the standalone biological BPE vocabulary is frequency-derived and can be studied as a segmentation;
- current evidence does not support calling those added entries CPT-learned biological tokens;
- a corrected vocabulary-contribution experiment requires modality-aware pretokenization followed by CPT.

The reproducible audit is implemented in `scripts/audit_omnigene_bio_tokens.py`.

## Graph schema

The exploratory layer uses these typed paths:

```text
bio_sequence_token
  -> observed_in_sequence
protein
  -> curated GO/evidence
paper

bio_sequence_token
  -> statistically_associated_with
GO term
```

`observed_in_sequence` is deterministic tokenization evidence. `statistically_associated_with` is exploratory statistical evidence and must never be presented as a curated or causal relation.

## Compact experiment blocks

### B1. Activation and compression audit (completed)

- Compare vocabulary entries, raw-input token hits, intended BPE segmentation, and sampled CPT binary IDs.
- Report residues per token and biological-token activation rate.
- Stop/go: do not run embedding-level token interpretation if activation is zero.

Result: the marker-prefixed DNA/protein entries have zero activation on current
raw inputs and sampled CPT binaries. Current OmniGene retrieval is attributed to
sequence CPT through base tokens, not an isolated vocabulary effect.

### B2. Parent-level GO association (completed, exploratory)

- Unit of analysis: one Swiss-Prot parent protein, never individual windows.
- Methods: intended protein BPE, actual current runtime tokens, overlapping fixed 3-mers.
- Statistics: hypergeometric enrichment, BH-FDR over all eligible token-GO pairs.
- Null: permute complete GO label sets within protein-length strata.
- Output: typed token-to-protein and token-to-GO graph edges with provenance.

Result: intended protein BPE has 15 significant token--GO pairs, while the
fixed 3-mer control has 57. The permutation control rejects a fully random-label
explanation, but no BPE advantage is established.

### B3. Held-out retrieval contribution (completed, negative/limited)

- Learn token-to-GO edges from 1,901 index proteins only.
- Select graph weight and ProtT5 tail budget on 33 development queries.
- Freeze and report 66 parent-held-out test queries with paired bootstrap intervals.
- Compare direct BPE BM25, BPE+GO expansion, fixed 3-mer BM25, ProtT5, RRF, and tail replacement.

Result: direct BPE and BPE+GO routes trail fixed 3-mer and ProtT5. Naive RRF
harms retrieval. Tail replacement recovers one additional top-100 query without
changing paper retrieval, and the paired interval includes no gain. The token
graph remains an interpretability/evidence extension rather than a selected
retrieval route.

### B4. Motif and family controls (paper-grade next step)

- Add PROSITE motif coordinates and Pfam/InterPro domain coordinates.
- Measure token-boundary precision/recall and span overlap against length-matched random boundaries.
- Split proteins by UniRef50, not random records, to prevent homolog leakage.
- Compare single tokens and adjacent 2/3-token compositions with fixed k-mers.
- Success criterion: a reproducible advantage over fixed k-mers on held-out families, not merely many significant in-index enrichments.

## Paper placement

- Keep B1 as a model/data audit or appendix result.
- Keep B2 and B3 exploratory; their controlled outcomes do not support a main retrieval contribution.
- Promote token biological meaning to the main paper only after B4 survives UniRef50 family holdout and known-motif coordinate controls.
- SeqLit-DAG and Agent evidence evaluation remain the main application contribution; this analysis is a biological-meaning extension rather than a replacement main line.
