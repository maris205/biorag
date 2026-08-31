# Agent Application Route Ablation

The generator, decoding, query split, and answer contract are fixed across routes. The experiment measures the effect of available evidence, not free-form expert reasoning.

| Route | Function F1 | Literature F1 | GO prompt recall | PMID prompt recall | GO/PMID selection F1 | Citation entailment | Pack hallucination | Mechanism abstention | Mean/P95 generation ms | Peak GPU GiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| No retrieval | 0.000 | 0.000 | 0.000 | 0.000 | -- | -- | 0.000 | 1.000 | 883.3/1369.8 | 17.611 |
| Ordinary text RAG (R2R) | 0.000 | 0.000 | 0.000 | 0.000 | 0.865/1.000 | 1.000 | 0.000 | 1.000 | 2722.5/4689.3 | 17.821 |
| Sequence vector | 0.072 | 0.075 | 0.187 | 0.128 | 0.944/1.000 | 1.000 | 0.000 | 1.000 | 2827.9/5548.3 | 17.876 |
| Combined BLAST+vector | 0.087 | 0.084 | 0.202 | 0.133 | 0.933/1.000 | 1.000 | 0.000 | 1.000 | 3001.6/6278.4 | 17.874 |
| Combined BLAST+vector+DAG | 0.094 | 0.088 | 0.202 | 0.133 | 1.000/1.000 | 1.000 | 0.000 | 1.000 | 2844.6/5544.8 | 17.772 |

The ordinary text-RAG control is a live R2R 3.6.6 collection (`8e999977-1eb4-4b24-a6d9-ce833a0f5d21`) with 14071 documents and qwen3-embedding:0.6b@ollama-ac6da0dfba84. Graph search is disabled. Its server-side query embedding plus lookup latency is 833.2 ms mean and 1431.6 ms P95.

The no-retrieval condition applies the system's no-evidence abstention policy; citation entailment and evidence selection are therefore not applicable rather than positive results.

## Paired Query Bootstrap

| Comparison | QA type | Metric | Delta | 95% CI |
|---|---|---|---:|---:|
| r2r_text_only -> sequence_vector | function | answer_f1 | +0.072 | [+0.035, +0.116] |
| r2r_text_only -> sequence_vector | literature | answer_f1 | +0.075 | [+0.039, +0.115] |
| r2r_text_only -> sequence_vector | function | prompt_gold_recall | +0.187 | [+0.106, +0.278] |
| r2r_text_only -> sequence_vector | literature | prompt_gold_recall | +0.128 | [+0.069, +0.195] |
| sequence_vector -> combined_blast_vector | function | answer_f1 | +0.015 | [+0.000, +0.038] |
| sequence_vector -> combined_blast_vector | literature | answer_f1 | +0.009 | [-0.003, +0.023] |
| sequence_vector -> combined_blast_vector | function | prompt_gold_recall | +0.015 | [+0.000, +0.045] |
| sequence_vector -> combined_blast_vector | literature | prompt_gold_recall | +0.005 | [-0.004, +0.018] |
| combined_blast_vector -> combined_blast_vector_dag | function | answer_f1 | +0.006 | [-0.026, +0.038] |
| combined_blast_vector -> combined_blast_vector_dag | literature | answer_f1 | +0.005 | [-0.003, +0.015] |
| combined_blast_vector -> combined_blast_vector_dag | function | evidence_selection_f1 | +0.067 | [+0.035, +0.105] |
| combined_blast_vector -> combined_blast_vector_dag | literature | evidence_selection_f1 | +0.000 | [+0.000, +0.000] |

Intervals are paired over the same 66 query IDs with 10,000 bootstrap replicates. A confidence interval crossing zero is treated as directional engineering evidence, not a statistically resolved gain.

## Generator Robustness

Both generators execute the identical combined BLAST+vector+DAG pack; this is a robustness check, not a generator contribution.

| Generator | Function F1 | Literature F1 | GO/PMID selection F1 | Citation entailment | Pack hallucination | Mechanism abstention | Mean generation ms | Peak GPU GiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.5-9B | 0.094 | 0.088 | 1.000/1.000 | 1.000 | 0.000 | 1.000 | 2844.6 | 17.772 |
| Qwen2.5-7B-Instruct | 0.094 | 0.090 | 0.990/0.988 | 1.000 | 0.000 | 1.000 | 1527.2 | 14.353 |
