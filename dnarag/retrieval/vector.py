"""Vector index scaffolding for OmniGene and development smoke builds."""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from dnarag.config import BioKBConfig
from dnarag.localdb.standard import StandardDocument, StandardKB
from dnarag.retrieval.vector_db import ChromaVectorDB, SimpleVectorDB


@dataclass(frozen=True, slots=True)
class VectorRecord:
    record_id: str
    target: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VectorBuildResult:
    vector_dir: Path
    targets: dict[str, int]
    backend: str
    manifest_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "vector_dir": str(self.vector_dir),
            "targets": self.targets,
            "backend": self.backend,
            "manifest_path": str(self.manifest_path),
        }


@dataclass(frozen=True, slots=True)
class SequenceWindowSettings:
    window_size: int = 128
    stride: int = 64
    source_limit: int = 0
    min_window_size: int = 24


class HashingEmbedder:
    """Deterministic local embedding backend for smoke tests.

    This is not a scientific embedding model. It exists so indexing, search, and
    artifacts can be tested without downloading OmniGene.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row_idx, text in enumerate(texts):
            for token in _tokens(text):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                value = int.from_bytes(digest, "little")
                col = value % self.dim
                sign = 1.0 if (value >> 63) == 0 else -1.0
                matrix[row_idx, col] += sign
            norm = np.linalg.norm(matrix[row_idx])
            if norm > 0:
                matrix[row_idx] /= norm
        return matrix


class OmniGeneEmbedder:
    """OmniGene-4 CPT embedding wrapper with mean/last-token pooling."""

    def __init__(
        self,
        model_name: str,
        pooling: str = "mean",
        dtype: str = "auto",
        load_in_4bit: bool = False,
    ):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except Exception as exc:
            raise RuntimeError("Install vector dependencies to use the OmniGene backend") from exc

        self.torch = torch
        self.pooling = pooling
        resolved_model = _resolve_transformers_model_name(model_name)
        local_only = _is_local_model_path(resolved_model)
        self.tokenizer = AutoTokenizer.from_pretrained(
            resolved_model,
            trust_remote_code=True,
            local_files_only=local_only,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        model_kwargs: dict[str, Any] = {
            "device_map": "auto",
            "trust_remote_code": True,
            "experts_implementation": "eager",
        }
        if load_in_4bit:
            try:
                from transformers import BitsAndBytesConfig
            except Exception as exc:
                raise RuntimeError("Install bitsandbytes to use the transformers4bit backend") from exc
            compute_dtype = (
                torch.float16
                if dtype == "fp16"
                else torch.float32
                if dtype == "fp32"
                else torch.bfloat16
            )
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=compute_dtype,
            )
        if dtype != "auto":
            model_kwargs["torch_dtype"] = (
                torch.bfloat16 if dtype == "bf16" else torch.float16 if dtype == "fp16" else torch.float32
            )
        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                resolved_model,
                local_files_only=local_only,
                **model_kwargs,
            )
        except ValueError as exc:
            if not load_in_4bit or "quantization" not in str(exc).lower():
                raise
            model_kwargs.pop("quantization_config", None)
            self.model = AutoModelForCausalLM.from_pretrained(
                resolved_model,
                local_files_only=local_only,
                **model_kwargs,
            )
        self.model.eval()

    def embed(self, texts: list[str]) -> np.ndarray:
        torch = self.torch
        max_length = max(_env_int("DNARAG_EMBED_MAX_LENGTH", 2048), 8)
        encoded = self.tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=max_length)
        encoded = {key: value.to(self.model.device) for key, value in encoded.items()}
        with torch.inference_mode():
            output = self.model(**encoded, output_hidden_states=True)
            hidden = output.hidden_states[-1]
            mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            if _pooling_mode(self.pooling) == "last":
                pooled = _last_token_pool(hidden, encoded["attention_mask"], padding_side=self.tokenizer.padding_side)
            else:
                pooled = _mean_pool(hidden, mask)
            pooled = torch.nn.functional.normalize(pooled.float(), p=2, dim=1)
        return pooled.cpu().numpy().astype(np.float32)


class HFEncoderEmbedder:
    """Generic Hugging Face encoder embedding wrapper for public baselines."""

    def __init__(
        self,
        model_name: str,
        pooling: str = "mean",
        dtype: str = "auto",
        input_format: str = "auto",
        trust_remote_code: bool = False,
    ):
        try:
            import torch
            from transformers import AutoModel, AutoModelForMaskedLM, AutoTokenizer, T5EncoderModel
        except Exception as exc:
            raise RuntimeError("Install vector dependencies to use Hugging Face encoder backends") from exc

        self.torch = torch
        self.force_cpu = _env_bool("DNARAG_FORCE_CPU", False) or str(os.environ.get("DNARAG_HF_DEVICE") or "").lower() == "cpu"
        self.pooling = _pooling_mode(pooling)
        self.input_format = str(input_format or "auto").lower()
        resolved_model = _resolve_transformers_model_name(model_name)
        local_only = _is_local_model_path(resolved_model)
        self.tokenizer = AutoTokenizer.from_pretrained(
            resolved_model,
            trust_remote_code=trust_remote_code,
            local_files_only=local_only,
            do_lower_case=False,
        )
        if "nucleotide-transformer" in str(model_name).lower():
            _patch_transformers_legacy_pytorch_utils()
        if self.tokenizer.pad_token is None and getattr(self.tokenizer, "eos_token", None) is not None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        model_kwargs: dict[str, Any] = {"trust_remote_code": trust_remote_code}
        if self.force_cpu:
            model_kwargs["low_cpu_mem_usage"] = False
        elif self.input_format != "dna":
            model_kwargs["device_map"] = "auto"
        else:
            model_kwargs["low_cpu_mem_usage"] = False
        if dtype != "auto":
            if self.force_cpu and dtype == "fp16":
                model_kwargs["torch_dtype"] = torch.float32
            else:
                model_kwargs["torch_dtype"] = (
                    torch.bfloat16 if dtype == "bf16" else torch.float16 if dtype == "fp16" else torch.float32
                )
        if self.input_format == "dna" and getattr(self.tokenizer, "pad_token_id", None) is not None:
            from transformers import AutoConfig

            config = AutoConfig.from_pretrained(
                resolved_model,
                trust_remote_code=trust_remote_code,
                local_files_only=local_only,
            )
            if getattr(config, "pad_token_id", None) is None:
                config.pad_token_id = int(self.tokenizer.pad_token_id)
            _patch_dna_encoder_config_defaults(config)
            model_kwargs["config"] = config
        if self.input_format == "prott5" or "prot_t5" in str(model_name).lower():
            model_cls = T5EncoderModel
        elif "nucleotide-transformer" in str(model_name).lower():
            model_cls = AutoModelForMaskedLM
        else:
            model_cls = AutoModel
        self.model = model_cls.from_pretrained(
            resolved_model,
            local_files_only=local_only,
            **model_kwargs,
        )
        if self.force_cpu:
            self.model.to("cpu")
        elif self.input_format == "dna" and torch.cuda.is_available():
            self.model.to("cuda")
        self.model.eval()
        if self.input_format == "dna" and selected_model_uses_legacy_flash(model_name):
            _disable_legacy_flash_attention()
        self.dim = int(getattr(self.model.config, "hidden_size", 0) or 0)

    def embed(self, texts: list[str]) -> np.ndarray:
        torch = self.torch
        max_length = max(_env_int("DNARAG_EMBED_MAX_LENGTH", 1024), 8)
        prepared = [_prepare_encoder_input(text, self.input_format) for text in texts]
        encoded = self.tokenizer(prepared, return_tensors="pt", padding=True, truncation=True, max_length=max_length)
        encoded = {key: value.to(self.model.device) for key, value in encoded.items()}
        with torch.inference_mode():
            output = self.model(**encoded, output_hidden_states=True)
            hidden = _last_hidden_state_from_output(output)
            token_mask = _encoder_pooling_mask(encoded, self.tokenizer).to(hidden.device)
            mask = token_mask.unsqueeze(-1).to(hidden.dtype)
            if self.pooling == "cls":
                pooled = hidden[:, 0, :]
            elif self.pooling == "last":
                pooled = _last_token_pool(hidden, token_mask, padding_side=self.tokenizer.padding_side)
            else:
                pooled = _mean_pool(hidden, mask)
            pooled = torch.nn.functional.normalize(pooled.float(), p=2, dim=1)
        return pooled.cpu().numpy().astype(np.float32)


class DNABERT2Embedder:
    """DNABERT-2 encoder loaded through its official custom model classes.

    DNABERT-2 declares a custom ``BertConfig``/``BertModel`` pair that is not
    compatible with newer AutoModel registration checks. Loading those classes
    directly preserves all checkpoint weights while keeping the same pooling
    contract as the other DNA encoders.
    """

    def __init__(
        self,
        model_name: str,
        pooling: str = "mean",
        dtype: str = "fp32",
    ):
        try:
            import torch
            from transformers import AutoTokenizer
        except Exception as exc:
            raise RuntimeError("Install vector dependencies to use the DNABERT-2 backend") from exc

        self.torch = torch
        self.pooling = _pooling_mode(pooling)
        self.force_cpu = _env_bool("DNARAG_FORCE_CPU", False) or str(os.environ.get("DNARAG_HF_DEVICE") or "").lower() == "cpu"
        resolved_model = _resolve_transformers_model_name(model_name)
        local_only = _is_local_model_path(resolved_model)
        self.tokenizer = AutoTokenizer.from_pretrained(
            resolved_model,
            local_files_only=local_only,
            trust_remote_code=False,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token or self.tokenizer.sep_token

        config_cls, model_cls = _load_dnabert2_classes(resolved_model)
        config = config_cls.from_pretrained(resolved_model, local_files_only=local_only)
        if getattr(config, "pad_token_id", None) is None and self.tokenizer.pad_token_id is not None:
            config.pad_token_id = int(self.tokenizer.pad_token_id)
        _patch_dna_encoder_config_defaults(config)
        self.model = model_cls.from_pretrained(
            resolved_model,
            config=config,
            local_files_only=local_only,
            add_pooling_layer=False,
        )
        _disable_legacy_flash_attention()
        self.device = torch.device("cpu" if self.force_cpu or not torch.cuda.is_available() else "cuda")
        self.model.to(self.device)
        if dtype == "fp16" and self.device.type == "cuda":
            self.model.to(dtype=torch.float16)
        elif dtype == "bf16" and self.device.type == "cuda":
            self.model.to(dtype=torch.bfloat16)
        else:
            self.model.to(dtype=torch.float32)
        self.model.eval()
        self.dim = int(getattr(self.model.config, "hidden_size", 0) or 0)

    def embed(self, texts: list[str]) -> np.ndarray:
        torch = self.torch
        max_length = max(_env_int("DNARAG_EMBED_MAX_LENGTH", 512), 8)
        prepared = [_prepare_encoder_input(text, "dna") for text in texts]
        encoded = self.tokenizer(
            prepared,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=max_length,
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with torch.inference_mode():
            output = self.model(**encoded, output_all_encoded_layers=False)
            hidden = output[0] if isinstance(output, (tuple, list)) else output.last_hidden_state
            token_mask = _encoder_pooling_mask(encoded, self.tokenizer).to(hidden.device)
            mask = token_mask.unsqueeze(-1).to(hidden.dtype)
            if self.pooling == "cls":
                pooled = hidden[:, 0, :]
            elif self.pooling == "last":
                pooled = _last_token_pool(hidden, encoded["attention_mask"])
            else:
                pooled = _mean_pool(hidden, mask)
            pooled = torch.nn.functional.normalize(pooled.float(), p=2, dim=1)
        return pooled.cpu().numpy().astype(np.float32)


class GGUFEmbedder:
    """llama.cpp GGUF embedding wrapper for OmniGene-4 CPT."""

    def __init__(self, model_name: str, pooling: str = "mean"):
        try:
            import llama_cpp
            from llama_cpp import Llama
        except Exception as exc:
            raise RuntimeError("Install llama-cpp-python to use the GGUF vector backend") from exc

        self.model_path = _resolve_gguf_model_path(model_name)
        self.pooling = pooling
        self.model = Llama(
            model_path=str(self.model_path),
            n_ctx=_env_int("DNARAG_GGUF_N_CTX", 1024),
            n_batch=_env_int("DNARAG_GGUF_N_BATCH", 64),
            n_ubatch=_env_int("DNARAG_GGUF_N_UBATCH", 64),
            n_gpu_layers=_env_int("DNARAG_GGUF_N_GPU_LAYERS", -1),
            embedding=True,
            pooling_type=_llama_pooling_type(llama_cpp, pooling),
            verbose=_env_bool("DNARAG_GGUF_VERBOSE", False),
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        output = self.model.create_embedding(texts)
        items = sorted(output["data"], key=lambda item: int(item.get("index", 0)))
        matrix = np.asarray([item["embedding"] for item in items], dtype=np.float32)
        if matrix.ndim != 2:
            raise RuntimeError(
                "GGUF backend returned token-level embeddings; use pooling='mean' or pooling='eos'"
            )
        return _normalize_rows(matrix)


def make_embedder(
    backend: str,
    *,
    model_name: str | None = None,
    pooling: str | None = None,
    dtype: str | None = None,
) -> Any:
    selected = str(backend or "").strip().lower()
    if selected == "hashing":
        return HashingEmbedder()
    if selected in {"omnigene", "transformers4bit", "omnigene4bit"}:
        if not model_name:
            raise ValueError("The OmniGene backend requires a model name or local model path")
        force_4bit = (
            selected in {"transformers4bit", "omnigene4bit"}
            or _env_bool("DNARAG_OMNIGENE_LOAD_IN_4BIT", False)
            or "4bit" in str(model_name).lower()
        )
        return OmniGeneEmbedder(
            model_name=model_name,
            pooling=pooling or "mean",
            dtype=dtype or "auto",
            load_in_4bit=force_4bit,
        )
    if selected in {"hf_encoder", "esm", "esm2", "prott5", "dnabert", "dnabert2", "dnabert-2", "dnabert_s", "dnabert-s", "nucleotide", "caduceus", "hyenadna", "gena_lm", "gena-lm"}:
        if not model_name:
            raise ValueError(f"The {selected} backend requires a model name or local model path")
        if selected in {"dnabert2", "dnabert-2"}:
            return DNABERT2Embedder(
                model_name=model_name,
                pooling=pooling or "mean",
                dtype=dtype or "fp32",
            )
        input_format = (
            "prott5"
            if selected == "prott5" or "prot_t5" in str(model_name).lower()
            else "protein"
            if selected in {"esm", "esm2"}
            else "dna"
            if selected in {"dnabert", "dnabert_s", "dnabert-s", "nucleotide", "caduceus", "hyenadna", "gena_lm", "gena-lm"}
            else "auto"
        )
        return HFEncoderEmbedder(
            model_name=model_name,
            pooling=pooling or "mean",
            dtype=dtype or "auto",
            input_format=input_format,
            trust_remote_code=selected in {"dnabert", "dnabert_s", "dnabert-s", "nucleotide", "caduceus", "hyenadna", "gena_lm", "gena-lm"},
        )
    if selected in {"dna_es2", "dna-es2", "dna_esm", "dna-esm"}:
        if not model_name:
            raise ValueError("The DNA-ESM backend requires a trained model directory")
        from dnarag.dna_es2 import DNAESMEmbedder

        return DNAESMEmbedder(model_name=model_name, pooling=pooling or "mean", dtype=dtype or "fp32")
    if selected == "gguf":
        if not model_name:
            raise ValueError("The GGUF backend requires a model name, directory, or .gguf path")
        return GGUFEmbedder(model_name=model_name, pooling=pooling or "mean")
    raise ValueError(f"Unknown vector backend: {backend}")


class VectorIndexBuilder:
    def __init__(self, config: BioKBConfig):
        self.config = config
        self.standard = StandardKB(config.sqlite_path, config.manifest_path)

    def build(
        self,
        *,
        targets: Iterable[str],
        backend: str,
        model_name: str | None = None,
        pooling: str | None = None,
        dtype: str | None = None,
        batch_size: int | None = None,
        limit: int = 1000,
        store: str = "files",
        append: bool = False,
        sequence_window_size: int | None = None,
        sequence_stride: int | None = None,
        sequence_source_limit: int | None = None,
    ) -> VectorBuildResult:
        self.config.vector_dir.mkdir(parents=True, exist_ok=True)
        selected_targets = [target.strip() for target in targets if target.strip()]
        embedder = self._make_embedder(backend, model_name=model_name, pooling=pooling, dtype=dtype)
        batch = max(int(batch_size or self.config.embedding.batch_size), 1)
        counts: dict[str, int] = {}
        selected_model = (
            (model_name or self.config.embedding.model)
            if _backend_requires_model(backend)
            else None
        )
        selected_pooling = pooling or self.config.embedding.pooling
        window_settings = SequenceWindowSettings(
            window_size=max(int(sequence_window_size or _env_int("DNARAG_SEQUENCE_WINDOW_SIZE", 128)), 1),
            stride=max(int(sequence_stride or _env_int("DNARAG_SEQUENCE_STRIDE", 64)), 1),
            source_limit=max(int(sequence_source_limit or _env_int("DNARAG_SEQUENCE_SOURCE_LIMIT", 0)), 0),
            min_window_size=max(_env_int("DNARAG_SEQUENCE_MIN_WINDOW_SIZE", 24), 1),
        )
        for target in selected_targets:
            if store == "chroma":
                counts[target] = self._stream_target_to_chroma(
                    target,
                    embedder,
                    batch_size=batch,
                    backend=backend,
                    model_name=selected_model,
                    pooling=selected_pooling,
                    limit=limit,
                    append=append,
                    window_settings=window_settings,
                )
            else:
                records = list(self._records_for_target(target, limit=limit, window_settings=window_settings))
                counts[target] = self._write_target(
                    target,
                    records,
                    embedder,
                    batch_size=batch,
                    backend=backend,
                    model_name=selected_model,
                    pooling=selected_pooling,
                )
        manifest_path = self.config.vector_dir / "manifest.json"
        existing_manifest: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing_manifest = {}
        merged_targets = dict(existing_manifest.get("targets") or {})
        merged_targets.update(counts)
        manifest = {
            "dataset": "dnarag_vector_index",
            "backend": backend,
            "model": selected_model,
            "pooling": selected_pooling,
            "targets": merged_targets,
            "limit": int(limit or 0),
            "sequence_window": {
                "window_size": window_settings.window_size,
                "stride": window_settings.stride,
                "source_limit": window_settings.source_limit,
                "min_window_size": window_settings.min_window_size,
            },
            "last_build": {
                "targets": counts,
                "limit": int(limit or 0),
            },
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return VectorBuildResult(
            vector_dir=self.config.vector_dir,
            targets=counts,
            backend=backend,
            manifest_path=manifest_path,
        )

    def _stream_target_to_chroma(
        self,
        target: str,
        embedder: Any,
        batch_size: int,
        backend: str,
        model_name: str | None,
        pooling: str | None,
        limit: int,
        append: bool,
        window_settings: SequenceWindowSettings,
    ) -> int:
        chroma = ChromaVectorDB(self.config.vector_dir)
        if not append:
            chroma.delete_collection(target, missing_ok=True)
        start_offset = int(chroma.collection_info(target).get("count", 0)) if append and chroma.collection_info(target) else 0
        chroma.ensure_collection(
            target,
            metadata={
                "backend": backend,
                "model": model_name or "",
                "pooling": pooling or "",
                "dim": int(getattr(embedder, "dim", 0) or 0),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **_target_build_metadata(target, window_settings),
            },
        )
        progress_every = max(_env_int("DNARAG_VECTOR_PROGRESS_EVERY", 100), 0)
        started = time.monotonic()
        records_iter = self._records_for_target(target, limit=limit, window_settings=window_settings)
        batch_records: list[VectorRecord] = []
        written = 0
        skipped = 0
        for record in records_iter:
            if skipped < start_offset:
                skipped += 1
                continue
            batch_records.append(record)
            if len(batch_records) >= batch_size:
                written += self._write_chroma_batch(chroma, target, batch_records, embedder, row_offset=start_offset + written)
                batch_records = []
                if progress_every and (written == batch_size or written % progress_every < batch_size):
                    elapsed = time.monotonic() - started
                    print(
                        f"[vector:{target}:chroma] {start_offset + written} records in {elapsed:.1f}s",
                        file=sys.stderr,
                        flush=True,
                    )
        if batch_records:
            written += self._write_chroma_batch(chroma, target, batch_records, embedder, row_offset=start_offset + written)
        return start_offset + written

    def _write_chroma_batch(
        self,
        chroma: ChromaVectorDB,
        target: str,
        records: list[VectorRecord],
        embedder: Any,
        row_offset: int,
    ) -> int:
        record_rows = []
        for offset, record in enumerate(records):
            row = _record_json(record)
            row["row_idx"] = row_offset + offset
            record_rows.append(row)
        matrix = embedder.embed([record.text for record in records])
        chroma.upsert_records(target, record_rows, matrix, documents=[record.text for record in records])
        return len(records)

    def _make_embedder(self, backend: str, *, model_name: str | None, pooling: str | None, dtype: str | None):
        return make_embedder(
            backend,
            model_name=model_name or self.config.embedding.model,
            pooling=pooling or self.config.embedding.pooling,
            dtype=dtype or self.config.embedding.dtype,
        )

    def _records_for_target(
        self,
        target: str,
        limit: int,
        window_settings: SequenceWindowSettings,
    ) -> Iterable[VectorRecord]:
        if target in {"text", "entity"}:
            for doc in self.standard.iter_documents(limit=limit):
                yield _record_from_document(doc, target)
            return
        if target in {"sequence", "protein_sequence"}:
            yield from self._protein_sequence_records(limit=limit, target=target)
            return
        if target == "protein_sequence_window":
            yield from self._protein_sequence_window_records(limit=limit, target=target, settings=window_settings)
            return
        if target == "dna_sequence":
            yield from self._dna_sequence_records(limit=limit, target=target)
            return
        if target == "dna_sequence_window":
            yield from self._dna_sequence_window_records(limit=limit, target=target, settings=window_settings)
            return
        if target == "mixed":
            yield from self._mixed_records(limit=limit)
            return
        raise ValueError(f"Unknown target: {target}")

    def _protein_sequence_records(self, limit: int, target: str = "protein_sequence") -> Iterable[VectorRecord]:
        fasta = self.config.blast_fasta
        if not fasta.exists() or _is_standard_protein_blast_fasta(fasta):
            gz_fasta = self.config.raw_dir / "uniprot" / "uniprot_sprot.fasta.gz"
            if not fasta.exists() and not gz_fasta.exists():
                return
            if not fasta.exists():
                fasta = gz_fasta
        yield from _fasta_records(
            fasta,
            limit=limit,
            target=target,
            record_kind="protein_sequence",
            source="Swiss-Prot",
            alphabet="protein",
        )

    def _dna_sequence_records(self, limit: int, target: str = "dna_sequence") -> Iterable[VectorRecord]:
        candidates = [
            self.config.blastn_fasta,
            self.config.raw_dir / "ensembl" / "Homo_sapiens.GRCh38.cdna.all.fa.gz",
            self.config.raw_dir / "ensembl" / "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz",
        ]
        fasta = next((path for path in candidates if path.exists()), None)
        if fasta is None:
            return
        yield from _fasta_records(
            fasta,
            limit=limit,
            target=target,
            record_kind="dna_sequence",
            source="Ensembl cDNA",
            alphabet="dna",
        )

    def _protein_sequence_window_records(
        self,
        limit: int,
        target: str,
        settings: SequenceWindowSettings,
    ) -> Iterable[VectorRecord]:
        fasta = self.config.blast_fasta
        if not fasta.exists() or _is_standard_protein_blast_fasta(fasta):
            gz_fasta = self.config.raw_dir / "uniprot" / "uniprot_sprot.fasta.gz"
            if not fasta.exists() and not gz_fasta.exists():
                return
            if not fasta.exists():
                fasta = gz_fasta
        yield from _fasta_window_records(
            fasta,
            limit=limit,
            target=target,
            record_kind="protein_sequence_window",
            parent_kind="protein_sequence",
            source="Swiss-Prot",
            alphabet="protein",
            settings=settings,
        )

    def _dna_sequence_window_records(
        self,
        limit: int,
        target: str,
        settings: SequenceWindowSettings,
    ) -> Iterable[VectorRecord]:
        candidates = [
            self.config.blastn_fasta,
            self.config.raw_dir / "ensembl" / "Homo_sapiens.GRCh38.cdna.all.fa.gz",
            self.config.raw_dir / "ensembl" / "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz",
        ]
        fasta = next((path for path in candidates if path.exists()), None)
        if fasta is None:
            return
        yield from _fasta_window_records(
            fasta,
            limit=limit,
            target=target,
            record_kind="dna_sequence_window",
            parent_kind="dna_sequence",
            source="Ensembl cDNA",
            alphabet="dna",
            settings=settings,
        )

    def _mixed_records(self, limit: int) -> Iterable[VectorRecord]:
        if limit and limit > 0:
            text_limit = max(limit // 3, 1)
            protein_limit = max(limit // 3, 1)
            dna_limit = max(limit - text_limit - protein_limit, 1)
        else:
            text_limit = protein_limit = dna_limit = 0
        for doc in self.standard.iter_documents(limit=text_limit):
            yield _record_from_document(doc, "mixed")
        yield from self._protein_sequence_records(limit=protein_limit, target="mixed")
        yield from self._dna_sequence_records(limit=dna_limit, target="mixed")

    def _write_target(
        self,
        target: str,
        records: list[VectorRecord],
        embedder: Any,
        batch_size: int,
        backend: str,
        model_name: str | None,
        pooling: str | None,
    ) -> int:
        vectors: list[np.ndarray] = []
        id_map_path = self.config.vector_dir / f"{target}_id_map.jsonl"
        record_rows = [_record_json(record) for record in records]
        with id_map_path.open("wt", encoding="utf-8") as handle:
            for record in record_rows:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        progress_every = max(_env_int("DNARAG_VECTOR_PROGRESS_EVERY", 100), 0)
        started = time.monotonic()
        for start in range(0, len(records), batch_size):
            batch_records = records[start : start + batch_size]
            if not batch_records:
                continue
            vectors.append(embedder.embed([record.text for record in batch_records]))
            batch_number = start // batch_size + 1
            if progress_every and (batch_number == 1 or batch_number % progress_every == 0):
                done = min(start + len(batch_records), len(records))
                elapsed = time.monotonic() - started
                print(
                    f"[vector:{target}] {done}/{len(records)} records in {elapsed:.1f}s",
                    file=sys.stderr,
                    flush=True,
                )
        matrix = np.vstack(vectors) if vectors else np.zeros((0, 0), dtype=np.float32)
        matrix_path = self.config.vector_dir / f"{target}.npz"
        np.savez_compressed(matrix_path, vectors=matrix)
        _try_write_faiss(self.config.vector_dir / f"{target}.faiss", matrix)
        SimpleVectorDB(self.config.vector_dir).upsert_collection(
            target=target,
            vector_path=matrix_path,
            matrix=matrix,
            records=record_rows,
            backend=backend,
            model=model_name,
            pooling=pooling,
        )
        return len(records)


def _fasta_records(
    path: Path,
    *,
    limit: int,
    target: str,
    record_kind: str,
    source: str,
    alphabet: str,
) -> Iterable[VectorRecord]:
    count = 0
    for header, sequence in _iter_fasta(path):
        yield _sequence_record(
            header,
            sequence,
            target=target,
            record_kind=record_kind,
            source=source,
            alphabet=alphabet,
        )
        count += 1
        if limit and count >= limit:
            return


def _is_standard_protein_blast_fasta(path: Path) -> bool:
    return path.name == "swissprot.fasta" and "open-rosalind-kb/standard/index/blast" in str(path)


def _fasta_window_records(
    path: Path,
    *,
    limit: int,
    target: str,
    record_kind: str,
    parent_kind: str,
    source: str,
    alphabet: str,
    settings: SequenceWindowSettings,
) -> Iterable[VectorRecord]:
    emitted = 0
    source_count = 0
    for header, raw_sequence in _iter_fasta(path):
        if settings.source_limit and source_count >= settings.source_limit:
            return
        source_count += 1
        sequence = _clean_sequence(raw_sequence, allow_stop=alphabet == "protein")
        for start, end in sequence_window_ranges(len(sequence), settings.window_size, settings.stride):
            if end - start < settings.min_window_size:
                continue
            yield _sequence_window_record(
                header,
                sequence,
                target=target,
                record_kind=record_kind,
                parent_kind=parent_kind,
                source=source,
                alphabet=alphabet,
                start=start,
                end=end,
                settings=settings,
            )
            emitted += 1
            if limit and emitted >= limit:
                return


def _iter_fasta(path: Path) -> Iterable[tuple[str, str]]:
    if path.suffix == ".gz":
        handle_factory = lambda: gzip.open(path, "rt", encoding="utf-8", errors="replace")
    else:
        handle_factory = lambda: path.open("rt", encoding="utf-8", errors="replace")

    with handle_factory() as handle:
        header = ""
        chunks: list[str] = []
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                if header and chunks:
                    yield header, "".join(chunks)
                header = line[1:]
                chunks = []
            elif line:
                chunks.append(line)
        if header and chunks:
            yield header, "".join(chunks)


def _record_from_document(doc: StandardDocument, target: str) -> VectorRecord:
    kind = doc.kind
    title = doc.name or doc.symbol or doc.source_id
    text = "\n".join(
        item
        for item in [
            f"[TYPE={kind}]",
            f"Source: {doc.source}",
            f"ID: {doc.source_id}",
            f"Symbol: {doc.symbol}" if doc.symbol else "",
            f"Title: {title}",
            f"Organism: {doc.organism}" if doc.organism else "",
            f"Description: {doc.description}" if doc.description else "",
        ]
        if item
    )
    return VectorRecord(
        record_id=doc.entity_id,
        target=target,
        text=text,
        metadata={
            "kind": doc.kind,
            "source_id": doc.source_id,
            "symbol": doc.symbol,
            "source": doc.source,
            "source_url": doc.source_url,
        },
    )


def _sequence_record(
    header: str,
    sequence: str,
    *,
    target: str,
    record_kind: str,
    source: str,
    alphabet: str,
) -> VectorRecord:
    accession = _accession_from_header(header)
    header_metadata = _fasta_header_metadata(header)
    sequence_limit = max(_env_int("DNARAG_SEQUENCE_MAX_CHARS", 1200), 1)
    sequence_text = sequence[:sequence_limit]
    truncated = len(sequence) > len(sequence_text)
    text = "\n".join(
        [
            f"[TYPE={record_kind}]",
            f"Source: {source}",
            f"Accession: {accession}",
            f"Header: {header}",
            f"Alphabet: {alphabet}",
            f"Length: {len(sequence)}",
            f"Sequence-truncated: {str(truncated).lower()}",
            "Sequence:",
            sequence_text,
        ]
    )
    return VectorRecord(
        record_id=f"{record_kind}:{accession}",
        target=target,
        text=text,
        metadata={
            "kind": record_kind,
            "accession": accession,
            "source_id": accession,
            "header": header,
            **header_metadata,
            "length": len(sequence),
            "alphabet": alphabet,
            "sequence_truncated": truncated,
            "sequence_max_chars": sequence_limit,
            "source": source,
        },
    )


def _sequence_window_record(
    header: str,
    sequence: str,
    *,
    target: str,
    record_kind: str,
    parent_kind: str,
    source: str,
    alphabet: str,
    start: int,
    end: int,
    settings: SequenceWindowSettings,
) -> VectorRecord:
    accession = _accession_from_header(header)
    header_metadata = _fasta_header_metadata(header)
    parent_record_id = f"{parent_kind}:{accession}"
    window_id = f"{record_kind}:{accession}:{start + 1}-{end}"
    window_sequence = sequence[start:end]
    return VectorRecord(
        record_id=parent_record_id,
        target=target,
        text=window_sequence,
        metadata={
            "kind": record_kind,
            "parent_kind": parent_kind,
            "parent_record_id": parent_record_id,
            "window_id": window_id,
            "accession": accession,
            "source_id": accession,
            "header": header,
            **header_metadata,
            "length": len(sequence),
            "alphabet": alphabet,
            "window_start": start,
            "window_end": end,
            "window_length": end - start,
            "window_size": settings.window_size,
            "stride": settings.stride,
            "source": source,
        },
    )


def sequence_window_ranges(length: int, window_size: int, stride: int) -> list[tuple[int, int]]:
    if length <= 0:
        return []
    window = max(int(window_size), 1)
    step = max(int(stride), 1)
    if length <= window:
        return [(0, length)]
    ranges: list[tuple[int, int]] = []
    start = 0
    while start + window < length:
        ranges.append((start, start + window))
        start += step
    tail = (length - window, length)
    if not ranges or ranges[-1] != tail:
        ranges.append(tail)
    return ranges


def sequence_window_texts(
    sequence: str,
    *,
    window_size: int,
    stride: int,
    max_windows: int = 8,
    include_full: bool = True,
) -> list[str]:
    clean = _clean_sequence(sequence, allow_stop=True)
    if not clean:
        return []
    texts: list[str] = []
    if include_full:
        texts.append(clean)
    for start, end in sequence_window_ranges(len(clean), window_size, stride):
        window = clean[start:end]
        if window and window not in texts:
            texts.append(window)
        if max_windows and len(texts) >= max_windows:
            break
    return texts


def _accession_from_header(header: str) -> str:
    accession = header.split()[0]
    if "|" in accession:
        parts = accession.split("|")
        accession = parts[1] if len(parts) > 1 else accession
    return accession


def _fasta_header_metadata(header: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key, value in re.findall(r"\b([A-Za-z_]+):([^\s]+)", str(header or "")):
        metadata[key] = value.strip(";,")
    if "gene_symbol" in metadata:
        metadata["symbol"] = metadata["gene_symbol"]
    if "gene" in metadata:
        metadata["gene_id"] = metadata["gene"]
    if "description:" in str(header or ""):
        metadata["description"] = str(header).split("description:", 1)[1].strip()
    return metadata


def _clean_sequence(sequence: str, *, allow_stop: bool) -> str:
    allowed_extra = {"*"} if allow_stop else set()
    return "".join(ch for ch in str(sequence or "").upper() if ch.isalpha() or ch in allowed_extra)


def _target_build_metadata(target: str, settings: SequenceWindowSettings) -> dict[str, Any]:
    if target not in {"protein_sequence_window", "dna_sequence_window"}:
        return {}
    return {
        "record_recipe": "sequence_windows",
        "window_size": settings.window_size,
        "stride": settings.stride,
        "source_limit": settings.source_limit,
        "min_window_size": settings.min_window_size,
    }


def _backend_requires_model(backend: str) -> bool:
    return str(backend or "").lower() in {
        "omnigene",
        "transformers4bit",
        "omnigene4bit",
        "gguf",
        "hf_encoder",
        "esm",
        "esm2",
        "prott5",
        "dnabert",
        "dnabert2",
        "dnabert-2",
        "dnabert_s",
        "dnabert-s",
        "nucleotide",
        "dna_es2",
        "dna-es2",
        "dna_esm",
        "dna-esm",
    }


def _pooling_mode(pooling: str | None) -> str:
    selected = str(pooling or "mean").strip().lower()
    if selected in {"mean", "avg", "average"}:
        return "mean"
    if selected in {"last", "eos", "last_token"}:
        return "last"
    if selected in {"cls", "bos", "first", "first_token"}:
        return "cls"
    raise ValueError(f"Unsupported pooling mode: {pooling}")


def _mean_pool(hidden: Any, mask: Any) -> Any:
    return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)


def _last_token_pool(hidden: Any, attention_mask: Any, *, padding_side: str = "right") -> Any:
    del padding_side
    positions = attention_mask.long() * hidden.new_tensor(range(hidden.shape[1]), dtype=attention_mask.dtype).unsqueeze(0)
    indices = positions.argmax(dim=1).long()
    rows = hidden.new_tensor(range(hidden.shape[0]), dtype=indices.dtype).long()
    return hidden[rows, indices]


def _last_hidden_state_from_output(output: Any) -> Any:
    if hasattr(output, "last_hidden_state"):
        return output.last_hidden_state
    hidden_states = getattr(output, "hidden_states", None)
    if hidden_states:
        return hidden_states[-1]
    if isinstance(output, (tuple, list)):
        for item in output:
            if hasattr(item, "shape") and len(item.shape) == 3:
                return item
    raise RuntimeError("Could not extract token-level hidden states from encoder output")


def _encoder_pooling_mask(encoded: dict[str, Any], tokenizer: Any) -> Any:
    input_ids = encoded.get("input_ids")
    attention_mask = encoded.get("attention_mask")
    if attention_mask is None:
        if input_ids is None:
            raise RuntimeError("Encoder tokenizer returned neither input_ids nor attention_mask")
        # Some custom DNA tokenizers omit attention_mask; infer it from padding.
        pad_token_id = getattr(tokenizer, "pad_token_id", None)
        if pad_token_id is None:
            attention_mask = input_ids.new_ones(input_ids.shape)
        else:
            attention_mask = input_ids.ne(int(pad_token_id)).long()
    mask = attention_mask.clone()
    if input_ids is None:
        return mask
    special_ids = {
        value
        for value in [
            getattr(tokenizer, "cls_token_id", None),
            getattr(tokenizer, "sep_token_id", None),
            getattr(tokenizer, "bos_token_id", None),
            getattr(tokenizer, "eos_token_id", None),
            getattr(tokenizer, "pad_token_id", None),
        ]
        if value is not None
    }
    for token_id in special_ids:
        mask = mask.masked_fill(input_ids == int(token_id), 0)
    empty = mask.sum(dim=1) == 0
    if empty.any():
        mask[empty] = attention_mask[empty]
    return mask


def _prepare_encoder_input(text: str, input_format: str) -> str:
    selected = str(input_format or "auto").lower()
    if selected == "prott5":
        sequence = _clean_sequence(text, allow_stop=False).replace("U", "X").replace("Z", "X").replace("O", "X").replace("B", "X")
        return " ".join(sequence)
    if selected == "protein":
        return _clean_sequence(text, allow_stop=True)
    if selected == "dna":
        sequence = _clean_sequence(text, allow_stop=False)
        return "".join(ch for ch in sequence if ch in {"A", "C", "G", "T", "N"})
    return str(text)


def _patch_dna_encoder_config_defaults(config: Any) -> None:
    """Fill config defaults required by newer Transformers ESM/BERT classes."""
    defaults = {
        "is_decoder": False,
        "add_cross_attention": False,
        "chunk_size_feed_forward": 0,
        "num_labels": 2,
        "problem_type": None,
    }
    for key, value in defaults.items():
        if getattr(config, key, None) is None:
            setattr(config, key, value)


def _load_dnabert2_classes(model_name: str) -> tuple[Any, Any]:
    """Load DNABERT-2's custom classes without registering them with AutoModel."""
    module_root: Path | None = None
    explicit_root = os.environ.get("DNARAG_DNABERT2_MODULE_DIR")
    if explicit_root:
        candidate = Path(explicit_root).expanduser()
        if (candidate / "bert_layers.py").exists():
            module_root = candidate
    if module_root is None:
        cache_roots = [
            Path(os.environ.get("HF_MODULES_CACHE", "")),
            Path(os.environ.get("HF_HOME", "")) / "modules",
            Path.home() / ".cache" / "huggingface" / "modules",
        ]
        for cache_root in cache_roots:
            if not str(cache_root) or not cache_root.exists():
                continue
            matches = sorted(cache_root.glob("transformers_modules/**/bert_layers.py"))
            matches = [
                path
                for path in matches
                if "dnabert" in str(path).lower() and "2" in str(path).lower()
            ]
            if matches:
                module_root = matches[-1].parent
                break
    if module_root is None:
        raise RuntimeError(
            "DNABERT-2 custom code is not cached. Set DNARAG_DNABERT2_MODULE_DIR "
            "to the directory containing bert_layers.py and configuration_bert.py."
        )

    package_name = f"dnarag_dnabert2_{abs(hash(str(module_root))) % 10**10}"
    package = types.ModuleType(package_name)
    package.__path__ = [str(module_root)]
    sys.modules[package_name] = package

    def load_module(module_name: str) -> Any:
        full_name = f"{package_name}.{module_name}"
        existing = sys.modules.get(full_name)
        if existing is not None:
            return existing
        source = module_root / f"{module_name}.py"
        if not source.exists():
            raise RuntimeError(f"DNABERT-2 custom module is missing {source}")
        spec = importlib.util.spec_from_file_location(full_name, source)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not import DNABERT-2 custom module {source}")
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = loaded
        spec.loader.exec_module(loaded)
        return loaded

    config_module = load_module("configuration_bert")
    load_module("bert_padding")
    layers_module = load_module("bert_layers")
    layers_module.flash_attn_qkvpacked_func = None
    return config_module.BertConfig, layers_module.BertModel


