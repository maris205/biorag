# Generated Agent QA Scoring

String-level GO/PMID correctness and graph-edge citation entailment are measured automatically. This does not replace expert judgment of free-form biomedical statements.

Queries: `66`; answers: `198`.

| QA type | End-to-end F1 | Prompt gold recall | Retrievable F1 | Evidence-selection F1 | Citation validity | Citation entailment | Pack hallucination | Correct abstention | Format | Citation syntax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| function | 0.100 | 0.172 | 0.111 | 0.985 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| literature | 0.100 | 0.128 | 0.138 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| mechanism | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 | 0.000 | 1.000 | 1.000 | 1.000 |

Only structured identifier claims are automatically judged; narrative biomedical correctness remains outside this pilot.
