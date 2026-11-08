#!/usr/bin/env python3
"""Build a reproducible, NotebookLM-ready source pack from local files.

This exporter does not log in to Google, access private services, or upload data.
It only reads explicitly selected local Markdown/text/HTML/CSV/PDF files and
writes a Markdown bundle plus a SHA-256 manifest. Review the output and upload
it to NotebookLM yourself. Never include credentials or files you do not have
permission to share.

Reproducibility properties:
- Input paths are sorted by normalized relative path before processing.
- Text sources are UTF-8 decoded, normalized to LF, and packed deterministically.
- SHA-256 is computed over the exact bytes read and over each generated output.
- The verifier checks the manifest against the files in the pack.

Example:
  python notebooklm_pack.py build ./sources ./notebooklm-pack
  python notebooklm_pack.py verify ./notebooklm-pack
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

TEXT_EXTENSIONS = {".md", ".txt", ".html", ".htm", ".csv", ".rst"}
BINARY_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | BINARY_EXTENSIONS
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*['\"]?\S+"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def contains_secret_like_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def collect_files(root: Path, output: Path, max_bytes: int) -> list[Path]:
    """Return sorted supported regular files, excluding the output subtree."""
    root = root.resolve(strict=True)
    output_abs = output.resolve(strict=False)
    found: list[Path] = []
    for current, dirs, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(
            name for name in dirs
            if not (current_path / name).is_symlink()
            and not (current_path / name).resolve().is_relative_to(output_abs)
            and name not in {".git", ".venv", "node_modules", "__pycache__"}
        )
        for name in filenames:
            path = current_path / name
            if path.is_symlink() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                if path.stat().st_size <= max_bytes:
                    found.append(path)
            except OSError:
                continue
    return sorted(found, key=lambda p: normalized_relpath(p, root).casefold())


def safe_text(path: Path) -> tuple[str | None, str | None, bytes | None]:
    raw = path.read_bytes()
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return None, None, raw
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, "Skipped: not valid UTF-8 text", raw
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in text:
        return None, "Skipped: NUL byte found in text input", raw
    if contains_secret_like_text(text):
        return None, "Skipped: secret-like pattern detected; review source locally", raw
    return text, None, raw


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        tmp = Path(handle.name)
        handle.write(data)
    os.replace(tmp, path)


def build(source: Path, destination: Path, max_bytes: int) -> int:
    source = source.resolve(strict=True)
    destination = destination.resolve(strict=False)
    if not source.is_dir():
        raise ValueError(f"Source must be a directory: {source}")
    if destination == source or source in destination.parents:
        raise ValueError("Destination must not be the source directory or inside it")

    files = collect_files(source, destination, max_bytes)
    entries: list[dict[str, Any]] = []
    sections: list[str] = [
        "# NotebookLM source pack\n\n"
        "> Generated locally by `notebooklm_pack.py`. This pack is a snapshot, not a live sync.\n"
        "> Review privacy and sharing permissions before importing into NotebookLM.\n"
    ]
    skipped: list[dict[str, str]] = []
    included_count = 0

    for path in files:
        rel = normalized_relpath(path, source)
        try:
            text, reason, raw = safe_text(path)
        except OSError as exc:
            skipped.append({"path": rel, "reason": f"Read error: {exc}"})
            continue
        assert raw is not None
        item = {"path": rel, "sha256": sha256(raw), "bytes": len(raw), "type": path.suffix.lower()}
        if reason:
            skipped.append({"path": rel, "reason": reason})
            continue
        if path.suffix.lower() in BINARY_EXTENSIONS:
            item["note"] = "Binary source; listed in manifest but not embedded. Import the original file separately."
            entries.append(item)
            continue
        assert text is not None
        entries.append(item)
        included_count += 1
        sections.append(f"\n---\n\n## Source: `{rel}`\n\n{text.rstrip()}\n")

    pack_text = "".join(sections).encode("utf-8")
    output_file = destination / "NOTEBOOKLM-SOURCES.md"
    write_atomic(output_file, pack_text)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generator": "notebooklm_pack.py",
        "source_root_name": source.name,
        "text_sources_embedded": included_count,
        "binary_sources_listed_not_embedded": sum(1 for e in entries if e["type"] in BINARY_EXTENSIONS),
        "skipped_count": len(skipped),
        "sources": entries,
        "skipped": skipped,
        "outputs": {output_file.name: {"sha256": sha256(pack_text), "bytes": len(pack_text)}},
        "limitations": [
            "No Google account access or NotebookLM upload is performed.",
            "The pack is a point-in-time snapshot; rerun the exporter to refresh it.",
            "PDF files are listed but not extracted or embedded.",
            "Secret-pattern filtering is a heuristic and cannot guarantee that no sensitive data remains.",
        ],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    write_atomic(destination / "MANIFEST.sha256.json", manifest_bytes)
    print(f"Created {output_file}")
    print(f"Included text files: {included_count}; listed PDFs: {manifest['binary_sources_listed_not_embedded']}; skipped: {len(skipped)}")
    print(f"Bundle SHA-256: {sha256(pack_text)}")
    return 0


def verify(destination: Path) -> int:
    destination = destination.resolve(strict=True)
    manifest_path = destination / "MANIFEST.sha256.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for name, metadata in manifest.get("outputs", {}).items():
        path = destination / name
        if not path.is_file():
            failures.append(f"Missing output: {name}")
            continue
        data = path.read_bytes()
        if sha256(data) != metadata.get("sha256"):
            failures.append(f"SHA-256 mismatch: {name}")
        if len(data) != metadata.get("bytes"):
            failures.append(f"Byte-count mismatch: {name}")
    if failures:
        print("Verification failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Verified {len(manifest.get('outputs', {}))} generated output(s).")
    print("Note: hashes establish byte integrity, not truth, completeness, or safety of source content.")
    return 0


def self_test() -> int:
    """Small deterministic tests for normalization, hashing, and secret detection."""
    assert sha256(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        src = base / "src"
        out = base / "out"
        src.mkdir()
        (src / "b.txt").write_bytes(b"second\r\nline\r")
        (src / "a.md").write_text("# Title\n", encoding="utf-8")
        (src / "secret.txt").write_text("api_key=example_secret_123", encoding="utf-8")
        assert build(src, out, DEFAULT_MAX_BYTES) == 0
        bundle = (out / "NOTEBOOKLM-SOURCES.md").read_bytes()
        assert bundle == (out / "NOTEBOOKLM-SOURCES.md").read_bytes()
        assert b"# Title\n" in bundle
        assert b"second\nline\n" in bundle
        assert b"example_secret_123" not in bundle
        assert verify(out) == 0
    print("Self-test passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create and verify a local NotebookLM source pack.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="Build a Markdown source pack from a local folder")
    build_parser.add_argument("source", type=Path, help="Folder containing files you are authorized to share")
    build_parser.add_argument("destination", type=Path, help="Output folder; created if needed")
    build_parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help=f"Skip files larger than this (default {DEFAULT_MAX_BYTES})")
    verify_parser = subparsers.add_parser("verify", help="Verify generated output hashes")
    verify_parser.add_argument("destination", type=Path)
    subparsers.add_parser("self-test", help="Run built-in deterministic tests")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            if args.max_bytes <= 0:
                raise ValueError("--max-bytes must be positive")
            return build(args.source, args.destination, args.max_bytes)
        if args.command == "verify":
            return verify(args.destination)
        return self_test()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
