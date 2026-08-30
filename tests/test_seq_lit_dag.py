import sqlite3
from pathlib import Path

from dnarag.config import BioKBConfig
from dnarag.seq_lit_dag.build import SeqLitDagBuilder, load_pubmed_cache, parse_gaf_line, parse_swissprot_header
from dnarag.seq_lit_dag.evaluate import evaluate_sequence_to_paper


def test_gaf_parser_extracts_pmids_and_accession():
    line = (
        "UniProtKB\tA0A024RBG1\tNUDT4B\tenables\tGO:0005515\t"
        "PMID:33961781\tIPI\tUniProtKB:Q8NFP7\tF\tProtein name\t"
        "NUDT4B\tprotein\ttaxon:9606\t20260228\tIntAct\t\tUniProtKB:A0A024RBG1"
    )

    ann = parse_gaf_line(line)

    assert ann is not None
    assert ann.accession == "A0A024RBG1"
    assert ann.pmids == ("33961781",)
    assert ann.evidence_code == "IPI"


def test_swissprot_header_parser_extracts_core_metadata():
    header = (
        "sp|P38398|BRCA1_HUMAN Breast cancer type 1 susceptibility protein "
        "OS=Homo sapiens OX=9606 GN=BRCA1 PE=1 SV=2"
    )

    metadata = parse_swissprot_header(header)

    assert metadata["protein_name"] == "Breast cancer type 1 susceptibility protein"
    assert metadata["organism"] == "Homo sapiens"
    assert metadata["taxon_id"] == "9606"
    assert metadata["gene_symbol"] == "BRCA1"


