# DNA Embedding Matrix

All rows use the same held-out-parent DNA/cDNA benchmark and controlled20k index. Biological metrics use shared gene labels; BLASTN remains the alignment reference.

| Model | Pooling | Strand | Window | N | Bio Hit@1 | Bio Hit@5 | Bio Hit@10 | Bio MRR | Exact Hit@10 | Embed ms/q | Lookup ms/q | E2E ms/q | Peak GiB |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| encoder | mean | none | 256/128 | 100 | 0.3100 | 0.5500 | 0.5900 | 0.4178 | 0.0000 | 0.4 | 131.42 | 131.8 | 0.33 |
| unknown | unknown | none | ?/? | 0 | 0.2700 | 0.2700 | 0.2800 | 0.2712 | 0.0000 | 0.0 | 0.00 | 0.0 | 0.00 |
| unknown | unknown | none | ?/? | 0 | 0.2700 | 0.2700 | 0.2700 | 0.2700 | 0.0000 | 0.0 | 0.00 | 0.0 | 0.00 |
| unknown | unknown | none | ?/? | 0 | 0.2700 | 0.2700 | 0.2700 | 0.2700 | 0.0000 | 0.0 | 0.00 | 0.0 | 0.00 |
| dnabert2_retrieval_hard_1k | mean | none | 256/128 | 100 | 0.2400 | 0.2500 | 0.2500 | 0.2465 | 0.0000 | 0.6 | 6.90 | 7.5 | 0.56 |
| DNABERT-2 117M | mean | none | 256/128 | 100 | 0.2300 | 0.2300 | 0.2500 | 0.2347 | 0.0000 | 0.6 | 10.38 | 10.9 | 0.67 |
| modernGENA-base | mean | rc_mean | 256/128 | 100 | 0.2100 | 0.2200 | 0.2400 | 0.2178 | 0.0000 | 2.6 | 12.44 | 15.1 | 0.35 |
| modernGENA-base | mean | none | 256/128 | 100 | 0.1900 | 0.2400 | 0.2700 | 0.2153 | 0.0000 | 0.7 | 7.11 | 7.8 | 0.35 |
| dnabert2_retrieval_hard_4k | mean | none | 256/128 | 100 | 0.2000 | 0.2300 | 0.2300 | 0.2139 | 0.0000 | 1.0 | 12.73 | 13.7 | 0.56 |
| GENA-LM-base | mean | none | 256/128 | 100 | 0.1900 | 0.2400 | 0.2500 | 0.2116 | 0.0000 | 0.6 | 7.01 | 7.6 | 0.71 |
| dnabert2_cdna_mlm_1k | mean | none | 256/128 | 100 | 0.2000 | 0.2300 | 0.2300 | 0.2109 | 0.0000 | 0.9 | 12.43 | 13.4 | 0.56 |
| encoder | mean | none | 256/128 | 100 | 0.1400 | 0.2000 | 0.2300 | 0.1687 | 0.0000 | 1.3 | 6.98 | 8.3 | 0.73 |
| dna_es2_small_genecontrast | mean | none | 256/128 | 100 | 0.1400 | 0.1700 | 0.1900 | 0.1551 | 0.0000 | 0.3 | 6.86 | 7.2 | 0.33 |
| encoder | last | none | 256/128 | 100 | 0.1200 | 0.1700 | 0.2100 | 0.1513 | 0.0000 | 1.3 | 7.11 | 8.4 | 0.73 |
| encoder | cls | none | 256/128 | 100 | 0.1200 | 0.1700 | 0.2100 | 0.1513 | 0.0000 | 1.3 | 7.28 | 8.6 | 0.73 |
| DNABERT-2 117M | mean | none | 128/64 | 100 | 0.1400 | 0.1600 | 0.1700 | 0.1481 | 0.0000 | 0.5 | 6.90 | 7.4 | 0.56 |
| dna_es2_117m_genecontrast | mean | none | 256/128 | 100 | 0.1200 | 0.1700 | 0.1900 | 0.1445 | 0.0000 | 1.3 | 6.97 | 8.3 | 0.73 |
| DNABERT-2 117M | mean | rc_mean | 128/64 | 100 | 0.1400 | 0.1400 | 0.1500 | 0.1438 | 0.0000 | 1.2 | 12.67 | 13.8 | 0.56 |
| encoder | mean | none | 256/128 | 100 | 0.1000 | 0.1700 | 0.2200 | 0.1364 | 0.0000 | 0.4 | 12.11 | 12.5 | 0.33 |
| DNABERT-S | mean | rc_mean | 128/64 | 100 | 0.1000 | 0.1100 | 0.1200 | 0.1090 | 0.0000 | 1.0 | 11.74 | 12.8 | 0.57 |
| DNABERT-S | mean | none | 128/64 | 100 | 0.0900 | 0.1100 | 0.1200 | 0.1020 | 0.0000 | 0.6 | 12.06 | 12.6 | 0.57 |
| OmniGene-4-CPT 4-bit | mean | none | 128/64 | 100 | 0.0500 | 0.0900 | 0.0900 | 0.0688 | 0.0000 | 324.7 | 16.63 | 341.3 | 27.75 |
| HyenaDNA-small | mean | none | 256/128 | 100 | 0.0200 | 0.0300 | 0.0300 | 0.0279 | 0.0000 | 1.6 | 6.80 | 8.4 | 0.15 |
| DNABERT-S | last | none | 128/64 | 100 | 0.0200 | 0.0200 | 0.0300 | 0.0244 | 0.0000 | 0.6 | 12.43 | 13.0 | 0.57 |
| Caduceus-PS | mean | none | 256/128 | 100 | 0.0000 | 0.0400 | 0.0700 | 0.0214 | 0.0000 | 1.8 | 11.62 | 13.4 | 0.50 |
| DNABERT-2 117M | last | none | 128/64 | 100 | 0.0100 | 0.0200 | 0.0200 | 0.0171 | 0.0000 | 0.5 | 11.41 | 11.9 | 0.56 |
| Caduceus-Ph | mean | none | 256/128 | 100 | 0.0000 | 0.0100 | 0.0300 | 0.0116 | 0.0000 | 3.7 | 6.80 | 10.5 | 0.29 |
| DNABERT-S | mean | none | 128/64 | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 35.9 | 0.15 | 36.1 | 0.48 |
| OmniGene-4-CPT 4-bit | mean | none | 128/64 | 2 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 2929.9 | 0.25 | 2930.2 | 27.29 |
| OmniGene-4-CPT 4-bit | mean | none | 128/64 | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 4055.0 | 0.16 | 4055.2 | 27.67 |
| OmniGene-4-CPT 4-bit | mean | none | 128/64 | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 3536.2 | 0.10 | 3536.3 | 27.31 |
| OmniGene-4-CPT 4-bit | mean | none | 128/64 | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 2985.5 | 0.10 | 2985.6 | 27.47 |
| encoder | mean | none | 64/32 | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.8 | 0.21 | 1.0 | 0.01 |
| unknown | unknown | none | ?/? | 0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0 | 0.00 | 0.0 | 0.00 |
| unknown | unknown | none | ?/? | 10000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0 | 0.00 | 0.0 | 0.00 |
| unknown | unknown | none | ?/? | 10000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0 | 0.00 | 0.0 | 0.00 |
| unknown | unknown | none | ?/? | 10000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0 | 0.00 | 0.0 | 0.00 |

