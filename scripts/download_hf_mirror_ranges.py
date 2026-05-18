#!/usr/bin/env python
"""Download Hugging Face files from hf-mirror with parallel HTTP ranges.

This is a fallback for large public safetensors files when the standard Hub
client stalls behind proxies. It writes directly to the Hugging Face cache blob
path named by the upstream ETag, then optionally creates the snapshot symlink.
"""
from __future__ import annotations

import argparse
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

import requests


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--filename", required=True)
    parser.add_argument("--cache-dir", default="/root/autodl-tmp/huggingface")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--endpoint", default="https://hf-mirror.com")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--chunk-mb", type=int, default=64)
    args = parser.parse_args()

    url = f"{args.endpoint.rstrip('/')}/{args.repo}/resolve/{quote(args.revision)}/{quote(args.filename)}"
    session = requests.Session()
    head = session.head(url, allow_redirects=False, timeout=30)
    head.raise_for_status()
    size = int(head.headers["x-linked-size"])
    etag = str(head.headers["x-linked-etag"]).strip('"')
    commit = str(head.headers.get("x-repo-commit") or args.revision)

    repo_cache = Path(args.cache_dir) / f"models--{args.repo.replace('/', '--')}"
    blob_path = repo_cache / "blobs" / etag
    snapshot_path = repo_cache / "snapshots" / commit / args.filename
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    if blob_path.exists() and blob_path.stat().st_size == size:
        print(f"exists {blob_path} {size}")
        _ensure_symlink(snapshot_path, blob_path)
        return

    part_dir = Path(tempfile.mkdtemp(prefix=f"{etag[:12]}_", dir=str(blob_path.parent)))
    chunk = max(args.chunk_mb, 1) * 1024 * 1024
    ranges = [(start, min(start + chunk - 1, size - 1)) for start in range(0, size, chunk)]
    print(f"download {args.filename} size={size} chunks={len(ranges)} workers={args.workers}", flush=True)

    try:
        with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as executor:
            futures = [
                executor.submit(_download_range, session, url, part_dir / f"{idx:05d}.part", start, end)
                for idx, (start, end) in enumerate(ranges)
            ]
            done = 0
            for future in as_completed(futures):
                future.result()
                done += 1
                if done == 1 or done % 8 == 0 or done == len(futures):
                    print(f"chunks {done}/{len(futures)}", flush=True)
        tmp_path = blob_path.with_suffix(".tmp")
        with tmp_path.open("wb") as out:
            for idx in range(len(ranges)):
                with (part_dir / f"{idx:05d}.part").open("rb") as part:
                    while True:
                        data = part.read(1024 * 1024)
                        if not data:
                            break
                        out.write(data)
        if tmp_path.stat().st_size != size:
            raise RuntimeError(f"Size mismatch for {tmp_path}: {tmp_path.stat().st_size} != {size}")
        tmp_path.replace(blob_path)
        _ensure_symlink(snapshot_path, blob_path)
        print(f"done {blob_path}")
    finally:
        for path in part_dir.glob("*.part"):
            path.unlink(missing_ok=True)
        part_dir.rmdir()


def _download_range(session: requests.Session, url: str, path: Path, start: int, end: int) -> None:
    if path.exists() and path.stat().st_size == end - start + 1:
        return
    headers = {"Range": f"bytes={start}-{end}"}
    with session.get(url, headers=headers, stream=True, timeout=120, allow_redirects=True) as response:
        response.raise_for_status()
        with path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    expected = end - start + 1
    if path.stat().st_size != expected:
        raise RuntimeError(f"Range size mismatch for {path}: {path.stat().st_size} != {expected}")


def _ensure_symlink(snapshot_path: Path, blob_path: Path) -> None:
    if snapshot_path.exists() or snapshot_path.is_symlink():
        snapshot_path.unlink()
    rel = os.path.relpath(blob_path, snapshot_path.parent)
    snapshot_path.symlink_to(rel)


if __name__ == "__main__":
    main()
