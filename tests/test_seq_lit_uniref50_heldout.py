import gzip
from pathlib import Path

from scripts.build_seq_lit_uniref50_heldout import (
    clusters_from_uniref50,
    extract_uniref50_mapping,
)


def test_extract_uniref50_mapping_reads_selected_column(tmp_path: Path):
    path = tmp_path / "mapping.tab.gz"
    rows = [
        ["P1", "P1_HUMAN", "", "", "", "", "", "U100_1", "U90_1", "UniRef50_A"],
        ["P2", "P2_HUMAN", "", "", "", "", "", "U100_2", "U90_2", "UniRef50_A"],
        ["P3", "P3_HUMAN", "", "", "", "", "", "U100_3", "U90_3", "UniRef50_B"],
    ]
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write("\t".join(row) + "\n")

    mapping, stats = extract_uniref50_mapping(path, {"P1", "P2"}, progress_every=0)

    assert mapping == {"P1": "UniRef50_A", "P2": "UniRef50_A"}
    assert stats["mapped_accessions"] == 2
    assert stats["missing_accessions"] == 0


def test_clusters_from_uniref50_keeps_missing_accessions_as_singletons():
    clusters, accession_cluster, stats = clusters_from_uniref50(
        {"P1", "P2", "P3"},
        {"P1": "UniRef50_A", "P2": "UniRef50_A"},
    )

    assert accession_cluster["P1"] == accession_cluster["P2"]
    assert accession_cluster["P3"] != accession_cluster["P1"]
    assert len(clusters[accession_cluster["P3"]]) == 1
    assert stats["clusters"] == 2
