# Figure Manifest

Date: 2026-05-16

All figures are generated as vector PDFs by Python scripts in this directory. Re-run from the project root:

```bash
python figures/gen_fig1_architecture.py
python figures/gen_fig2_dataset.py
python figures/gen_fig3_retrieval_quality.py
python figures/gen_fig4_latency.py
python figures/gen_fig5_drag_biology.py
python figures/gen_fig6_drag_knowledge_graph_showcase.py
python figures/gen_latex_includes.py
```

## Figures

| Figure | Output | Script | Data sources |
| --- | --- | --- | --- |
| Fig. 1 architecture | `fig1_architecture.pdf` | `gen_fig1_architecture.py` | manuscript architecture; no experimental data |
| Fig. 2 dataset | `fig2_dataset.pdf` | `gen_fig2_dataset.py` | `data/biorag_standard_v0/manifest.json` |
| Fig. 3 retrieval quality | `fig3_retrieval_quality.pdf` | `gen_fig3_retrieval_quality.py` | `reports/sequence_window_bf16_100k_100query_bio_split_summary.json`, `reports/vector_candidate_budget_sweep_eval.json` |
| Fig. 4 latency | `fig4_latency.pdf` | `gen_fig4_latency.py` | `reports/instant_verified_latency_benchmark.json`, `reports/chroma_lookup_text_sequence_100k_benchmark.json`, `reports/faiss_cpu_lookup_*.json` |
| Fig. 5 DRAG biology | `fig5_drag_biology.pdf` | `gen_fig5_drag_biology.py` | `reports/drag_gene_family_purity_10k.json`, `reports/drag_functional_enrichment_10k.json`, `reports/drag_literature_support_10k.json` |
| Fig. 6 DRAG evidence showcase | `fig6_drag_knowledge_graph_showcase.pdf` | `gen_fig6_drag_knowledge_graph_showcase.py` | `reports/traces/dna_igkv2_40_hybrid_trace.json`, `reports/traces/protein_yfbr_hybrid_trace.json` |

## Caption Snippets

LaTeX snippets are generated in `latex_includes.tex`. Markdown references are already inserted in `paper.md`.

## Quality Notes

- Figures use PDF vector output.
- Figure text uses embedded TrueType-compatible fonts.
- No figure contains a plot title; explanatory text belongs in captions.
- Fig. 4 uses a log scale for verified-mode route latency because BLAST is two to three orders of magnitude slower than graph expansion.
- Fig. 5 reports biological evidence structure as community-level support, not proof of mechanism.
- Fig. 6 is a real trace visualization: nodes and typed vector/BLAST edges come from saved DRAG traces, not a conceptual drawing.