def _patch_transformers_legacy_pytorch_utils() -> None:
    """Provide legacy helper expected by older remote ESM model code."""
    try:
        import torch
        import transformers.modeling_utils as modeling_utils
        import transformers.pytorch_utils as pytorch_utils
    except Exception:
        return
    if not hasattr(pytorch_utils, "find_pruneable_heads_and_indices"):

        def find_pruneable_heads_and_indices(
            heads: set[int],
            n_heads: int,
            head_size: int,
            already_pruned_heads: set[int],
        ) -> tuple[set[int], Any]:
            heads = set(heads) - set(already_pruned_heads)
            mask = torch.ones(n_heads, head_size)
            for head in heads:
                shifted = int(head) - sum(1 for pruned in already_pruned_heads if pruned < head)
                mask[shifted] = 0
            mask = mask.view(-1).contiguous().eq(1)
            index = torch.arange(len(mask))[mask].long()
            return heads, index

        pytorch_utils.find_pruneable_heads_and_indices = find_pruneable_heads_and_indices
    pre_trained = getattr(modeling_utils, "PreTrainedModel", None)
    if pre_trained is None:
        return
    if not hasattr(pre_trained, "all_tied_weights_keys"):

        @property
        def all_tied_weights_keys(self: Any) -> dict[str, Any]:
            return self.__dict__.get("_dnarag_all_tied_weights_keys", {})

        @all_tied_weights_keys.setter
        def all_tied_weights_keys(self: Any, value: Any) -> None:
            self.__dict__["_dnarag_all_tied_weights_keys"] = value or {}

        pre_trained.all_tied_weights_keys = all_tied_weights_keys
    if not hasattr(pre_trained, "get_head_mask"):

        def get_head_mask(self: Any, head_mask: Any, num_hidden_layers: int, is_attention_chunked: bool = False) -> Any:
            if head_mask is None:
                return [None] * int(num_hidden_layers)
            if head_mask.dim() == 1:
                head_mask = head_mask.unsqueeze(0).unsqueeze(0).unsqueeze(-1).unsqueeze(-1)
                head_mask = head_mask.expand(num_hidden_layers, -1, -1, -1, -1)
            elif head_mask.dim() == 2:
                head_mask = head_mask.unsqueeze(1).unsqueeze(-1).unsqueeze(-1)
            if is_attention_chunked:
                head_mask = head_mask.unsqueeze(-1)
            return head_mask.to(dtype=self.dtype)

        pre_trained.get_head_mask = get_head_mask


