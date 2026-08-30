"""Schema helpers for the sequence-literature evidence DAG."""
from __future__ import annotations


def graph_schema_sql() -> str:
    return """
    PRAGMA journal_mode = OFF;
    PRAGMA synchronous = OFF;

    CREATE TABLE nodes (
        entity_id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        canonical_id TEXT,
        name TEXT,
        source TEXT,
        description TEXT,
        organism TEXT,
        metadata_json TEXT
    );

    CREATE INDEX idx_nodes_type ON nodes(entity_type);
    CREATE INDEX idx_nodes_name ON nodes(name);
    CREATE INDEX idx_nodes_canonical ON nodes(canonical_id);

    CREATE TABLE aliases (
        entity_id TEXT NOT NULL,
        alias TEXT NOT NULL,
        alias_type TEXT,
        source TEXT,
        PRIMARY KEY (entity_id, alias, source)
    );

    CREATE INDEX idx_aliases_alias ON aliases(alias);

    CREATE TABLE edges (
        source_entity_id TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        target_entity_id TEXT NOT NULL,
        source TEXT,
        source_record TEXT,
        evidence_level TEXT,
        confidence REAL,
        retrieval_score REAL,
        verification_method TEXT,
        database_version TEXT,
        metadata_json TEXT,
        PRIMARY KEY (source_entity_id, relation_type, target_entity_id, source)
    );

    CREATE INDEX idx_edges_source ON edges(source_entity_id);
    CREATE INDEX idx_edges_target ON edges(target_entity_id);
    CREATE INDEX idx_edges_type ON edges(relation_type);
    """


def manifest_schema() -> dict[str, object]:
    return {
        "dataset": "BioRAG-SeqLit-DAG",
        "version": "0.2.0",
        "node_types": {
            "protein": "Reviewed UniProt/Swiss-Prot protein sequence entry.",
            "protein_window": "Local protein sequence window for retrieval tasks.",
            "go_term": "Gene Ontology term.",
            "paper": "PubMed literature record or PMID placeholder.",
            "evidence": "Curated GO annotation evidence record linking protein, GO term, and citation.",
            "organism": "NCBI taxonomy organism node.",
            "gene": "Gene symbol node from GOA/UniProt metadata.",
        },
        "edge_types": {
            "has_window": "protein -> protein_window",
            "encoded_by": "protein -> gene",
            "from_organism": "protein/gene -> organism",
            "annotated_with_go": "protein -> go_term",
            "has_evidence": "protein -> evidence",
            "evidence_for_go": "evidence -> go_term",
            "supported_by_paper": "protein/go_term/evidence -> paper",
        },
        "edge_provenance": {
            "source_record": "Stable local or upstream record identifier supporting the edge.",
            "evidence_level": "Curated, alignment-verified, inferred, or unverified retrieval evidence class.",
            "retrieval_score": "Optional query-time retrieval score; null for static curated edges.",
            "verification_method": "Method used to establish or verify the edge.",
            "database_version": "Upstream release or explicitly labeled local snapshot identifier.",
        },
        "dag_view": [
            "query_sequence",
            "protein_candidate",
            "go_term_or_future_domain_family_pathway",
            "evidence_record",
            "paper",
        ],
    }
