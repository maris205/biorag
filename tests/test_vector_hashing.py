import numpy as np

from dnarag.retrieval.vector import (
    HashingEmbedder,
    _fasta_header_metadata,
    _pooling_mode,
    _prepare_encoder_input,
    make_embedder,
    sequence_window_ranges,
    sequence_window_texts,
)


def test_hashing_embedder_shape_and_norm():
    matrix = HashingEmbedder(dim=32).embed(["BRCA1 DNA repair", "MAPK pathway"])

    assert matrix.shape == (2, 32)
    assert np.isclose(np.linalg.norm(matrix[0]), 1.0)


def test_make_hashing_embedder():
    matrix = make_embedder("hashing").embed(["BRCA1"])

    assert matrix.shape == (1, 256)


def test_sequence_window_ranges_cover_tail():
    assert sequence_window_ranges(10, window_size=4, stride=3) == [(0, 4), (3, 7), (6, 10)]


def test_sequence_window_texts_normalizes_and_deduplicates():
    texts = sequence_window_texts("acgt acgt", window_size=4, stride=4, max_windows=4)

    assert texts == ["ACGTACGT", "ACGT"]


def test_pooling_aliases_support_mean_and_last_token():
    assert _pooling_mode("mean") == "mean"
    assert _pooling_mode("last") == "last"
    assert _pooling_mode("eos") == "last"
    assert _pooling_mode("cls") == "cls"


def test_prott5_input_is_spaced_and_rare_residues_are_masked():
    assert _prepare_encoder_input("ACD UZOB", "prott5") == "A C D X X X X"


def test_dna_encoder_input_keeps_only_iupac_core_bases():
    assert _prepare_encoder_input("acgt n xyz 123", "dna") == "ACGTN"


def test_ensembl_fasta_header_metadata_extracts_gene_fields():
    metadata = _fasta_header_metadata(
        "ENST00000632585.1 cdna scaffold:GRCh38 gene:ENSG00000282172.1 "
        "gene_biotype:IG_V_gene transcript_biotype:IG_V_gene "
        "gene_symbol:IGKV5-2 description:immunoglobulin kappa variable 5-2"
    )

    assert metadata["gene_id"] == "ENSG00000282172.1"
    assert metadata["gene_symbol"] == "IGKV5-2"
    assert metadata["symbol"] == "IGKV5-2"
    assert metadata["transcript_biotype"] == "IG_V_gene"