def selected_model_uses_legacy_flash(model_name: str) -> bool:
    lowered = str(model_name or "").lower()
    return "dnabert" in lowered


def _disable_legacy_flash_attention() -> None:
    """Disable old DNABERT remote Triton code on modern PyTorch/Triton stacks."""
    for module in list(sys.modules.values()):
        if module is None or not str(getattr(module, "__name__", "")).endswith("bert_layers"):
            continue
        if hasattr(module, "flash_attn_qkvpacked_func"):
            module.flash_attn_qkvpacked_func = None


def _try_write_faiss(path: Path, matrix: np.ndarray) -> None:
    if matrix.size == 0:
        return
    try:
        import faiss
    except Exception:
        return
    dim = matrix.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(np.ascontiguousarray(matrix.astype(np.float32)))
    faiss.write_index(index, str(path))


def _is_local_model_path(model_name: str) -> bool:
    return Path(model_name).expanduser().exists()


def _resolve_transformers_model_name(model_name: str) -> str:
    raw = str(model_name or "").strip()
    path = Path(raw).expanduser()
    if path.exists():
        return str(path)
    if not _env_bool("DNARAG_USE_LOCAL_TRANSFORMERS_CACHE", False):
        return raw
    if "/" not in raw:
        return raw
    repo_cache = f"models--{raw.replace('/', '--')}"
    for root in _hf_cache_roots():
        snapshot_root = root / repo_cache / "snapshots"
        if not snapshot_root.exists():
            continue
        snapshots = sorted(path for path in snapshot_root.iterdir() if path.is_dir() and _looks_like_transformers_snapshot(path))
        if snapshots:
            return str(snapshots[-1])
    return raw