def test_seq_lit_dag_builder_writes_core_path(tmp_path: Path):
    raw = tmp_path / "raw"
    index = tmp_path / "index"
    (raw / "go").mkdir(parents=True)
    (raw / "pubmed" / "baseline").mkdir(parents=True)
    (index / "blast").mkdir(parents=True)

    (index / "blast" / "swissprot.fasta").write_text(
        ">sp|P38398|BRCA1_HUMAN Breast cancer type 1 susceptibility protein OS=Homo sapiens OX=9606 GN=BRCA1 PE=1 SV=2\n"
        "M" + "A" * 180 + "\n",
        encoding="utf-8",
    )
    (raw / "go" / "goa_human.gaf").write_text(
        "UniProtKB\tP38398\tBRCA1\tinvolved_in\tGO:0006281\t"
        "PMID:12345\tIDA\t\tP\tBreast cancer type 1 susceptibility protein\t"
        "BRCAI\tprotein\ttaxon:9606\t20260101\tUniProt\t\tUniProtKB:P38398\n",
        encoding="utf-8",
    )
    (raw / "go" / "go-basic.obo").write_text(
        "[Term]\n"
        "id: GO:0006281\n"
        "name: DNA repair\n"
        "namespace: biological_process\n"
        "def: \"The process of restoring DNA.\"\n",
        encoding="utf-8",
    )

    config = BioKBConfig(
        root=tmp_path,
        raw_dir=raw,
        index_dir=index,
        sqlite_path=index / "open_rosalind_standard.sqlite",
        manifest_path=index / "manifest.json",
        blast_fasta=index / "blast" / "swissprot.fasta",
        graph_dir=index / "graph",
        vector_dir=index / "vector",
    )

    result = SeqLitDagBuilder(config).build(
        output_dir=tmp_path / "seq_lit",
        limit_proteins=1,
        pubmed_xml_limit=0,
    )

    assert result.node_count >= 5
    assert result.edge_count >= 5
    with sqlite3.connect(result.graph_db) as conn:
        path_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM edges
            WHERE source_entity_id = 'protein:P38398'
              AND relation_type = 'supported_by_paper'
              AND target_entity_id = 'paper:PMID:12345'
            """
        ).fetchone()[0]
    assert path_count == 1


def test_pubmed_jsonl_cache_loader(tmp_path: Path):
    cache = tmp_path / "pubmed.jsonl"
    cache.write_text(
        '{"pmid":"12345","title":"DNA repair study","year":"2025","journal":"Test Journal"}\n',
        encoding="utf-8",
    )

    records = load_pubmed_cache(cache, wanted_pmids={"12345"})

    assert records["12345"].title == "DNA repair study"
    assert records["12345"].year == "2025"


def test_builder_preserves_cache_inside_reset_output(tmp_path: Path):
    raw = tmp_path / "raw"
    index = tmp_path / "index"
    output = tmp_path / "seq_lit"
    (raw / "go").mkdir(parents=True)
    (raw / "pubmed" / "baseline").mkdir(parents=True)
    (index / "blast").mkdir(parents=True)
    output.mkdir()
    (index / "blast" / "swissprot.fasta").write_text(
        ">sp|P1|P1_HUMAN Protein one OS=Homo sapiens OX=9606 GN=P1 PE=1 SV=1\n" + "M" + "A" * 40 + "\n",
        encoding="utf-8",
    )
    (raw / "go" / "goa_human.gaf").write_text(
        "UniProtKB\tP1\tP1\tinvolved_in\tGO:0000001\tPMID:12345\tIDA\t\tP\tProtein one\t\tprotein\ttaxon:9606\t20260101\tUniProt\t\tUniProtKB:P1\n",
        encoding="utf-8",
    )
    (raw / "go" / "go-basic.obo").write_text("[Term]\nid: GO:0000001\nname: test process\n", encoding="utf-8")
    cache = output / "pubmed_metadata.jsonl"
    cache.write_text('{"pmid":"12345","title":"Cached title"}\n', encoding="utf-8")
    config = BioKBConfig(
        root=tmp_path,
        raw_dir=raw,
        index_dir=index,
        sqlite_path=index / "db.sqlite",
        manifest_path=index / "manifest.json",
        blast_fasta=index / "blast" / "swissprot.fasta",
        graph_dir=index / "graph",
        vector_dir=index / "vector",
    )

    result = SeqLitDagBuilder(config).build(output_dir=output, limit_proteins=1, pubmed_cache=cache, reset=True)

    assert result.source_counts["pubmed_metadata_found"] == 1


def test_cpu_sequence_to_paper_sanity_uses_dataset_ground_truth(tmp_path: Path):
    documents = tmp_path / "documents.jsonl"
    documents.write_text(
        '{"record_id":"protein:P1","modality":"protein_sequence","accession":"P1",'
        '"text":"[TYPE=protein_sequence]\\nSequence:\\nMABCDEFGHIKLMNPQRSTVWY"}\n'
        '{"record_id":"protein:P2","modality":"protein_sequence","accession":"P2",'
        '"text":"[TYPE=protein_sequence]\\nSequence:\\nMYYYYYYYYYYYYYYYYYYYYY"}\n',
        encoding="utf-8",
    )
    queries = tmp_path / "queries.jsonl"
    queries.write_text(
        '{"id":"q1","query":"MABCDEFGHIKLMNPQRSTVWY","expected_accessions":["P1"],'
        '"expected_pmids":["12345"]}\n',
        encoding="utf-8",
    )
    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(graph) as conn:
        conn.execute("CREATE TABLE edges (source_entity_id TEXT, relation_type TEXT, target_entity_id TEXT)")
        conn.execute("INSERT INTO edges VALUES ('protein:P1', 'supported_by_paper', 'paper:PMID:12345')")

    result = evaluate_sequence_to_paper(
        queries_path=queries,
        documents_path=documents,
        graph_db=graph,
        top_k=1,
        paper_k=1,
    )

    assert result["summary"]["kmer_jaccard"]["accession_hit"] == 1.0
    assert result["summary"]["kmer_jaccard"]["paper_hit"] == 1.0
    assert "not held-out" in result["claim_scope"]