## Biological Hit@10 by Query Type

| Model / setting | exact_fragment | middle | mutated | prefix | suffix |
|---|---:|---:|---:|---:|---:|
| encoder / mean / none / 256/128 | 0.7000 | 0.7000 | 0.6000 | 0.4500 | 0.5000 |
| unknown / unknown / none / ?/? | 0.1500 | 0.2500 | 0.2500 | 0.4000 | 0.3500 |
| unknown / unknown / none / ?/? | 0.1500 | 0.2500 | 0.2500 | 0.3500 | 0.3500 |
| unknown / unknown / none / ?/? | 0.1500 | 0.2500 | 0.2500 | 0.3500 | 0.3500 |
| dnabert2_retrieval_hard_1k / mean / none / 256/128 | 0.1500 | 0.2000 | 0.2500 | 0.3500 | 0.3000 |
| DNABERT-2 117M / mean / none / 256/128 | 0.1500 | 0.2000 | 0.2500 | 0.3000 | 0.3500 |
| modernGENA-base / mean / rc_mean / 256/128 | 0.1500 | 0.2500 | 0.2500 | 0.2500 | 0.3000 |
| modernGENA-base / mean / none / 256/128 | 0.1500 | 0.2000 | 0.2500 | 0.4000 | 0.3500 |
| dnabert2_retrieval_hard_4k / mean / none / 256/128 | 0.1500 | 0.1000 | 0.2500 | 0.3500 | 0.3000 |
| GENA-LM-base / mean / none / 256/128 | 0.1500 | 0.2000 | 0.2500 | 0.3000 | 0.3500 |
| dnabert2_cdna_mlm_1k / mean / none / 256/128 | 0.0500 | 0.2000 | 0.3000 | 0.3000 | 0.3000 |
| encoder / mean / none / 256/128 | 0.1500 | 0.1500 | 0.3000 | 0.2500 | 0.3000 |
| dna_es2_small_genecontrast / mean / none / 256/128 | 0.1500 | 0.1000 | 0.2500 | 0.1500 | 0.3000 |
| encoder / last / none / 256/128 | 0.1000 | 0.2000 | 0.2500 | 0.2500 | 0.2500 |
| encoder / cls / none / 256/128 | 0.1000 | 0.2000 | 0.2500 | 0.2500 | 0.2500 |
| DNABERT-2 117M / mean / none / 128/64 | 0.1500 | 0.0500 | 0.3000 | 0.2000 | 0.1500 |
| dna_es2_117m_genecontrast / mean / none / 256/128 | 0.1500 | 0.1500 | 0.2500 | 0.1500 | 0.2500 |
| DNABERT-2 117M / mean / rc_mean / 128/64 | 0.1500 | 0.0500 | 0.2500 | 0.1500 | 0.1500 |
| encoder / mean / none / 256/128 | 0.1000 | 0.2000 | 0.3000 | 0.1500 | 0.3500 |
| DNABERT-S / mean / rc_mean / 128/64 | 0.1500 | 0.0500 | 0.2000 | 0.1000 | 0.1000 |
| DNABERT-S / mean / none / 128/64 | 0.1000 | 0.0500 | 0.2000 | 0.1000 | 0.1500 |
| OmniGene-4-CPT 4-bit / mean / none / 128/64 | 0.1000 | 0.0500 | 0.1000 | 0.1000 | 0.1000 |
| HyenaDNA-small / mean / none / 256/128 | 0.0000 | 0.0500 | 0.0000 | 0.1000 | 0.0000 |
| DNABERT-S / last / none / 128/64 | 0.0000 | 0.0000 | 0.1000 | 0.0000 | 0.0500 |
| Caduceus-PS / mean / none / 256/128 | 0.0500 | 0.0000 | 0.1500 | 0.1000 | 0.0500 |
| DNABERT-2 117M / last / none / 128/64 | 0.0000 | 0.0500 | 0.0500 | 0.0000 | 0.0000 |
| Caduceus-Ph / mean / none / 256/128 | 0.0500 | 0.0500 | 0.0000 | 0.0000 | 0.0500 |
| DNABERT-S / mean / none / 128/64 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| OmniGene-4-CPT 4-bit / mean / none / 128/64 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| OmniGene-4-CPT 4-bit / mean / none / 128/64 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| OmniGene-4-CPT 4-bit / mean / none / 128/64 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| OmniGene-4-CPT 4-bit / mean / none / 128/64 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| encoder / mean / none / 64/32 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| unknown / unknown / none / ?/? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| unknown / unknown / none / ?/? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| unknown / unknown / none / ?/? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| unknown / unknown / none / ?/? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

## Reading the Matrix

- Select the primary DNA encoder by held-out biological MRR/Hit@10, then check stability by query type in the source JSON details.
- Treat reverse-complement averaging as a strand-invariance engineering ablation, not as a new biological learning method.
- Do not compare lookup-only latency with end-to-end latency; the latter includes query embedding.
- Only scale a condition to 100k/full indexes after it improves or clarifies the controlled20k result.