def _looks_like_transformers_snapshot(path: Path) -> bool:
    if not (path / "config.json").exists():
        return False
    weight_patterns = ["*.safetensors", "pytorch_model*.bin", "model*.safetensors", "*.index.json"]
    return any(any(path.glob(pattern)) for pattern in weight_patterns)


def _resolve_gguf_model_path(model_name: str) -> Path:
    raw = str(model_name or "").strip()
    path = Path(raw).expanduser()
    if path.is_file():
        return path
    if path.is_dir():
        return _find_gguf(path)
    if "/" in raw:
        repo_cache = f"models--{raw.replace('/', '--')}"
        preferred = os.environ.get("DNARAG_GGUF_FILENAME") or os.environ.get("FILENAME")
        for root in _hf_cache_roots():
            snapshot_root = root / repo_cache / "snapshots"
            if not snapshot_root.exists():
                continue
            if preferred:
                matches = sorted(snapshot_root.glob(f"*/{preferred}"))
                if matches:
                    return matches[-1]
            matches = sorted(snapshot_root.glob("*/*.gguf"))
            if matches:
                return matches[-1]
    raise FileNotFoundError(f"Could not resolve GGUF model path: {model_name}")


def _find_gguf(directory: Path) -> Path:
    preferred = os.environ.get("DNARAG_GGUF_FILENAME") or os.environ.get("FILENAME")
    if preferred:
        preferred_path = directory / preferred
        if preferred_path.is_file():
            return preferred_path
    matches = sorted(directory.glob("*.gguf"))
    if not matches:
        raise FileNotFoundError(f"No .gguf file found in {directory}")
    return matches[-1]


