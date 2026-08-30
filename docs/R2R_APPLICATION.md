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

Create a separate generic text-RAG control that includes sequence payloads. This
collection is for the application ablation only and must not be reported as a
biological sequence encoder:

```bash
python scripts/export_seq_lit_r2r.py \
  --source data/seq_lit_dag_swissprot_sample \
  --output outputs/r2r/seq_lit_dag_text_control \
  --include-sequence-documents
```

## Live R2R Import

The adapter targets the public R2R v3 SDK contract tested against R2R 3.6.6. It
uses pre-processed chunks, explicit entity/relationship creation, deterministic
document UUIDs, and a resumable import state file.

```bash
pip install 'r2r>=3.6,<4'
export R2R_API_KEY=...
python scripts/export_seq_lit_r2r.py \
  --source data/seq_lit_dag_swissprot_sample \
  --output outputs/r2r/seq_lit_dag_swissprot_sample \
  --base-url http://localhost:7272 \
  --collection-name 'BioRAG SeqLit Evidence' \
  --ingest
```

For a large graph, keep SQLite as the authoritative graph and import only the
application projection needed by R2R. The current public R2R graph SDK creates
entities and relationships one request at a time; the resumable importer is
appropriate for the 200-protein sample, while production-scale loading should
use a server-side batch path or a narrower projection.

## Application Ablation

Freeze the four locally executable evidence conditions:

```bash
python scripts/build_agent_application_ablation.py
```

This creates the same 66-query test partition for:

1. `no_retrieval`;
2. `sequence_vector`;
3. `combined_blast_vector`;
4. `combined_blast_vector_dag`.

The fifth condition, `r2r_text_only`, must be run against a live, versioned R2R
collection. The evaluator records the R2R collection ID, embedding label, API
latency, ranked accessions, and PMIDs. It also writes
`reports/results/agent_application_ablation/r2r_text_only.jsonl`, which uses the
same evidence-pack contract as the four local routes:

```bash
python scripts/eval_r2r_text_control.py \
  --base-url http://localhost:7272 \
  --collection-id <frozen-collection-uuid> \
  --embedding-label <configured-r2r-embedding> \
  --top-k 50 \
  --output reports/results/r2r_text_control.json
```

Run the fixed executor on that pack with `--evidence-mode raw`; score it with
the same query file and `score_generated_agent_qa.py`. This keeps R2R's own
embedding configuration as the only changed retrieval variable. Until the
server version, collection UUID, and embedding label are frozen, the R2R row is
reported as pending rather than replaced by a local proxy.

The same fixed instruction model must execute every evidence pack. Report
end-to-end GO/PMID F1, evidence coverage, evidence-selection F1, citation
validity, citation entailment, out-of-pack identifier hallucination,
evidence-aware abstention, and end-to-end latency.

The four local routes have been completed with Qwen3.5-9B. Sequence vector,
combined BLAST+vector, and combined BLAST+vector+DAG obtain function/literature
F1 of `0.072/0.075`, `0.087/0.084`, and `0.094/0.088`, respectively. DAG keeps
the prompt evidence coverage fixed and raises GO evidence-selection F1 from
`0.933` to `1.000`; the paired 95% interval for this delta is
`[0.035, 0.105]`. The live R2R text-only row remains pending by design.

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
