"""Build the first-pass DRAG graph index from the Standard KB."""
from __future__ import annotations

import csv
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dnarag.config import BioKBConfig
from dnarag.localdb.standard import StandardDocument, StandardKB


KIND_TO_ENTITY_TYPE = {
    "hgnc_gene": "gene",
    "ncbi_gene": "gene",
    "clinvar_gene_summary": "gene",
    "clinvar_variant": "variant",
    "go_term": "go_term",
    "reactome_pathway": "pathway",
    "pubmed_article": "paper",
}


@dataclass(frozen=True, slots=True)
class GraphBuildResult:
    graph_db: Path
    node_count: int
    edge_count: int
    alias_count: int
    manifest_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_db": str(self.graph_db),
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "alias_count": self.alias_count,
            "manifest_path": str(self.manifest_path),
        }


class GraphIndexBuilder:
    def __init__(self, config: BioKBConfig):
        self.config = config
        self.standard = StandardKB(config.sqlite_path, config.manifest_path)
        self.graph_dir = config.graph_dir
        self.graph_db = config.graph_db

    def build(
        self,
        limit: int = 0,
        reactome_edge_limit: int = 200_000,
        write_sidecars: bool = True,
    ) -> GraphBuildResult:
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        if self.graph_db.exists():
            self.graph_db.unlink()
        with sqlite3.connect(self.graph_db) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(_graph_schema())
            docs = list(self.standard.iter_documents(limit=limit))
            self._insert_documents(conn, docs)
            self._insert_clinvar_gene_edges(conn)
            self._insert_reactome_edges(conn, reactome_edge_limit)
            counts = _counts(conn)
        if write_sidecars:
            self._write_sidecars()
        manifest = {
            "dataset": "dnarag_drag_graph",
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_sqlite": str(self.config.sqlite_path),
            "raw_dir": str(self.config.raw_dir),
            "limit": int(limit or 0),
            "reactome_edge_limit": int(reactome_edge_limit or 0),
            "sidecars": bool(write_sidecars),
            **counts,
        }
        manifest_path = self.graph_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return GraphBuildResult(
            graph_db=self.graph_db,
            node_count=counts["node_count"],
            edge_count=counts["edge_count"],
            alias_count=counts["alias_count"],
            manifest_path=manifest_path,
        )

    def _insert_documents(self, conn: sqlite3.Connection, docs: Iterable[StandardDocument]) -> None:
        hgnc_docs: list[StandardDocument] = []
        for doc in docs:
            if doc.kind == "hgnc_gene":
                hgnc_docs.append(doc)
            entity_type = KIND_TO_ENTITY_TYPE.get(doc.kind, "database_entry")
            node_name = doc.symbol if entity_type == "gene" and doc.symbol else doc.name or doc.symbol or doc.source_id
            _upsert_node(
                conn,
                entity_id=doc.entity_id,
                entity_type=entity_type,
                canonical_id=doc.source_id,
                name=node_name,
                source=doc.source,
                description=doc.description,
                organism=doc.organism,
                metadata={"kind": doc.kind, "payload": doc.payload, "source_url": doc.source_url},
            )
            _insert_aliases(conn, doc.entity_id, _aliases_for_document(doc), source=doc.source)
        self._insert_hgnc_xrefs(conn, hgnc_docs)

    def _insert_hgnc_xrefs(self, conn: sqlite3.Connection, docs: Iterable[StandardDocument]) -> None:
        for doc in docs:
            if doc.kind != "hgnc_gene":
                continue
            for accession in _split_list(doc.payload.get("uniprot_ids")):
                protein_id = f"protein:{accession}"
                _upsert_node(
                    conn,
                    entity_id=protein_id,
                    entity_type="protein",
                    canonical_id=accession,
                    name=accession,
                    source="UniProt",
                    description=f"UniProt cross-reference for {doc.symbol or doc.name}",
                    organism=doc.organism,
                    metadata={"xref_source": "HGNC", "gene_entity_id": doc.entity_id},
                )
                _insert_aliases(conn, protein_id, [accession], source="UniProt")
                _insert_edge(conn, doc.entity_id, "has_uniprot_xref", protein_id, source="HGNC", confidence=1.0)
            entrez_id = _clean(doc.payload.get("entrez_id"))
            if entrez_id:
                ncbi_id = f"ncbi_gene:{entrez_id}"
                _upsert_node(
                    conn,
                    entity_id=ncbi_id,
                    entity_type="gene",
                    canonical_id=entrez_id,
                    name=doc.symbol or entrez_id,
                    source="NCBI Gene",
                    description=f"NCBI Gene cross-reference for {doc.symbol or doc.name}",
                    organism=doc.organism,
                    metadata={"xref_source": "HGNC", "hgnc_entity_id": doc.entity_id},
                )
                _insert_aliases(conn, ncbi_id, [entrez_id, doc.symbol or ""], source="NCBI Gene")
                _insert_edge(conn, doc.entity_id, "has_ncbi_gene_xref", ncbi_id, source="HGNC", confidence=1.0)
            ensembl_id = _clean(doc.payload.get("ensembl_gene_id"))
            if ensembl_id:
                ensembl_entity_id = f"ensembl_gene:{ensembl_id}"
                _upsert_node(
                    conn,
                    entity_id=ensembl_entity_id,
                    entity_type="gene",
                    canonical_id=ensembl_id,
                    name=doc.symbol or ensembl_id,
                    source="Ensembl",
                    description=f"Ensembl cross-reference for {doc.symbol or doc.name}",
                    organism=doc.organism,
                    metadata={"xref_source": "HGNC", "hgnc_entity_id": doc.entity_id},
                )
                _insert_aliases(conn, ensembl_entity_id, [ensembl_id, doc.symbol or ""], source="Ensembl")
                _insert_edge(conn, doc.entity_id, "has_ensembl_xref", ensembl_entity_id, source="HGNC", confidence=1.0)

    def _insert_clinvar_gene_edges(self, conn: sqlite3.Connection) -> None:
        hgnc_by_symbol = {
            str(row["name"]).upper(): str(row["entity_id"])
            for row in conn.execute(
                """
                SELECT entity_id, name
                FROM nodes
                WHERE source = 'HGNC' AND entity_type = 'gene' AND name IS NOT NULL
                """
            )
        }
        clinvar_rows = conn.execute(
            """
            SELECT entity_id, name
            FROM nodes
            WHERE source = 'ClinVar' AND entity_type = 'gene' AND name IS NOT NULL
            """
        ).fetchall()
        for row in clinvar_rows:
            hgnc_entity_id = hgnc_by_symbol.get(str(row["name"]).upper())
            if not hgnc_entity_id:
                continue
            _insert_edge(
                conn,
                hgnc_entity_id,
                "has_clinvar_summary",
                row["entity_id"],
                source="ClinVar",
                confidence=1.0,
            )

    def _insert_reactome_edges(self, conn: sqlite3.Connection, edge_limit: int) -> None:
        mapping_path = self.config.raw_dir / "reactome" / "UniProt2Reactome_All_Levels.txt"
        if not mapping_path.exists() or edge_limit <= 0:
            return
        pathway_ids = {
            str(row["canonical_id"]): str(row["entity_id"])
            for row in conn.execute("SELECT entity_id, canonical_id FROM nodes WHERE entity_type = 'pathway'")
        }
        if not pathway_ids:
            return
        inserted = 0
        with mapping_path.open("rt", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            for row in reader:
                if len(row) < 6:
                    continue
                uniprot_id, reactome_id = row[0], row[1]
                species = row[5] if len(row) > 5 else ""
                if species != "Homo sapiens" or reactome_id not in pathway_ids:
                    continue
                protein_id = f"protein:{uniprot_id}"
                _upsert_node(
                    conn,
                    entity_id=protein_id,
                    entity_type="protein",
                    canonical_id=uniprot_id,
                    name=uniprot_id,
                    source="UniProt",
                    description=f"Reactome UniProt participant {uniprot_id}",
                    organism="Homo sapiens",
                    metadata={"xref_source": "Reactome"},
                )
                _insert_aliases(conn, protein_id, [uniprot_id], source="UniProt")
                _insert_edge(
                    conn,
                    protein_id,
                    "participates_in_pathway",
                    pathway_ids[reactome_id],
                    source="Reactome",
                    confidence=1.0,
                    metadata={"reactome_id": reactome_id},
                )
                inserted += 1
                if inserted >= edge_limit:
                    return

    def _write_sidecars(self) -> None:
        with sqlite3.connect(self.graph_db) as conn:
            conn.row_factory = sqlite3.Row
            tables = {
                "nodes": conn.execute("SELECT * FROM nodes ORDER BY entity_id").fetchall(),
                "edges": conn.execute("SELECT * FROM edges ORDER BY source_entity_id, relation_type, target_entity_id").fetchall(),
                "entity_aliases": conn.execute("SELECT * FROM aliases ORDER BY entity_id, alias").fetchall(),
            }
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except Exception:
            for name, rows in tables.items():
                path = self.graph_dir / f"{name}.jsonl"
                with path.open("wt", encoding="utf-8") as handle:
                    for row in rows:
                        handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            return

        for name, rows in tables.items():
            data = [dict(row) for row in rows]
            table = pa.Table.from_pylist(data) if data else pa.Table.from_pylist([])
            pq.write_table(table, self.graph_dir / f"{name}.parquet")


def _graph_schema() -> str:
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
        confidence REAL,
        metadata_json TEXT,
        PRIMARY KEY (source_entity_id, relation_type, target_entity_id, source)
    );

    CREATE INDEX idx_edges_source ON edges(source_entity_id);
    CREATE INDEX idx_edges_target ON edges(target_entity_id);
    CREATE INDEX idx_edges_type ON edges(relation_type);
    """


def _upsert_node(
    conn: sqlite3.Connection,
    *,
    entity_id: str,
    entity_type: str,
    canonical_id: str | None,
    name: str | None,
    source: str | None,
    description: str | None,
    organism: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO nodes
        (entity_id, entity_type, canonical_id, name, source, description, organism, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity_id,
            entity_type,
            canonical_id,
            name,
            source,
            description,
            organism,
            json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":")),
        ),
    )


def _insert_aliases(conn: sqlite3.Connection, entity_id: str, aliases: Iterable[str], source: str | None) -> None:
    for alias in aliases:
        clean_alias = _clean(alias)
        if not clean_alias:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO aliases (entity_id, alias, alias_type, source)
            VALUES (?, ?, ?, ?)
            """,
            (entity_id, clean_alias, "xref" if ":" in clean_alias else "name", source),
        )


def _insert_edge(
    conn: sqlite3.Connection,
    source_entity_id: str,
    relation_type: str,
    target_entity_id: str,
    *,
    source: str | None,
    confidence: float | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO edges
        (source_entity_id, relation_type, target_entity_id, source, confidence, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            source_entity_id,
            relation_type,
            target_entity_id,
            source,
            confidence,
            json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":")),
        ),
    )


def _aliases_for_document(doc: StandardDocument) -> list[str]:
    aliases = [doc.source_id, doc.symbol or "", doc.name or ""]
    payload = doc.payload
    aliases.extend(_split_list(payload.get("alias_symbol")))
    aliases.extend(_split_list(payload.get("uniprot_ids")))
    aliases.extend(_split_list(payload.get("omim_id")))
    aliases.extend(_split_list(payload.get("entrez_id")))
    aliases.extend(_split_list(payload.get("ensembl_gene_id")))
    return aliases


def _split_list(value: Any) -> list[str]:
    if value in {None, ""}:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = str(value).replace("|", ",").split(",")
    return [item.strip() for item in items if _clean(item)]


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text != "-" else None


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "node_count": int(conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]),
        "edge_count": int(conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]),
        "alias_count": int(conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]),
    }