def _hf_cache_roots() -> list[Path]:
    raw_roots = [
        os.environ.get("HF_HOME"),
        os.environ.get("HUGGINGFACE_HUB_CACHE"),
        str(Path.home() / ".cache" / "huggingface"),
        str(Path.home() / ".cache" / "huggingface" / "hub"),
        "/root/autodl-tmp/huggingface",
    ]
    roots: list[Path] = []
    seen: set[Path] = set()
    for raw in raw_roots:
        if not raw:
            continue
        root = Path(raw).expanduser()
        candidates = [root]
        if root.name == "hub":
            candidates.append(root.parent)
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                roots.append(candidate)
    return roots


def _llama_pooling_type(llama_cpp: Any, pooling: str) -> int:
    selected = str(pooling or "mean").lower()
    if selected == "mean":
        return int(llama_cpp.LLAMA_POOLING_TYPE_MEAN)
    if selected == "eos":
        return int(llama_cpp.LLAMA_POOLING_TYPE_LAST)
    raise ValueError(f"Unsupported GGUF pooling mode: {pooling}")


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value in {None, ""}:
        return default
    return int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value in {None, ""}:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    normalized = matrix.astype(np.float32, copy=True)
    norms = np.linalg.norm(normalized, axis=1, keepdims=True)
    np.divide(normalized, norms, out=normalized, where=norms > 0)
    return normalized


def _record_json(record: VectorRecord) -> dict[str, Any]:
    return {
        "record_id": record.record_id,
        "target": record.target,
        "document": record.text,
        "text_sha256": hashlib.sha256(record.text.encode("utf-8")).hexdigest(),
        "metadata": record.metadata,
    }


def _tokens(text: str) -> list[str]:
    return [token for token in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if token]


def cosine_search(npz_path: str | Path, query_vector: np.ndarray, top_k: int = 10) -> list[tuple[int, float]]:
    data = np.load(npz_path)
    matrix = data["vectors"]
    if matrix.size == 0:
        return []
    query = query_vector.astype(np.float32)
    norm = np.linalg.norm(query)
    if norm > 0:
        query = query / norm
    scores = matrix @ query
    top = np.argsort(-scores)[: max(int(top_k), 1)]
    return [(int(idx), float(scores[idx])) for idx in top if not math.isnan(float(scores[idx]))]
