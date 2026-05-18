import json
import sqlite3
from pathlib import Path

from dnarag.config import BioKBConfig
from dnarag.localdb.graph import GraphStore
from dnarag.localdb.graph_builder import GraphIndexBuilder
from dnarag.localdb.standard import StandardKB


def test_standard_search_and_graph_build(tmp_path: Path):
    db_path = tmp_path / "index" / "open_rosalind_standard.sqlite"
    db_path.parent.mkdir(parents=True)
    _make_standard_sqlite(db_path)

    standard = StandardKB(db_path)
    hits = standard.search_text("BRCA1", limit=5)

    assert hits
    assert hits[0].symbol == "BRCA1"

    config = BioKBConfig(
        root=tmp_path,
        raw_dir=tmp_path / "raw",
        index_dir=tmp_path / "index",
        sqlite_path=db_path,
        manifest_path=tmp_path / "index" / "manifest.json",
        graph_dir=tmp_path / "index" / "graph",
        vector_dir=tmp_path / "index" / "vector",
    )
    result = GraphIndexBuilder(config).build(limit=0, reactome_edge_limit=0)

    assert result.node_count >= 2
    assert result.alias_count >= 2

    graph = GraphStore(config.graph_db)
    nodes = graph.resolve_aliases("BRCA1")
    assert any(node.entity_id == "hgnc_gene:HGNC:1100" for node in nodes)
    assert graph.expand("hgnc_gene:HGNC:1100")


def _make_standard_sqlite(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                symbol TEXT,
                name TEXT,
                organism TEXT,
                description TEXT,
                source TEXT NOT NULL,
                source_url TEXT,
                payload_json TEXT
            );
            CREATE VIRTUAL TABLE search_index USING fts5(
                kind,
                source_id,
                symbol,
                name,
                organism,
                description,
                source,
                content='documents',
                content_rowid='id',
                tokenize='unicode61'
            );
            """
        )
        docs = [
            (
                "hgnc_gene",
                "HGNC:1100",
                "BRCA1",
                "BRCA1 DNA repair associated",
                "Homo sapiens",
                "breast cancer type 1 DNA repair homologous recombination",
                "HGNC",
                "https://example.org/hgnc/1100",
                json.dumps({"uniprot_ids": "P38398", "entrez_id": "672", "ensembl_gene_id": "ENSG00000012048"}),
            ),
            (
                "clinvar_gene_summary",
                "672",
                "BRCA1",
                "BRCA1",
                "Homo sapiens",
                "ClinVar gene summary pathogenic variants",
                "ClinVar",
                "https://example.org/clinvar/gene/672",
                "{}",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO documents
            (kind, source_id, symbol, name, organism, description, source, source_url, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            docs,
        )
        conn.execute("INSERT INTO search_index(search_index) VALUES ('rebuild')")
