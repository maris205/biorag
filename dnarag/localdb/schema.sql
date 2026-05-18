PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_id TEXT,
    name TEXT,
    source TEXT,
    description TEXT,
    organism TEXT,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_canonical ON entities(canonical_id);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

CREATE TABLE IF NOT EXISTS aliases (
    entity_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    alias_type TEXT,
    source TEXT,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(alias);
CREATE INDEX IF NOT EXISTS idx_aliases_entity ON aliases(entity_id);

CREATE TABLE IF NOT EXISTS text_chunks (
    chunk_id TEXT PRIMARY KEY,
    entity_id TEXT,
    source TEXT,
    title TEXT,
    text TEXT,
    chunk_type TEXT,
    year TEXT,
    pmid TEXT,
    metadata_json TEXT,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_text_chunks_entity ON text_chunks(entity_id);
CREATE INDEX IF NOT EXISTS idx_text_chunks_type ON text_chunks(chunk_type);
CREATE INDEX IF NOT EXISTS idx_text_chunks_pmid ON text_chunks(pmid);

CREATE TABLE IF NOT EXISTS sequences (
    sequence_id TEXT PRIMARY KEY,
    entity_id TEXT,
    sequence_type TEXT NOT NULL,
    sequence TEXT NOT NULL,
    sequence_hash TEXT NOT NULL,
    length INTEGER NOT NULL,
    alphabet TEXT,
    source TEXT,
    accession TEXT,
    metadata_json TEXT,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sequences_entity ON sequences(entity_id);
CREATE INDEX IF NOT EXISTS idx_sequences_hash ON sequences(sequence_hash);
CREATE INDEX IF NOT EXISTS idx_sequences_accession ON sequences(accession);

CREATE TABLE IF NOT EXISTS relations (
    relation_id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    evidence_id TEXT,
    source TEXT,
    confidence REAL,
    metadata_json TEXT,
    FOREIGN KEY (source_entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (target_entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);

CREATE TABLE IF NOT EXISTS retrieval_evidence (
    evidence_id TEXT PRIMARY KEY,
    query_id TEXT,
    route TEXT NOT NULL,
    entity_id TEXT,
    source_id TEXT,
    title TEXT,
    snippet TEXT,
    score REAL,
    source TEXT,
    source_url TEXT,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_retrieval_evidence_query ON retrieval_evidence(query_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_evidence_route ON retrieval_evidence(route);

CREATE TABLE IF NOT EXISTS retrieval_traces (
    trace_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    created_at REAL NOT NULL,
    trace_json TEXT NOT NULL
);
