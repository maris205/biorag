"""Build a curated protein sequence-to-literature evidence DAG."""
from __future__ import annotations

import gzip
import json
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from dnarag.config import BioKBConfig
from dnarag.seq_lit_dag.schema import graph_schema_sql, manifest_schema


DATASET_VERSION = "0.2.0"
PROTEIN_WINDOW_SIZE = 128
PROTEIN_WINDOW_STRIDE = 64
DEFAULT_EVIDENCE_CODES = {
    "EXP",
    "IDA",
    "IPI",
    "IMP",
    "IGI",
    "IEP",
    "HTP",
    "HDA",
    "HMP",
    "HGI",
    "HEP",
}


@dataclass(frozen=True, slots=True)
class ProteinRecord:
    accession: str
    entry_name: str
    header: str
    sequence: str
    protein_name: str | None
    organism: str | None
    taxon_id: str | None
    gene_symbol: str | None


@dataclass(frozen=True, slots=True)
class GoAnnotation:
    accession: str
    gene_symbol: str | None
    qualifier: str
    go_id: str
    reference: str
    evidence_code: str
    aspect: str
    protein_name: str | None
    synonyms: tuple[str, ...]
    taxon_ids: tuple[str, ...]
    assigned_by: str | None
    date: str | None

    @property
    def pmids(self) -> tuple[str, ...]:
        return tuple(sorted(set(re.findall(r"PMID:(\d+)", self.reference or ""))))


@dataclass(frozen=True, slots=True)
class GoTerm:
    go_id: str
    name: str
    namespace: str | None = None
    definition: str | None = None


@dataclass(frozen=True, slots=True)
class PubmedRecord:
    pmid: str
    title: str | None = None
    abstract: str | None = None
    year: str | None = None
    journal: str | None = None
    doi: str | None = None


@dataclass(slots=True)
class SeqLitDagBuildResult:
    output_dir: Path
    graph_db: Path
    manifest_path: Path
    report_path: Path
    node_count: int
    edge_count: int
    document_count: int
    sample_query_count: int
    source_counts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "graph_db": str(self.graph_db),
            "manifest_path": str(self.manifest_path),
            "report_path": str(self.report_path),
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "document_count": self.document_count,
            "sample_query_count": self.sample_query_count,
            "source_counts": self.source_counts,
        }


