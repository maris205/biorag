from dnarag.retrieval.hybrid import plan_retrieval_modes


def test_route_gated_modes_keep_blast_for_pure_sequence():
    modes = plan_retrieval_modes("MAFSAEDVLKEYDRRRRMEALLLSLYYPNDRKLLDYKEWSPPRVQVECPKAPVEW")

    assert modes == ("blast", "vector")


def test_route_gated_modes_use_text_graph_vector_for_language_query():
    modes = plan_retrieval_modes("BRCA1 DNA repair")

    assert modes == ("fts", "graph", "vector")
