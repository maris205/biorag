# Data

The initialized config points to the existing Standard bundle:

```text
/autodl-fs/data/open-rosalind-kb/standard
```

Expected contents:

- `raw/`: source files from UniProt, NCBI Gene, HGNC, GO, Reactome, ClinVar, Ensembl, PubMed, and BLAST Swiss-Prot.
- `index/open_rosalind_standard.sqlite`: SQLite FTS5 search index.
- `index/blast/swissprot.*`: local Swiss-Prot BLAST database.
- `index/blast/ensembl_cdna.*`: local Ensembl cDNA BLASTN database, generated from `raw/ensembl/Homo_sapiens.GRCh38.cdna.all.fa.gz`.
- `index/manifest.json`: build metadata and counts.

The current manifest in this workspace reports:

```text
hgnc: 44,986
reactome_human: 2,870
go_terms: 5,000
clinvar_gene: 5,000
blast sequences: 574,627
cDNA BLASTN sequences: 328,868
```

Rebuild the cDNA BLASTN database with:

```bash
bash scripts/build_ensembl_cdna_blastn.sh
```

## Generated Outputs

## BioRAG-Standard Dataset

The current paper-facing annotated dataset is exported to:

```text
data/biorag_standard_v0
```

Build it with:

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

Current v0 contents:

- 57,856 Standard text records: HGNC, GO, Reactome, and ClinVar gene summaries.
- 100,000 protein sequence-window records.
- 100,000 DNA/cDNA sequence-window records.
- 30 mixed-modality POC records.
- 112 annotated RAG tasks, all linked to positive corpus references in the full export.

See `reports/biorag_standard_dataset.md` for the dataset report and
`data/biorag_standard_v0/SCHEMA.md` for the row schema.

`dnarag build-graph` writes to the configured graph directory. The default repo-local path is:

```text
indexes/standard/graph
```

The expected files are:

```text
graph.sqlite
nodes.parquet
edges.parquet
entity_aliases.parquet
manifest.json
```

If `pyarrow` is unavailable, the builder still writes `graph.sqlite` and JSONL sidecars.
Use `--skip-sidecars` for fast smoke builds that only need SQLite and the manifest.

`dnarag build-vector` writes to the configured vector directory. The default repo-local path is:

```text
indexes/standard/vector
```

The expected files are:

```text
<target>.npz
<target>_id_map.jsonl
vector.sqlite
chroma/
manifest.json
```

`chroma/` is the RAG POC vector database. It is a local persistent Chroma store,
so the project uses a common RAG stack without running an external vector DB
service:

```bash
python -m dnarag.cli vector-db import --engine chroma --config configs/standard.yaml --targets text
python -m dnarag.cli vector-db status --engine chroma --config configs/standard.yaml
```

Chroma record CRUD is exposed through `vector-db add`, `vector-db upsert`,
`vector-db update`, `vector-db delete`, and `vector-db get`. `add/upsert/update`
consume JSONL rows containing `embedding`, `record_id`, and `metadata`.

Current vector targets are:

- `text`: typed Standard KB text records, including HGNC genes, GO terms, Reactome pathways, and ClinVar gene summaries.
- `protein_sequence`: Swiss-Prot protein FASTA records with English headers, accessions, alphabet, length, and sequence text.
- `dna_sequence`: Ensembl human cDNA FASTA records with English headers, accessions, alphabet, length, and sequence text.
- `protein_sequence_window`: sequence-only Swiss-Prot protein windows for fragment retrieval.
- `dna_sequence_window`: sequence-only Ensembl cDNA windows for fragment retrieval.
- `mixed`: a small mixed-modality collection for POC retrieval over English biomedical text plus protein and DNA/cDNA sequence records.

Sequence records are stored as typed documents such as `[TYPE=protein_sequence]`
or `[TYPE=dna_sequence]`. `DNARAG_SEQUENCE_MAX_CHARS` controls how many sequence
characters are embedded per record.

Window records store only the biological sequence in the Chroma document, with
metadata carrying the accession, parent record ID, window offset, window size,
stride, alphabet, source, and original FASTA header. This avoids the earlier
failure mode where long header-heavy sequence documents were embedded as a
single record and short query fragments did not reliably retrieve their parent.

Build the paper-scale BF16 sequence-window index:

```bash
bash scripts/build_omnigene_merged_sequence_windows.sh protein_sequence_window,dna_sequence_window 100000 128 64 16
```

Build a transformers 4-bit sequence-window POC only as a low-memory efficiency
baseline:

```bash
bash scripts/build_omnigene_4bit_sequence_windows.sh protein_sequence_window,dna_sequence_window 1024 128 64 1
```

Arguments are `targets`, `limit`, `window_size`, `stride`, `batch_size`, and
optional `source_limit`.

`vector.sqlite` is the fallback local vector database. It stores collection metadata
and row metadata in SQLite, while vectors remain in the compressed NumPy matrix:

```bash
python -m dnarag.cli vector-db import --engine simple --config configs/standard.yaml --targets text
python -m dnarag.cli vector-db status --engine simple --config configs/standard.yaml
```

When FAISS is installed, a future build can add `.faiss` files beside the fallback NumPy artifacts.

For backend selection, use Chroma as the CRUD-complete POC vector DB, FAISS GPU
as the easiest local lookup-speed benchmark, and Milvus GPU as the later
production-scale serving benchmark for very large indexes and high concurrency.

## Data Policy

Downloaded reference projects, PDFs, raw data, generated indexes, and local databases are ignored by `.gitignore`. The source repo should track code, configuration, docs, and tests only.
