# 100-query Split Summary

Strict parent-ID evaluation split by modality. Each seed has 50 protein and 50 DNA/cDNA tasks.

## seed20260515

| Condition | Modality | Hit@1 | Hit@5 | Hit@10 | MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| `blast` | protein | 0.9000 | 0.9800 | 1.0000 | 0.9395 |
| `blast` | DNA/cDNA | 0.1200 | 0.3400 | 0.5600 | 0.2368 |
| `vector` | protein | 0.4600 | 0.5600 | 0.5800 | 0.5045 |
| `vector` | DNA/cDNA | 0.3800 | 0.5000 | 0.5600 | 0.4361 |
| `hybrid_gated` | protein | 0.9000 | 0.9800 | 1.0000 | 0.9395 |
| `hybrid_gated` | DNA/cDNA | 0.1200 | 0.3400 | 0.5600 | 0.2512 |

## seed20260516

| Condition | Modality | Hit@1 | Hit@5 | Hit@10 | MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| `blast` | protein | 0.8600 | 0.9000 | 0.9200 | 0.8825 |
| `blast` | DNA/cDNA | 0.0800 | 0.2800 | 0.5400 | 0.2025 |
| `vector` | protein | 0.3200 | 0.4800 | 0.5200 | 0.3927 |
| `vector` | DNA/cDNA | 0.3800 | 0.4800 | 0.4800 | 0.4200 |
| `hybrid_gated` | protein | 0.8600 | 0.9000 | 0.9200 | 0.8847 |
| `hybrid_gated` | DNA/cDNA | 0.0800 | 0.2800 | 0.5400 | 0.2185 |

## Mean Over Seeds

| Condition | Modality | Hit@1 | Hit@5 | Hit@10 | MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| `blast` | protein | 0.8800 | 0.9400 | 0.9600 | 0.9110 |
| `blast` | DNA/cDNA | 0.1000 | 0.3100 | 0.5500 | 0.2197 |
| `vector` | protein | 0.3900 | 0.5200 | 0.5500 | 0.4486 |
| `vector` | DNA/cDNA | 0.3800 | 0.4900 | 0.5200 | 0.4280 |
| `hybrid_gated` | protein | 0.8800 | 0.9400 | 0.9600 | 0.9121 |
| `hybrid_gated` | DNA/cDNA | 0.1000 | 0.3100 | 0.5500 | 0.2349 |

Interpretation: protein and DNA/cDNA should be reported separately. The combined headline is useful only as a smoke summary, because strict transcript-level DNA recovery is much harder and has different failure modes from protein retrieval.
