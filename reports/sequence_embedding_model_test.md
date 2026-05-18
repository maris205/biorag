# Sequence Embedding Model Test

Date: 2026-05-15 UTC

## Models

| Model path | Quantization | Load path | Notes |
| --- | --- | --- | --- |
| `dnagpt/OmniGene-4-CPT-v2-GGUF` / `OmniGene-4-CPT-v2-Q4_K_M.gguf` | pre-quantized GGUF Q4_K_M | llama.cpp | ~16 GiB file, ~20 GiB VRAM during embedding |
| `dnagpt/OmniGene-4-CPT-v2-4bit` | bitsandbytes NF4, double quant, BF16 compute | transformers | ~48 GiB safetensors cache, ~26.5 GiB VRAM during embedding |

The `4bit` model is load-time quantized by transformers/bitsandbytes:

```json
{
  "quant_method": "bitsandbytes",
  "load_in_4bit": true,
  "bnb_4bit_quant_type": "nf4",
  "bnb_4bit_compute_dtype": "bfloat16",
  "bnb_4bit_use_double_quant": true
}
```

## GGUF Diagnosis

With current default GGUF parameters:

```text
DNARAG_GGUF_N_CTX=1024
DNARAG_GGUF_N_BATCH=64
DNARAG_GGUF_N_UBATCH=64
```

different suffixes after a moderate prefix produce identical embeddings:

```text
cos(prefix, prefix + A...) = 1.0
cos(prefix, prefix + text...) = 1.0
```

With:

```text
DNARAG_GGUF_N_CTX=4096
DNARAG_GGUF_N_BATCH=512
DNARAG_GGUF_N_UBATCH=512
```

suffix sensitivity returns:

```text
cos(prefix, prefix + A...) = 0.773214
cos(prefix, prefix + text...) = 0.732812
```

So the existing Chroma sequence vectors were likely built with an embedding path that mostly used the record prefix/header and ignored much of the sequence body.

## Small Sequence-Only Retrieval Test

Temporary in-memory corpus:

- 220 protein sequence windows, first 120 aa/record
- 220 DNA sequence windows, first 120 nt/record
- Query is the matching 120-character sequence fragment

### GGUF Q4_K_M, fixed batch params

| Query | Rank | Self score |
| --- | ---: | ---: |
| `protein_sequence:Q6GZX4` | 181 | 0.782115 |
| `protein_sequence:Q6GZX3` | 51 | 0.901810 |
| `dna_sequence:ENST00000622028.1` | 29 | 0.957463 |
| `dna_sequence:ENST00000632585.1` | 27 | 0.962624 |

### Transformers 4bit NF4

| Query | Rank | Self score |
| --- | ---: | ---: |
| `protein_sequence:Q6GZX4` | 1 | 0.998352 |
| `protein_sequence:Q6GZX3` | 1 | 0.998563 |
| `dna_sequence:ENST00000622028.1` | 2 | 0.988263 |
| `dna_sequence:ENST00000632585.1` | 1 | 0.994926 |

## Interpretation

- Current full Chroma sequence collections should not be treated as valid sequence-vector indexes for exact fragment retrieval.
- GGUF is fast and fits well, but the current llama.cpp embedding setup is fragile for sequence documents and weak on exact sequence-window retrieval.
- The transformers/bitsandbytes 4bit backend is much better for sequence-only fragment retrieval in this small test, but it is slower and uses about 26.5 GiB VRAM.
- BLASTP/BLASTN remains the right exact sequence-search baseline.
- Sequence vectors should be rebuilt as a separate `*_window` collection using sequence-only windows, then evaluated against BLAST and semantic-neighbor tasks.
