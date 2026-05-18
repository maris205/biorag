"""Configuration loading for local Bio-KB paths."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_ROOT = Path("/autodl-fs/data/open-rosalind-kb/standard")
DEFAULT_CONFIG = Path("configs/standard.yaml")


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    model: str = "dnagpt/OmniGene-4-CPT-v2-merged"
    pooling: str = "mean"
    dtype: str = "bf16"
    batch_size: int = 1


@dataclass(frozen=True, slots=True)
class RetrievalConfig:
    local_first: bool = True
    fallback_public_api: bool = False
    default_modes: tuple[str, ...] = ("fts", "blast", "graph", "vector")


DEFAULT_EMBEDDING = EmbeddingConfig()
DEFAULT_RETRIEVAL = RetrievalConfig()


@dataclass(frozen=True, slots=True)
class BioKBConfig:
    root: Path = DEFAULT_ROOT
    raw_dir: Path = DEFAULT_ROOT / "raw"
    index_dir: Path = DEFAULT_ROOT / "index"
    sqlite_path: Path = DEFAULT_ROOT / "index" / "open_rosalind_standard.sqlite"
    manifest_path: Path = DEFAULT_ROOT / "index" / "manifest.json"
    blast_db: Path = DEFAULT_ROOT / "index" / "blast" / "swissprot"
    blast_fasta: Path = DEFAULT_ROOT / "index" / "blast" / "swissprot.fasta"
    blastn_db: Path = DEFAULT_ROOT / "index" / "blast" / "ensembl_cdna"
    blastn_fasta: Path = DEFAULT_ROOT / "index" / "blast" / "ensembl_cdna.fasta"
    graph_dir: Path = DEFAULT_ROOT / "index" / "graph"
    vector_dir: Path = DEFAULT_ROOT / "index" / "vector"
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)

    @property
    def graph_db(self) -> Path:
        return self.graph_dir / "graph.sqlite"


def load_config(path: str | Path | None = None) -> BioKBConfig:
    """Load a YAML config, falling back to Standard KB defaults."""
    config_path = Path(path or DEFAULT_CONFIG)
    if not config_path.exists():
        return BioKBConfig()

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    kb = data.get("kb") or {}
    embedding = data.get("embedding") or {}
    retrieval = data.get("retrieval") or {}

    root = _path(kb.get("root"), DEFAULT_ROOT)
    index_dir = _path(kb.get("index_dir"), root / "index")
    raw_dir = _path(kb.get("raw_dir"), root / "raw")

    return BioKBConfig(
        root=root,
        raw_dir=raw_dir,
        index_dir=index_dir,
        sqlite_path=_path(kb.get("sqlite_path"), index_dir / "open_rosalind_standard.sqlite"),
        manifest_path=_path(kb.get("manifest_path"), index_dir / "manifest.json"),
        blast_db=_path(kb.get("blast_db"), index_dir / "blast" / "swissprot"),
        blast_fasta=_path(kb.get("blast_fasta"), index_dir / "blast" / "swissprot.fasta"),
        blastn_db=_path(kb.get("blastn_db"), index_dir / "blast" / "ensembl_cdna"),
        blastn_fasta=_path(kb.get("blastn_fasta"), index_dir / "blast" / "ensembl_cdna.fasta"),
        graph_dir=_path(kb.get("graph_dir"), index_dir / "graph"),
        vector_dir=_path(kb.get("vector_dir"), index_dir / "vector"),
        embedding=EmbeddingConfig(
            model=str(embedding.get("model") or DEFAULT_EMBEDDING.model),
            pooling=str(embedding.get("pooling") or DEFAULT_EMBEDDING.pooling),
            dtype=str(embedding.get("dtype") or DEFAULT_EMBEDDING.dtype),
            batch_size=int(embedding.get("batch_size") or DEFAULT_EMBEDDING.batch_size),
        ),
        retrieval=RetrievalConfig(
            local_first=bool(retrieval.get("local_first", True)),
            fallback_public_api=bool(retrieval.get("fallback_public_api", False)),
            default_modes=tuple(str(item) for item in retrieval.get("default_modes", DEFAULT_RETRIEVAL.default_modes)),
        ),
    )


def as_jsonable(config: BioKBConfig) -> dict[str, Any]:
    return {
        "root": str(config.root),
        "raw_dir": str(config.raw_dir),
        "index_dir": str(config.index_dir),
        "sqlite_path": str(config.sqlite_path),
        "manifest_path": str(config.manifest_path),
        "blast_db": str(config.blast_db),
        "blast_fasta": str(config.blast_fasta),
        "blastn_db": str(config.blastn_db),
        "blastn_fasta": str(config.blastn_fasta),
        "graph_dir": str(config.graph_dir),
        "vector_dir": str(config.vector_dir),
        "embedding": {
            "model": config.embedding.model,
            "pooling": config.embedding.pooling,
            "dtype": config.embedding.dtype,
            "batch_size": config.embedding.batch_size,
        },
        "retrieval": {
            "local_first": config.retrieval.local_first,
            "fallback_public_api": config.retrieval.fallback_public_api,
            "default_modes": list(config.retrieval.default_modes),
        },
    }


def _path(value: Any, default: Path) -> Path:
    if value in {None, ""}:
        return default
    return Path(str(value)).expanduser()
