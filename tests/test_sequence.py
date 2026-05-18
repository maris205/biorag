from dnarag.retrieval.sequence import detect_sequence


def test_detect_peptide_fragment():
    query = detect_sequence("MVKVGVNGFGRIGRLVTRA")

    assert query is not None
    assert query.sequence_type == "peptide_fragment"
    assert query.alphabet == "protein"


def test_detect_dna():
    query = detect_sequence("ATGCGTACGTAGCTAGCTA")

    assert query is not None
    assert query.sequence_type == "dna"
    assert query.alphabet == "dna"


def test_does_not_treat_short_phrase_as_sequence():
    assert detect_sequence("BRCA1 DNA repair") is None
