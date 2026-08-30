# DNA-ESM2-Style Training

This prototype trains a DNA-specific encoder with an ESM-style bidirectional
Transformer objective. It is intentionally separate from the OmniGene
generator: the output is a sequence embedding for DNA retrieval.

## Design

- overlapping 3-mer vocabulary over `ACGTN` plus five special tokens;
- BERT/ESM-style bidirectional Transformer encoder;
- masked DNA modeling on two augmented views from the same crop;
- symmetric InfoNCE view loss;
- optional reverse-complement augmentation;
- attention-mask mean pooling for BioRAG embeddings.

The first practical model is a 384-hidden, 8-layer encoder (about 28M
parameters). A 12-layer, 768-hidden variant can also fit on a 32GB GPU, but
the smaller model is preferred for the initial retrieval experiment.

## Pilot training

The source file contains one 1,000-base DNA record per line. The command below
loads a bounded 100k-record pilot subset while leaving the held-out benchmark
parents in `data/heldout/` untouched:

```bash
CUDA_VISIBLE_DEVICES=0 \
/root/autodl-tmp/dnarag/.venv-dna4/bin/python scripts/train_dna_es2.py \
  --source /autodl-fs/data/omnigene_v2/data/dna_32g.txt \
  --output runs/dna_es2_small_pilot \
  --max-records 100000 --max-length 512 --max-bases 512 \
  --hidden-size 384 --layers 8 --heads 6 --batch-size 32 \
  --steps 2000 --warmup-steps 100 --dtype bf16 \
  --contrastive-weight 0.25 --rc-probability 0.5 --seed 13
```

The trained embedding checkpoint is written to
`runs/dna_es2_small_pilot/encoder`. It can be evaluated through the existing
DNA benchmark:

```bash
HF_HOME=/root/autodl-tmp/huggingface \
/root/autodl-tmp/dnarag/.venv-dna4/bin/python \
scripts/eval_dna_embedding_matrix.py \
  --backend dna_es2 --model runs/dna_es2_small_pilot/encoder \
  --pooling mean --dtype bf16 \
  --benchmark benchmarks/dna_parent_frag_100.jsonl \
  --index-fasta data/heldout/dna_parent_frag_100_controlled20k_index.fasta \
  --index-window-limit 20000 \
  --window-size 256 --window-stride 128 --max-length 512 --top-k 200 \
  --output reports/results/dna_es2_small_pilot_eval.json
```

The completed second-round 117M MLM run used the same command with
`--max-records 1000000 --hidden-size 768 --layers 12 --heads 12
--batch-size 32 --steps 10000 --learning-rate 1e-4
--contrastive-weight 0` and writes its encoder to
`runs/dna_es2_117m_mlm_1m_10k/encoder`. Its fair 20k evaluation is stored in
`reports/results/dna_es2_117m_mlm_1m_10k_20k_eval.json`.

## Evaluation rule

The held-out benchmark uses parent-level exclusion. The headline comparison
must include DNABERT-2 mean, DNABERT-S, Nucleotide Transformer, BLASTN, and
DNA-ESM2 mean. Any model trained on the 32GB corpus must be checked for exact
parent or sequence-window overlap before its score is interpreted as a
biological retrieval result.

The target for the first pilot is improvement over DNABERT-2 mean (`Bio
Hit@10 = 0.25` on the current control), not parity with BLASTN. BLASTN remains
the alignment-grounded verifier in the BioRAG route.
