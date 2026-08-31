# R2R Application Integration

## Boundary

R2R is the application substrate, not the biological method contribution. The
integration uses R2R v3 for document CRUD, collections, access control, ordinary
text retrieval, and Agent-facing APIs. BioRAG remains responsible for:

- protein and DNA sequence encoders;
- vector candidate generation over sequence partitions;
- BLASTP/BLASTN verification;
- authoritative sequence-to-literature graph traversal;
- typed evidence packs and provenance checks.

This division keeps the deployment close to an existing R2R project without
forcing raw sequences through a generic text embedding model. It also lets the
paper hold the generator and application shell fixed while ablating the evidence
route.

## How SeqLit-DAG Is Built

The current graph is database-derived rather than extracted from paper prose by
an LLM:

1. Select reviewed Swiss-Prot proteins with GOA annotations supported by PubMed
   identifiers and approved experimental evidence codes.
2. Parse protein sequences and identifiers from Swiss-Prot FASTA.
3. Resolve GO terms from the Gene Ontology OBO snapshot.
4. Preserve each GOA annotation as an explicit evidence node, including its
   qualifier, evidence code, assigned database, annotation date, and reference.
5. Link PubMed nodes from GOA references and optionally enrich them with titles
   and abstracts from a local PubMed cache.
6. Export the directed application view:

```text
held-out sequence
  -> retrieved protein candidate
  -> GO term and GOA evidence record
  -> PubMed record
```

The 2k resource currently contains 2,000 protein nodes, 12,858 GO annotation
records, 4,304 PMID nodes, and 63,651 typed edges. The held-out application split
removes 99 parent proteins from the 1,901-protein index. This controls exact
parent leakage, but it is not yet a family-cluster or remote-homology split.

## Evidence Contract

Every exported relationship carries these fields:

| Field | Meaning |
|---|---|
| `relation_type` | Typed graph predicate |
| `source_database` | GOA, UniProtKB, PubMed, BLAST, or another named source |
| `source_record` | Stable supporting record or local evidence-node ID |
| `evidence_level` | Curated, alignment-verified, derived, or unverified retrieval evidence |
| `retrieval_score` | Optional query-time score; null for static curated edges |
| `verification_method` | GOA evidence code, curated record, BLAST alignment, or dense similarity |
| `database_version` | Upstream release or explicitly labeled local snapshot |

The SQLite graph is the source of truth. R2R receives an explicit projection of
the same entities and relationships; automatic LLM graph extraction is not used
for these biological edges.

## Export

Build the normal application bundle. Raw sequence documents are excluded from
R2R text embedding by default:

```bash
python scripts/export_seq_lit_r2r.py \
  --source data/seq_lit_dag_swissprot_sample \
  --output outputs/r2r/seq_lit_dag_swissprot_sample
```

The output contains `documents.jsonl`, `entities.jsonl`,
`relationships.jsonl`, and `manifest.json`. The sample export contains 985 text
evidence documents, 2,231 entities, and 5,240 explicit relationships.

The full 2k application projection is produced with:

```bash
python scripts/export_seq_lit_r2r.py \
  --source data/seq_lit_dag_swissprot_2k \
  --output outputs/r2r/seq_lit_dag_swissprot_2k
```

It contains 12,858 text/mixed evidence documents, 22,939 entities, and 63,651
explicit relationships while excluding 2,000 raw sequence documents from the
generic text collection.

Create the leakage-audited generic text-RAG control from the same held-out split
used by the Agent ablation. It contains 1,901 index proteins and 12,170
flattened text-evidence records. The 99 held-out parents are rejected if any
accession occurs in this collection:

```bash
python scripts/export_seq_lit_r2r.py \
  --source data/seq_lit_dag_swissprot_2k \
  --documents-file data/seq_lit_dag_function_heldout_2k/index_documents.jsonl \
  --heldout-queries-file data/seq_lit_dag_function_heldout_2k/queries.jsonl \
  --documents-only --include-sequence-documents \
  --output outputs/r2r/seq_lit_dag_function_heldout_2k_text_control
```

The resulting manifest contains 14,071 documents and an explicit leakage audit
with 99 held-out parents, 1,901 indexed accessions, and zero exact accession
overlap. This collection is an ordinary flattened text-RAG application control,
not a biological sequence embedding baseline.

## Live R2R Import

The adapter targets the public R2R v3 SDK contract tested against R2R 3.6.6. The
published 3.6.6 dependency metadata has incompatible OpenAI/LiteLLM constraints,
so the reproducible setup uses the upstream v3.6.5 frozen lock and overlays only
the 3.6.6 package:

```bash
bash scripts/setup_r2r_runtime.sh
```

The live text control uses PostgreSQL 14 with pgvector 0.8.1 and Ollama 0.33.2
with `qwen3-embedding:0.6b` (595.78M parameters, Q8_0 artifact digest
`ac6da0dfba84`, 1,024 dimensions). Start Ollama and R2R after creating
the PostgreSQL role/database and enabling the `vector` extension:

```bash
OLLAMA_MODELS=/path/to/ollama-models ollama serve
ollama pull qwen3-embedding:0.6b

export R2R_POSTGRES_USER=r2r
export R2R_POSTGRES_PASSWORD='<local-password>'
export R2R_POSTGRES_HOST=127.0.0.1
export R2R_POSTGRES_PORT=5432
export R2R_POSTGRES_DBNAME=biorag_r2r
export OLLAMA_API_BASE=http://127.0.0.1:11434
.venv-r2r/bin/python -m r2r.serve \
  --host 127.0.0.1 --port 7272 \
  --config-path configs/r2r_text_control.toml
```

Import the frozen text control with deterministic UUIDs, four concurrent
requests, and a resumable state file:

```bash
.venv-r2r/bin/python scripts/export_seq_lit_r2r.py \
  --source data/seq_lit_dag_swissprot_2k \
  --documents-file data/seq_lit_dag_function_heldout_2k/index_documents.jsonl \
  --heldout-queries-file data/seq_lit_dag_function_heldout_2k/queries.jsonl \
  --documents-only --include-sequence-documents \
  --output outputs/r2r/seq_lit_dag_function_heldout_2k_text_control \
  --ingest --skip-graph --base-url http://127.0.0.1:7272 \
  --collection-name 'BioRAG SeqLit heldout text control Qwen3-0.6B' \
  --document-workers 4
```

The state file is checkpointed after every 50 successful documents. Repeating
the command resumes the same collection and skips completed deterministic IDs.
If a remote write succeeds immediately before a local checkpoint, the importer
recognizes the existing document, verifies its BioRAG record ID, and restores
the target collection association instead of failing or duplicating content.

For a large graph, keep SQLite as the authoritative graph and import only the
application projection needed by R2R. The current public R2R graph SDK creates
entities and relationships one request at a time; the resumable importer is
appropriate for the 200-protein sample, while production-scale loading should
use a server-side batch path or a narrower projection.

## Application Ablation

Freeze the four biological evidence conditions:

```bash
python scripts/build_agent_application_ablation.py
```

This creates the same 66-query test partition for:

1. `no_retrieval`;
2. `sequence_vector`;
3. `combined_blast_vector`;
4. `combined_blast_vector_dag`.

The fifth condition, `r2r_text_only`, runs against the live, versioned R2R
collection. The evaluator automatically records the SDK and dependency
versions, sanitized server settings, collection UUID and document count,
embedding configuration, API latency, ranked accessions, and PMIDs. It also writes
`reports/results/agent_application_ablation/r2r_text_only.jsonl`, which uses the
same evidence-pack contract as the four local routes:

```bash
.venv-r2r/bin/python scripts/eval_r2r_text_control.py \
  --base-url http://127.0.0.1:7272 \
  --collection-id <frozen-collection-uuid> \
  --embedding-label qwen3-embedding:0.6b@ollama-ac6da0dfba84 \
  --top-k 50 \
  --output reports/results/r2r_text_control_qwen3_06b.json
```

Run the fixed executor on that pack with `--evidence-mode raw`; score it with
the same query file and `score_generated_agent_qa.py`. This keeps R2R's own
embedding configuration as the only changed retrieval variable. R2R graph,
full-text, and hybrid search are disabled for this control; the measured API
latency includes server-side query embedding plus pgvector lookup.

The same fixed instruction model must execute every evidence pack. Report
end-to-end GO/PMID F1, evidence coverage, evidence-selection F1, citation
validity, citation entailment, out-of-pack identifier hallucination,
evidence-aware abstention, and end-to-end latency.

All five routes have been completed with Qwen3.5-9B. Ordinary R2R text RAG,
sequence vector, combined BLAST+vector, and combined BLAST+vector+DAG obtain
function/literature F1 of `0.000/0.000`, `0.072/0.075`, `0.087/0.084`, and
`0.094/0.088`, respectively. The generic text embedder retrieves no gold label
into the fixed five-candidate prompt; a top-200 diagnostic recovers a relevant
accession for 8/66 queries but still no prompt-level gold evidence. Relative to
R2R, the sequence-vector gains have paired intervals `[0.035, 0.116]` and
`[0.039, 0.115]`. DAG keeps prompt coverage fixed and raises GO
evidence-selection F1 from `0.933` to `1.000` with interval `[0.035, 0.105]`.
See `reports/r2r_text_control_qwen3_06b.md` for integrity checks and claim
boundaries.

## Deployment Notes

- Keep the R2R service and biological indexes on a private network unless the
  deployment has been independently hardened.
- Pin the R2R server and SDK versions and record the collection ID and embedding
  configuration with every result.
- Use separate collections for authoritative application evidence and the
  generic text-only control.
- Do not enable automatic relation extraction for the imported curated graph.
- Treat sequence-to-paper paths as traceable evidence associations, not proof of
  a molecular mechanism for the query sequence.
