import sqlite3
from pathlib import Path

import numpy as np
import pytest

from dnarag.config import BioKBConfig
from dnarag.localdb.graph import GraphStore
from dnarag.localdb.view_graph import VectorViewGraphBuilder
from dnarag.retrieval.vector_db import ChromaVectorDB


def test_build_text_style_view_graph_from_chroma(tmp_path: Path):
    pytest.importorskip("chromadb")
    config = BioKBConfig(
        root=tmp_path,
        raw_dir=tmp_path / "raw",
        index_dir=tmp_path / "index",
        sqlite_path=tmp_path / "index" / "open_rosalind_standard.sqlite",
        manifest_path=tmp_path / "index" / "manifest.json",
        graph_dir=tmp_path / "index" / "graph",
        vector_dir=tmp_path / "index" / "vector",
    )
    vector_db = ChromaVectorDB(config.vector_dir)
    records = [
        {
            "row_idx": 0,
            "record_id": "protein_sequence:P38398",
            "metadata": {"kind": "protein_sequence", "accession": "P38398", "alphabet": "protein"},
            "document": "[TYPE=protein_sequence]\nAccession: P38398\nSequence: MAAA",
        },
        {
            "row_idx": 1,
            "record_id": "protein_sequence:P51587",
            "metadata": {"kind": "protein_sequence", "accession": "P51587", "alphabet": "protein"},
            "document": "[TYPE=protein_sequence]\nAccession: P51587\nSequence: MAAA",
        },
        {
            "row_idx": 2,
            "record_id": "protein_sequence:Q99999",
            "metadata": {"kind": "protein_sequence", "accession": "Q99999", "alphabet": "protein"},
            "document": "[TYPE=protein_sequence]\nAccession: Q99999\nSequence: GGGG",
        },
    ]
    embeddings = np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    vector_db.add_records("protein_sequence", records, embeddings)

    result = VectorViewGraphBuilder(config).build(target="protein_sequence", limit=3, neighbors=1)

    assert result.node_count == 3
    assert result.edge_count == 3
    graph = GraphStore(result.graph_db)
    status = graph.status()
    assert status["nodes"]["protein_sequence"] == 3
    assert status["edges"]["vector_neighbor"] == 3
    assert graph.expand("protein_sequence:P38398")


def test_view_graph_skips_duplicate_entity_self_loops(tmp_path: Path):
    pytest.importorskip("chromadb")
    config = BioKBConfig(
        root=tmp_path,
        raw_dir=tmp_path / "raw",
        index_dir=tmp_path / "index",
        sqlite_path=tmp_path / "index" / "open_rosalind_standard.sqlite",
        manifest_path=tmp_path / "index" / "manifest.json",
        graph_dir=tmp_path / "index" / "graph",
        vector_dir=tmp_path / "index" / "vector",
    )
    vector_db = ChromaVectorDB(config.vector_dir)
    records = [
        {
            "row_idx": 0,
            "record_id": "dna_sequence:ENST1",
            "metadata": {"kind": "dna_sequence", "alphabet": "dna"},
            "document": "Sequence: AAAA",
        },
        {
            "row_idx": 1,
            "record_id": "dna_sequence:ENST1",
            "metadata": {"kind": "dna_sequence", "alphabet": "dna"},
            "document": "Sequence: AAAA",
        },
        {
            "row_idx": 2,
            "record_id": "dna_sequence:ENST2",
            "metadata": {"kind": "dna_sequence", "alphabet": "dna"},
            "document": "Sequence: CCCC",
        },
    ]
    embeddings = np.asarray(
        [
            [1.0, 0.0],
            [0.99, 0.01],
            [0.0, 1.0],
        ],
        dtype=np.float32,
    )
    vector_db.add_records("dna_sequence", records, embeddings)

    result = VectorViewGraphBuilder(config).build(target="dna_sequence", limit=3, neighbors=2)

    with sqlite3.connect(result.graph_db) as conn:
        self_loops = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE source_entity_id = target_entity_id"
        ).fetchone()[0]
    assert self_loops == 0