class SeqLitDagBuilder:
    """CPU-only builder for the first curated sequence-literature DAG."""

    def __init__(self, config: BioKBConfig):
        self.config = config
        self.raw_dir = config.raw_dir

    def build(
        self,
        *,
        output_dir: str | Path,
        limit_proteins: int = 200,
        min_pubmed_per_protein: int = 1,
        max_go_annotations_per_protein: int = 8,
        max_windows_per_protein: int = 2,
        pubmed_xml_limit: int = 0,
        pubmed_cache: str | Path | None = None,
        reset: bool = False,
    ) -> SeqLitDagBuildResult:
        output = Path(output_dir)
        cached_pubmed_records = load_pubmed_cache(Path(pubmed_cache)) if pubmed_cache else {}
        if reset and output.exists():
            _reset_generated_dir(output)
        output.mkdir(parents=True, exist_ok=True)

        source_paths = self._source_paths()
        go_terms = parse_go_obo(source_paths["go_obo"])
        selected_annotations = select_goa_annotations(
            source_paths["goa_human"],
            limit_proteins=limit_proteins,
            min_pubmed_per_protein=min_pubmed_per_protein,
            max_go_annotations_per_protein=max_go_annotations_per_protein,
        )
        selected_accessions = set(selected_annotations)
        proteins = parse_swissprot_fasta(source_paths["swissprot_fasta"], selected_accessions)
        missing_sequence = sorted(selected_accessions - set(proteins))
        selected_accessions = set(proteins)
        selected_annotations = {
            accession: annotations
            for accession, annotations in selected_annotations.items()
            if accession in selected_accessions
        }
        pmids = sorted({pmid for annotations in selected_annotations.values() for ann in annotations for pmid in ann.pmids})
        pubmed_records = {
            pmid: record for pmid, record in cached_pubmed_records.items() if pmid in set(pmids)
        }
        baseline_records = parse_pubmed_baseline(
            source_paths["pubmed_baseline"],
            wanted_pmids=set(pmids) - set(pubmed_records),
            xml_limit=pubmed_xml_limit,
        )
        pubmed_records.update(baseline_records)

        graph_db = output / "graph.sqlite"
        if graph_db.exists():
            graph_db.unlink()
        with sqlite3.connect(graph_db) as conn:
            conn.executescript(graph_schema_sql())
            write_graph(
                conn,
                proteins=proteins,
                annotations=selected_annotations,
                go_terms=go_terms,
                pubmed_records=pubmed_records,
                max_windows_per_protein=max_windows_per_protein,
            )
            counts = _counts(conn)

        sidecar_counts = write_sidecars(output, graph_db)
        document_count = write_documents(
            output / "documents.jsonl",
            proteins=proteins,
            annotations=selected_annotations,
            go_terms=go_terms,
            pubmed_records=pubmed_records,
        )
        sample_query_count = write_sample_queries(
            output / "sample_queries.jsonl",
            proteins=proteins,
            annotations=selected_annotations,
            go_terms=go_terms,
            limit=50,
        )
        schema_path = output / "schema.json"
        schema_path.write_text(json.dumps(manifest_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        source_counts = {
            "selected_proteins": len(proteins),
            "selected_go_annotations": sum(len(items) for items in selected_annotations.values()),
            "selected_pmids": len(pmids),
            "pubmed_metadata_found": len(pubmed_records),
            "missing_sequence_accessions": len(missing_sequence),
            "go_terms_loaded": len(go_terms),
            **sidecar_counts,
        }
        manifest = {
            "dataset": "BioRAG-SeqLit-DAG",
            "version": DATASET_VERSION,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "description": (
                "Curated protein sequence-to-literature evidence DAG built from "
                "Swiss-Prot FASTA, GOA human annotations, GO terms, and local PubMed metadata."
            ),
            "config": {
                "limit_proteins": int(limit_proteins),
                "min_pubmed_per_protein": int(min_pubmed_per_protein),
                "max_go_annotations_per_protein": int(max_go_annotations_per_protein),
                "max_windows_per_protein": int(max_windows_per_protein),
                "pubmed_xml_limit": int(pubmed_xml_limit),
                "pubmed_cache": str(pubmed_cache) if pubmed_cache else None,
            },
            "source_files": {key: str(value) for key, value in source_paths.items()},
            "files": {
                "graph_sqlite": str(graph_db),
                "nodes_jsonl": str(output / "nodes.jsonl"),
                "edges_jsonl": str(output / "edges.jsonl"),
                "aliases_jsonl": str(output / "aliases.jsonl"),
                "documents_jsonl": str(output / "documents.jsonl"),
                "sample_queries_jsonl": str(output / "sample_queries.jsonl"),
                "schema_json": str(schema_path),
            },
            "counts": {
                **counts,
                "document_count": document_count,
                "sample_query_count": sample_query_count,
                **source_counts,
            },
            "dag_view": "query_sequence -> protein_candidate -> go_term/evidence -> paper",
            "gpu_required": False,
            "gpu_note": "GPU is only required for large embedding refreshes or FAISS GPU benchmarking.",
        }
        manifest_path = output / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report_path = output / "REPORT.md"
        report_path.write_text(render_report(manifest, proteins, selected_annotations, go_terms, pubmed_records), encoding="utf-8")

        return SeqLitDagBuildResult(
            output_dir=output,
            graph_db=graph_db,
            manifest_path=manifest_path,
            report_path=report_path,
            node_count=counts["node_count"],
            edge_count=counts["edge_count"],
            document_count=document_count,
            sample_query_count=sample_query_count,
            source_counts=source_counts,
        )

    def _source_paths(self) -> dict[str, Path]:
        swissprot_fasta = self.config.blast_fasta
        if not swissprot_fasta.exists():
            swissprot_fasta = self.raw_dir / "blast" / "swissprot.gz"
        goa_human = self.raw_dir / "go" / "goa_human.gaf.gz"
        if not goa_human.exists():
            goa_human = self.raw_dir / "go" / "goa_human.gaf"
        return {
            "swissprot_fasta": swissprot_fasta,
            "goa_human": goa_human,
            "go_obo": self.raw_dir / "go" / "go-basic.obo",
            "pubmed_baseline": self.raw_dir / "pubmed" / "baseline",
        }


def select_goa_annotations(
    path: Path,
    *,
    limit_proteins: int,
    min_pubmed_per_protein: int,
    max_go_annotations_per_protein: int,
    evidence_codes: set[str] | None = None,
) -> dict[str, list[GoAnnotation]]:
    selected: dict[str, list[GoAnnotation]] = {}
    pmids_by_accession: dict[str, set[str]] = defaultdict(set)
    allowed_evidence = evidence_codes or DEFAULT_EVIDENCE_CODES
    with _open_text(path) as handle:
        for line in handle:
            if not line.strip() or line.startswith("!"):
                continue
            ann = parse_gaf_line(line)
            if ann is None or not ann.pmids:
                continue
            if ann.evidence_code not in allowed_evidence:
                continue
            if ann.qualifier.startswith("NOT") or "NOT|" in ann.qualifier:
                continue
            accession = normalize_accession(ann.accession)
            if accession not in selected and limit_proteins and len(selected) >= limit_proteins:
                continue
            current = selected.setdefault(accession, [])
            if len(current) >= max_go_annotations_per_protein:
                continue
            current.append(ann)
            pmids_by_accession[accession].update(ann.pmids)
    return {
        accession: annotations
        for accession, annotations in selected.items()
        if len(pmids_by_accession[accession]) >= min_pubmed_per_protein
    }


def parse_gaf_line(line: str) -> GoAnnotation | None:
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 15 or parts[0] != "UniProtKB":
        return None
    synonyms = tuple(item for item in parts[10].split("|") if item) if len(parts) > 10 else ()
    taxon_ids = tuple(item.replace("taxon:", "") for item in parts[12].split("|") if item) if len(parts) > 12 else ()
    return GoAnnotation(
        accession=normalize_accession(parts[1]),
        gene_symbol=_clean(parts[2]),
        qualifier=_clean(parts[3]) or "",
        go_id=parts[4],
        reference=parts[5],
        evidence_code=parts[6],
        aspect=parts[8] if len(parts) > 8 else "",
        protein_name=_clean(parts[9]) if len(parts) > 9 else None,
        synonyms=synonyms,
        taxon_ids=taxon_ids,
        assigned_by=_clean(parts[14]) if len(parts) > 14 else None,
        date=_clean(parts[13]) if len(parts) > 13 else None,
    )


def parse_swissprot_fasta(path: Path, wanted_accessions: set[str]) -> dict[str, ProteinRecord]:
    proteins: dict[str, ProteinRecord] = {}
    for header, sequence in iter_fasta(path):
        accession, entry_name = accession_and_entry_from_header(header)
        normalized = normalize_accession(accession)
        if normalized not in wanted_accessions:
            continue
        metadata = parse_swissprot_header(header)
        proteins[normalized] = ProteinRecord(
            accession=normalized,
            entry_name=entry_name,
            header=header,
            sequence=clean_sequence(sequence),
            protein_name=metadata.get("protein_name"),
            organism=metadata.get("organism"),
            taxon_id=metadata.get("taxon_id"),
            gene_symbol=metadata.get("gene_symbol"),
        )
        if len(proteins) >= len(wanted_accessions):
            break
    return proteins


def parse_go_obo(path: Path) -> dict[str, GoTerm]:
    terms: dict[str, GoTerm] = {}
    current: dict[str, str] = {}
    with path.open("rt", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if line == "[Term]":
                _flush_go_term(current, terms)
                current = {}
                continue
            if not line:
                continue
            if line.startswith("id: "):
                current["id"] = line.removeprefix("id: ").strip()
            elif line.startswith("name: "):
                current["name"] = line.removeprefix("name: ").strip()
            elif line.startswith("namespace: "):
                current["namespace"] = line.removeprefix("namespace: ").strip()
            elif line.startswith("def: "):
                current["definition"] = line.removeprefix("def: ").strip()
    _flush_go_term(current, terms)
    return terms


def parse_pubmed_baseline(path: Path, *, wanted_pmids: set[str], xml_limit: int = 0) -> dict[str, PubmedRecord]:
    if not wanted_pmids or not path.exists() or xml_limit <= 0:
        return {}
    records: dict[str, PubmedRecord] = {}
    files = sorted(path.glob("*.xml.gz"))
    files = files[:xml_limit]
    for xml_path in files:
        try:
            with gzip.open(xml_path, "rt", encoding="utf-8", errors="replace") as handle:
                for _event, elem in ET.iterparse(handle, events=("end",)):
                    if elem.tag != "PubmedArticle":
                        continue
                    record = pubmed_record_from_xml(elem)
                    if record and record.pmid in wanted_pmids:
                        records[record.pmid] = record
                    elem.clear()
                    if len(records) >= len(wanted_pmids):
                        return records
        except (OSError, ET.ParseError):
            continue
    return records


def load_pubmed_cache(path: Path, *, wanted_pmids: set[str] | None = None) -> dict[str, PubmedRecord]:
    """Load the compact JSONL cache produced by fetch_pubmed_metadata.py."""
    if not path.exists():
        raise FileNotFoundError(f"PubMed metadata cache not found: {path}")
    records: dict[str, PubmedRecord] = {}
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            pmid = str(row.get("pmid") or "").strip()
            if not pmid or (wanted_pmids is not None and pmid not in wanted_pmids):
                continue
            records[pmid] = PubmedRecord(
                pmid=pmid,
                title=_clean(row.get("title")),
                abstract=_clean(row.get("abstract")),
                year=_clean(row.get("year")),
                journal=_clean(row.get("journal")),
                doi=_clean(row.get("doi")),
            )
    return records


def write_graph(
    conn: sqlite3.Connection,
    *,
    proteins: dict[str, ProteinRecord],
    annotations: dict[str, list[GoAnnotation]],
    go_terms: dict[str, GoTerm],
    pubmed_records: dict[str, PubmedRecord],
    max_windows_per_protein: int,
) -> None:
    organism_nodes: set[str] = set()
    gene_nodes: set[str] = set()
    for accession, protein in proteins.items():
        taxon_id = protein.taxon_id or first_taxon_id(annotations.get(accession, []))
        organism = protein.organism or ("Homo sapiens" if taxon_id == "9606" else None)
        gene_symbol = protein.gene_symbol or first_gene_symbol(annotations.get(accession, []))
        protein_id = protein_node_id(accession)
        upsert_node(
            conn,
            protein_id,
            "protein",
            accession,
            protein.protein_name or accession,
            "UniProtKB Swiss-Prot",
            f"Reviewed Swiss-Prot protein sequence, length {len(protein.sequence)}.",
            organism,
            {
                "entry_name": protein.entry_name,
                "header": protein.header,
                "length": len(protein.sequence),
                "taxon_id": taxon_id,
                "gene_symbol": gene_symbol,
            },
        )
        insert_aliases(conn, protein_id, [accession, protein.entry_name, gene_symbol or "", protein.protein_name or ""], "UniProtKB")
        if taxon_id and taxon_id not in organism_nodes:
            organism_nodes.add(taxon_id)
            upsert_node(conn, organism_node_id(taxon_id), "organism", taxon_id, organism or f"taxon:{taxon_id}", "NCBI Taxonomy", None, organism, {})
        if taxon_id:
            insert_edge(conn, protein_id, "from_organism", organism_node_id(taxon_id), "UniProtKB", 1.0, {"taxon_id": taxon_id})
        if gene_symbol:
            gene_nodes.add(gene_symbol)
            upsert_node(conn, gene_node_id(gene_symbol), "gene", gene_symbol, gene_symbol, "GOA/UniProtKB", None, organism, {"taxon_id": taxon_id})
            insert_aliases(conn, gene_node_id(gene_symbol), [gene_symbol], "GOA/UniProtKB")
            insert_edge(conn, protein_id, "encoded_by", gene_node_id(gene_symbol), "GOA/UniProtKB", 1.0, {})
            if taxon_id:
                insert_edge(conn, gene_node_id(gene_symbol), "from_organism", organism_node_id(taxon_id), "GOA/UniProtKB", 1.0, {"taxon_id": taxon_id})

        for index, (start, end, window) in enumerate(sequence_windows(protein.sequence, max_windows_per_protein)):
            window_id = protein_window_node_id(accession, start, end)
            upsert_node(
                conn,
                window_id,
                "protein_window",
                f"{accession}:{start + 1}-{end}",
                f"{accession} window {start + 1}-{end}",
                "UniProtKB Swiss-Prot",
                window,
                organism,
                {"parent_accession": accession, "window_start": start, "window_end": end, "window_index": index},
            )
            insert_edge(conn, protein_id, "has_window", window_id, "BioRAG-SeqLit-DAG", 1.0, {"window_start": start, "window_end": end})

    for accession, protein_annotations in annotations.items():
        protein_id = protein_node_id(accession)
        for index, ann in enumerate(protein_annotations):
            go_id = ann.go_id
            term = go_terms.get(go_id)
            go_node = go_node_id(go_id)
            upsert_node(
                conn,
                go_node,
                "go_term",
                go_id,
                term.name if term else go_id,
                "Gene Ontology",
                term.definition if term else None,
                None,
                {"namespace": term.namespace if term else None, "aspect": ann.aspect},
            )
            insert_aliases(conn, go_node, [go_id, term.name if term else ""], "Gene Ontology")
            evidence_id = evidence_node_id(accession, go_id, ann.evidence_code, index)
            evidence_text = evidence_description(accession, ann, term)
            upsert_node(
                conn,
                evidence_id,
                "evidence",
                evidence_id,
                f"{accession} {ann.evidence_code} {go_id}",
                "GOA",
                evidence_text,
                "Homo sapiens" if "9606" in ann.taxon_ids else None,
                {
                    "accession": accession,
                    "go_id": go_id,
                    "qualifier": ann.qualifier,
                    "evidence_code": ann.evidence_code,
                    "assigned_by": ann.assigned_by,
                    "date": ann.date,
                    "references": ann.reference,
                    "pmids": list(ann.pmids),
                },
            )
            provenance = {
                "accession": accession,
                "go_id": go_id,
                "evidence_code": ann.evidence_code,
                "assigned_by": ann.assigned_by,
                "date": ann.date,
                "references": ann.reference,
            }
            insert_edge(
                conn,
                protein_id,
                "annotated_with_go",
                go_node,
                "GOA",
                1.0,
                {**provenance, "qualifier": ann.qualifier},
                source_record=evidence_id,
            )
            insert_edge(
                conn,
                protein_id,
                "has_evidence",
                evidence_id,
                "GOA",
                1.0,
                provenance,
                source_record=evidence_id,
            )
            insert_edge(
                conn,
                evidence_id,
                "evidence_for_go",
                go_node,
                "GOA",
                1.0,
                {**provenance, "qualifier": ann.qualifier},
                source_record=evidence_id,
            )
            for pmid in ann.pmids:
                paper = pubmed_records.get(pmid)
                paper_id = paper_node_id(pmid)
                upsert_node(
                    conn,
                    paper_id,
                    "paper",
                    pmid,
                    paper.title if paper and paper.title else f"PubMed {pmid}",
                    "PubMed",
                    paper.abstract if paper else None,
                    None,
                    {
                        "pmid": pmid,
                        "year": paper.year if paper else None,
                        "journal": paper.journal if paper else None,
                        "doi": paper.doi if paper else None,
                        "metadata_status": "found" if paper else "pmid_only",
                    },
                )
                insert_aliases(conn, paper_id, [pmid, f"PMID:{pmid}", paper.doi if paper else ""], "PubMed")
                insert_edge(
                    conn,
                    evidence_id,
                    "supported_by_paper",
                    paper_id,
                    "GOA",
                    1.0,
                    {**provenance, "pmid": pmid},
                    source_record=evidence_id,
                )
                insert_edge(
                    conn,
                    go_node,
                    "supported_by_paper",
                    paper_id,
                    "GOA",
                    1.0,
                    {**provenance, "pmid": pmid},
                    source_record=evidence_id,
                )
                insert_edge(
                    conn,
                    protein_id,
                    "supported_by_paper",
                    paper_id,
                    "GOA",
                    1.0,
                    {**provenance, "pmid": pmid},
                    source_record=evidence_id,
                )


def write_sidecars(output: Path, graph_db: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with sqlite3.connect(graph_db) as conn:
        conn.row_factory = sqlite3.Row
        for table_name, output_name in (("nodes", "nodes.jsonl"), ("edges", "edges.jsonl"), ("aliases", "aliases.jsonl")):
            rows = conn.execute(f"SELECT * FROM {table_name} ORDER BY 1, 2").fetchall()
            counts[f"{table_name}_sidecar_records"] = len(rows)
            path = output / output_name
            with path.open("wt", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    return counts


def write_documents(
    path: Path,
    *,
    proteins: dict[str, ProteinRecord],
    annotations: dict[str, list[GoAnnotation]],
    go_terms: dict[str, GoTerm],
    pubmed_records: dict[str, PubmedRecord],
) -> int:
    count = 0
    with path.open("wt", encoding="utf-8") as handle:
        for accession, protein in proteins.items():
            anns = annotations.get(accession, [])
            go_labels = [go_terms[ann.go_id].name for ann in anns if ann.go_id in go_terms]
            pmids = sorted({pmid for ann in anns for pmid in ann.pmids})
            record = {
                "id": f"seq_lit:protein:{accession}",
                "record_id": protein_node_id(accession),
                "modality": "protein_sequence",
                "partition": "seq_lit_dag/protein",
                "source": "UniProtKB Swiss-Prot",
                "accession": accession,
                "symbol": protein.gene_symbol or first_gene_symbol(anns),
                "name": protein.protein_name,
                "organism": protein.organism,
                "text": "\n".join(
                    [
                        "[TYPE=protein_sequence]",
                        f"Accession: {accession}",
                        f"Protein: {protein.protein_name or accession}",
                        f"Gene: {protein.gene_symbol or first_gene_symbol(anns) or ''}",
                        f"Organism: {protein.organism or ''}",
                        f"GO: {'; '.join(go_labels[:8])}",
                        "Sequence:",
                        protein.sequence[:1200],
                    ]
                ),
                "labels": {"go_ids": sorted({ann.go_id for ann in anns}), "pmids": pmids},
                "metadata": {"length": len(protein.sequence), "entry_name": protein.entry_name},
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

            for ann_index, ann in enumerate(anns):
                term = go_terms.get(ann.go_id)
                for pmid in ann.pmids:
                    paper = pubmed_records.get(pmid)
                    mixed = {
                        "id": f"seq_lit:path:{accession}:{ann.go_id}:{ann.evidence_code}:{ann_index + 1}:{pmid}",
                        "record_id": evidence_node_id(accession, ann.go_id, ann.evidence_code, ann_index),
                        "modality": "mixed",
                        "partition": "seq_lit_dag/evidence_path",
                        "source": "GOA",
                        "accession": accession,
                        "symbol": ann.gene_symbol,
                        "name": protein.protein_name or ann.protein_name,
                        "organism": protein.organism,
                        "text": compact_text(
                            [
                                "[TYPE=sequence_literature_evidence_path]",
                                f"Protein sequence accession {accession} ({protein.protein_name or ann.protein_name or accession})",
                                f"is annotated with {ann.qualifier} {ann.go_id} {term.name if term else ''}",
                                f"using GO evidence code {ann.evidence_code}",
                                f"and is supported by PMID:{pmid}.",
                                f"Paper title: {paper.title}" if paper and paper.title else "",
                                f"Abstract: {paper.abstract}" if paper and paper.abstract else "",
                            ]
                        ),
                        "labels": {"go_ids": [ann.go_id], "pmids": [pmid], "evidence_codes": [ann.evidence_code]},
                        "metadata": {"qualifier": ann.qualifier, "go_name": term.name if term else None},
                    }
                    handle.write(json.dumps(mixed, ensure_ascii=False) + "\n")
                    count += 1
    return count


def write_sample_queries(
    path: Path,
    *,
    proteins: dict[str, ProteinRecord],
    annotations: dict[str, list[GoAnnotation]],
    go_terms: dict[str, GoTerm],
    limit: int,
) -> int:
    count = 0
    with path.open("wt", encoding="utf-8") as handle:
        for accession, protein in proteins.items():
            anns = annotations.get(accession, [])
            if not anns:
                continue
            fragment = protein.sequence[: min(160, len(protein.sequence))]
            pmids = sorted({pmid for ann in anns for pmid in ann.pmids})
            go_names = [go_terms[ann.go_id].name for ann in anns if ann.go_id in go_terms]
            record = {
                "id": f"seq_lit_query:{accession}",
                "query": fragment,
                "query_type": "protein_sequence_fragment",
                "expected_accessions": [accession],
                "expected_pmids": pmids,
                "expected_go_ids": sorted({ann.go_id for ann in anns}),
                "expected_go_names": go_names[:8],
                "task": "sequence_to_literature",
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
            if limit and count >= limit:
                break
    return count


def render_report(
    manifest: dict[str, Any],
    proteins: dict[str, ProteinRecord],
    annotations: dict[str, list[GoAnnotation]],
    go_terms: dict[str, GoTerm],
    pubmed_records: dict[str, PubmedRecord],
) -> str:
    edge_counts = manifest["counts"]
    pmids = sorted({pmid for anns in annotations.values() for ann in anns for pmid in ann.pmids})
    evidence_counter = Counter(ann.evidence_code for anns in annotations.values() for ann in anns)
    aspect_counter = Counter(ann.aspect for anns in annotations.values() for ann in anns)
    example_lines: list[str] = []
    for accession, protein in list(proteins.items())[:5]:
        anns = annotations.get(accession, [])
        if not anns:
            continue
        ann = anns[0]
        term = go_terms.get(ann.go_id)
        pmid = ann.pmids[0] if ann.pmids else ""
        paper = pubmed_records.get(pmid)
        example_lines.append(
            f"- `{accession}` -> `{ann.go_id}` {term.name if term else ''} -> `PMID:{pmid}`"
            + (f" ({paper.title})" if paper and paper.title else "")
        )
    return "\n".join(
        [
            "# BioRAG-SeqLit-DAG Sample Report",
            "",
            "This CPU-built sample links protein sequences to curated GO evidence and PubMed references.",
            "",
            "## Build",
            "",
            f"- Built at: `{manifest['built_at']}`",
            f"- GPU required: `{manifest['gpu_required']}`",
            f"- Output: `{manifest['files']['graph_sqlite']}`",
            "",
            "## Counts",
            "",
            f"- Proteins: `{len(proteins)}`",
            f"- GO annotations: `{sum(len(items) for items in annotations.values())}`",
            f"- Unique PMIDs: `{len(pmids)}`",
            f"- PubMed metadata found locally: `{len(pubmed_records)}`",
            f"- Graph nodes: `{edge_counts['node_count']}`",
            f"- Graph edges: `{edge_counts['edge_count']}`",
            f"- Chroma-ready documents: `{edge_counts['document_count']}`",
            f"- Sample sequence-to-literature queries: `{edge_counts['sample_query_count']}`",
            "",
            "## Evidence Codes",
            "",
            *[f"- `{key}`: {value}" for key, value in evidence_counter.most_common()],
            "",
            "## GO Aspects",
            "",
            *[f"- `{key}`: {value}" for key, value in aspect_counter.most_common()],
            "",
            "## Example DAG Paths",
            "",
            *(example_lines or ["- No example paths generated."]),
            "",
            "## Interpretation",
            "",
            "The sample is a curated sequence-conditioned literature resource, not a full text-mined paper graph. "
            "The main paper claim should be that protein sequences can enter a reusable evidence DAG through "
            "classical sequence candidates, specialized protein embeddings, curated annotations, and PubMed references.",
            "",
        ]
    )


def iter_fasta(path: Path) -> Iterable[tuple[str, str]]:
    with _open_text(path) as handle:
        header = ""
        chunks: list[str] = []
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header and chunks:
                    yield header, "".join(chunks)
                header = line[1:]
                chunks = []
            else:
                chunks.append(line)
        if header and chunks:
            yield header, "".join(chunks)


def accession_and_entry_from_header(header: str) -> tuple[str, str]:
    token = header.split()[0]
    if "|" in token:
        parts = token.split("|")
        accession = parts[1] if len(parts) > 1 else token
        entry = parts[2] if len(parts) > 2 else accession
    else:
        accession = token
        entry = token
    return normalize_accession(accession), entry


def parse_swissprot_header(header: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    first_os = header.find(" OS=")
    if first_os >= 0:
        protein_part = header.split(maxsplit=1)[1] if len(header.split(maxsplit=1)) > 1 else ""
        protein_part = protein_part[: max(protein_part.find(" OS="), 0)].strip()
        metadata["protein_name"] = protein_part or ""
    for key, field in (("organism", "OS"), ("taxon_id", "OX"), ("gene_symbol", "GN")):
        match = re.search(rf"\b{field}=([^=]+?)(?=\s[A-Z]{{2}}=|$)", header)
        if match:
            metadata[key] = match.group(1).strip()
    return metadata


def sequence_windows(sequence: str, max_windows: int) -> Iterable[tuple[int, int, str]]:
    if max_windows <= 0 or not sequence:
        return
    length = len(sequence)
    starts = [0]
    if length > PROTEIN_WINDOW_SIZE:
        starts.append(max(0, length - PROTEIN_WINDOW_SIZE))
    seen: set[tuple[int, int]] = set()
    for start in starts:
        end = min(length, start + PROTEIN_WINDOW_SIZE)
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        yield start, end, sequence[start:end]
        if len(seen) >= max_windows:
            return


def pubmed_record_from_xml(elem: ET.Element) -> PubmedRecord | None:
    pmid = _xml_text(elem.find(".//PMID"))
    if not pmid:
        return None
    title = compact_text(_iter_texts(elem.findall(".//ArticleTitle")))
    abstract = compact_text(_iter_texts(elem.findall(".//AbstractText")))
    journal = _xml_text(elem.find(".//Journal/Title")) or _xml_text(elem.find(".//MedlineTA"))
    year = _xml_text(elem.find(".//PubDate/Year"))
    doi = None
    for article_id in elem.findall(".//ArticleId"):
        if article_id.attrib.get("IdType") == "doi" and article_id.text:
            doi = article_id.text.strip()
            break
    return PubmedRecord(
        pmid=pmid,
        title=title or None,
        abstract=abstract or None,
        year=year,
        journal=journal,
        doi=doi,
    )


def _iter_texts(elements: Iterable[ET.Element]) -> Iterable[str]:
    for elem in elements:
        text = "".join(elem.itertext()).strip()
        if text:
            yield text


def _xml_text(elem: ET.Element | None) -> str | None:
    if elem is None or elem.text is None:
        return None
    return elem.text.strip() or None


def _flush_go_term(current: dict[str, str], terms: dict[str, GoTerm]) -> None:
    go_id = current.get("id")
    if not go_id or "name" not in current:
        return
    terms[go_id] = GoTerm(
        go_id=go_id,
        name=current["name"],
        namespace=current.get("namespace"),
        definition=current.get("definition"),
    )


def evidence_description(accession: str, ann: GoAnnotation, term: GoTerm | None) -> str:
    parts = [
        f"Protein {accession}",
        f"{ann.qualifier} {ann.go_id}",
        term.name if term else "",
        f"with GO evidence code {ann.evidence_code}",
        f"supported by {', '.join('PMID:' + pmid for pmid in ann.pmids)}" if ann.pmids else "",
    ]
    return compact_text(parts)


def upsert_node(
    conn: sqlite3.Connection,
    entity_id: str,
    entity_type: str,
    canonical_id: str | None,
    name: str | None,
    source: str | None,
    description: str | None,
    organism: str | None,
    metadata: dict[str, Any] | None,
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


def insert_aliases(conn: sqlite3.Connection, entity_id: str, aliases: Iterable[str | None], source: str | None) -> None:
    for alias in aliases:
        cleaned = _clean(alias)
        if not cleaned:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO aliases (entity_id, alias, alias_type, source)
            VALUES (?, ?, ?, ?)
            """,
            (entity_id, cleaned, "xref" if ":" in cleaned else "name", source),
        )


def insert_edge(
    conn: sqlite3.Connection,
    source_entity_id: str,
    relation_type: str,
    target_entity_id: str,
    source: str | None,
    confidence: float | None,
    metadata: dict[str, Any] | None,
    *,
    source_record: str | None = None,
    evidence_level: str | None = None,
    retrieval_score: float | None = None,
    verification_method: str | None = None,
    database_version: str | None = None,
) -> None:
    edge_metadata = metadata or {}
    source_record = source_record or _edge_source_record(source_entity_id, edge_metadata)
    evidence_level = evidence_level or _edge_evidence_level(source, edge_metadata)
    verification_method = verification_method or _edge_verification_method(source, edge_metadata)
    database_version = database_version or _edge_database_version(source, edge_metadata)
    conn.execute(
        """
        INSERT OR IGNORE INTO edges
        (source_entity_id, relation_type, target_entity_id, source, source_record,
         evidence_level, confidence, retrieval_score, verification_method,
         database_version, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_entity_id,
            relation_type,
            target_entity_id,
            source,
            source_record,
            evidence_level,
            confidence,
            retrieval_score,
            verification_method,
            database_version,
            json.dumps(edge_metadata, ensure_ascii=False, separators=(",", ":")),
        ),
    )


def _edge_source_record(source_entity_id: str, metadata: dict[str, Any]) -> str:
    references = str(metadata.get("references") or "").strip()
    if references:
        return references
    return source_entity_id


def _edge_evidence_level(source: str | None, metadata: dict[str, Any]) -> str:
    normalized = (source or "").lower()
    if "blast" in normalized:
        return "alignment_verified"
    if "vector" in normalized or "dense" in normalized:
        return "retrieved_unverified"
    if metadata.get("evidence_code"):
        return "curated_experimental_annotation"
    if any(token in normalized for token in ("goa", "uniprot", "ontology", "taxonomy", "pubmed")):
        return "curated_database_assertion"
    return "derived_dataset_edge"


def _edge_verification_method(source: str | None, metadata: dict[str, Any]) -> str:
    normalized = (source or "").lower()
    if "blast" in normalized:
        return "sequence_alignment"
    if "vector" in normalized or "dense" in normalized:
        return "dense_similarity_only"
    evidence_code = str(metadata.get("evidence_code") or "").strip()
    if evidence_code:
        return f"GOA:{evidence_code}"
    if any(token in normalized for token in ("goa", "uniprot", "ontology", "taxonomy", "pubmed")):
        return "curated_record"
    return "dataset_construction_rule"


def _edge_database_version(source: str | None, metadata: dict[str, Any]) -> str:
    record_date = str(metadata.get("date") or "").strip()
    source_name = (source or "local").replace(" ", "_")
    if record_date:
        return f"{source_name}@record-date-{record_date}"
    return f"{source_name}@local-snapshot"


def protein_node_id(accession: str) -> str:
    return f"protein:{normalize_accession(accession)}"


def protein_window_node_id(accession: str, start: int, end: int) -> str:
    return f"protein_window:{normalize_accession(accession)}:{start + 1}-{end}"


def go_node_id(go_id: str) -> str:
    return f"go_term:{go_id}"


def paper_node_id(pmid: str) -> str:
    return f"paper:PMID:{pmid}"


def evidence_node_id(accession: str, go_id: str, evidence_code: str, index: int) -> str:
    safe_go = go_id.replace(":", "_")
    return f"evidence:{normalize_accession(accession)}:{safe_go}:{evidence_code}:{index + 1}"


def organism_node_id(taxon_id: str) -> str:
    return f"organism:taxon:{taxon_id}"


def gene_node_id(symbol: str) -> str:
    return f"gene:{symbol.upper()}"


def first_gene_symbol(annotations: list[GoAnnotation] | None) -> str | None:
    for ann in annotations or []:
        if ann.gene_symbol:
            return ann.gene_symbol
    return None


def first_taxon_id(annotations: list[GoAnnotation] | None) -> str | None:
    for ann in annotations or []:
        for taxon_id in ann.taxon_ids:
            if taxon_id:
                return taxon_id
    return None


def normalize_accession(accession: str) -> str:
    token = str(accession or "").strip()
    if "|" in token:
        parts = token.split("|")
        token = parts[1] if len(parts) > 1 else token
    return token.split(".", 1)[0]


def clean_sequence(sequence: str) -> str:
    return "".join(ch for ch in str(sequence or "").upper() if ch.isalpha() or ch == "*")


def compact_text(parts: Iterable[str | None]) -> str:
    return " ".join(str(part).strip() for part in parts if _clean(part))


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text != "-" else None


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("rt", encoding="utf-8", errors="replace")


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "node_count": int(conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]),
        "edge_count": int(conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]),
        "alias_count": int(conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]),
    }


def _reset_generated_dir(path: Path) -> None:
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            _reset_generated_dir(child)
            child.rmdir()
        else:
            child.unlink()
