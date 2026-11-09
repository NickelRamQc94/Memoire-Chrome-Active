#!/usr/bin/env python3
"""Build a deterministic, reviewable NotebookLM source pack from local files and URLs.

This tool does not log in to Google, Chrome, GitHub, Drive, or Notion; it does not
fetch URLs or upload anything. It packages authorized local text sources and
catalogues URLs found in those files or supplied in a text file. Import the
result into NotebookLM manually after reviewing it.

Usage:
  python3 notebooklm_pack.py build ./sources ./notebooklm-pack --links ./links.txt
  python3 notebooklm_pack.py verify ./notebooklm-pack
  python3 notebooklm_pack.py self-test
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
from urllib.parse import urlsplit

TEXT_EXTENSIONS = {".md", ".txt", ".html", ".htm", ".csv", ".rst"}
BINARY_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | BINARY_EXTENSIONS
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*['\"]?\S+"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
PRIORITY_TERMS = (
    "algorithm", "algorithme", "equation", "équation", "formula", "formule",
    "qbit", "qubit", "willow", "quantum", "quantique", "mathemat",
    "mathématique", "proof", "preuve", "tritbyte", "biosku",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def contains_secret_like_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def collect_files(root: Path, output: Path, max_bytes: int) -> list[Path]:
    """Return supported, regular files in stable path order; never follow symlinks."""
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


def clean_url(candidate: str) -> str | None:
    """Trim common prose punctuation and accept only ordinary HTTP(S) URLs."""
    value = candidate.rstrip(".,;:!?)]}")
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
            return None
        if parts.username or parts.password:
            return None
        return value
    except ValueError:
        return None


def classify_url(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host == "github.com" or host.endswith(".github.com"):
        return "GitHub"
    if host in {"drive.google.com", "docs.google.com"} or host.endswith(".googleusercontent.com"):
        return "Google Drive / Docs"
    if host == "notion.so" or host.endswith(".notion.so") or host == "notion.site" or host.endswith(".notion.site"):
        return "Notion"
    return "Other URL"


def priority_score(path: str, text: str) -> int:
    haystack = f"{path}\n{text}".casefold()
    return sum(1 for term in PRIORITY_TERMS if term.casefold() in haystack)


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    os.replace(temporary, path)


def read_link_file(path: Path) -> list[str]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Links file is not valid UTF-8: {path}") from exc
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def build(source: Path, destination: Path, max_bytes: int, link_file: Path | None) -> int:
    source = source.resolve(strict=True)
    destination = destination.resolve(strict=False)
    if not source.is_dir():
        raise ValueError(f"Source must be a directory: {source}")
    if destination == source or source in destination.parents:
        raise ValueError("Destination must not be the source directory or inside it")

    files = collect_files(source, destination, max_bytes)
    entries: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    embedded: list[tuple[int, str, str]] = []
    raw_urls: list[tuple[str, str]] = []

    for path in files:
        rel = normalized_relpath(path, source)
        try:
            text, reason, raw = safe_text(path)
        except OSError as exc:
            skipped.append({"path": rel, "reason": f"Read error: {exc}"})
            continue
        assert raw is not None
        entry: dict[str, Any] = {
            "path": rel,
            "sha256": sha256(raw),
            "bytes": len(raw),
            "type": path.suffix.lower(),
        }
        if reason:
            skipped.append({"path": rel, "reason": reason})
            continue
        if path.suffix.lower() in BINARY_EXTENSIONS:
            entry["note"] = "Binary source; listed in manifest but not embedded. Import the original separately."
            entries.append(entry)
            continue
        assert text is not None
        score = priority_score(rel, text)
        entry["priority_score"] = score
        entries.append(entry)
        embedded.append((score, rel, text))
        raw_urls.extend((url, rel) for url in URL_RE.findall(text))

    explicit_links: list[tuple[str, str]] = []
    if link_file is not None:
        resolved_links = link_file.resolve(strict=True)
        explicit_links = [(line, f"link list: {resolved_links.name}") for line in read_link_file(resolved_links)]

    deduplicated: dict[str, str] = {}
    for candidate, origin in raw_urls + explicit_links:
        url = clean_url(candidate)
        if url:
            deduplicated.setdefault(url, origin)
    links = [
        {"url": url, "category": classify_url(url), "found_in": origin}
        for url, origin in sorted(deduplicated.items(), key=lambda item: (classify_url(item[0]), item[0].casefold()))
    ]

    # High-relevance sources first; ties and all output ordering are stable.
    embedded.sort(key=lambda item: (-item[0], item[1].casefold()))
    sections = [
        "# NotebookLM — source pack (snapshot)\n\n",
        "> Generated locally. It does not connect to Chrome, Google, GitHub, Drive, or Notion, and does not upload data.\n",
        "> URLs below are a catalogue only; their contents are not downloaded or verified. Import this Markdown and any authorized files manually.\n",
        "> Review privacy, permissions, and sensitive information before sharing. A hash proves byte integrity, not safety or truth.\n\n",
        "## Priority reading: algorithms, equations, qubits / Willow\n\n",
        "Sources are ordered by keyword matches in filenames and text. This is a transparent heuristic, not a scientific assessment.\n\n",
    ]
    for score, rel, _text in embedded:
        if score:
            sections.append(f"- Priority {score}: `{rel}`\n")
    if not any(score for score, _, _ in embedded):
        sections.append("- No sources matched the configured priority terms.\n")

    sections.append("\n## Link catalogue\n\nLinks are categorized by hostname only; access rights and link contents are not checked.\n")
    if links:
        categories = ("GitHub", "Google Drive / Docs", "Notion", "Other URL")
        for category in categories:
            matching = [item for item in links if item["category"] == category]
            if matching:
                sections.append(f"\n### {category}\n")
                for item in matching:
                    sections.append(f"- <{item['url']}> — listed from `{item['found_in']}`\n")
    else:
        sections.append("\nNo HTTP(S) links found or supplied.\n")

    sections.append("\n## Source documents\n")
    for score, rel, text in embedded:
        label = f" — priority score {score}" if score else ""
        sections.append(f"\n---\n\n### Source: `{rel}`{label}\n\n{text.rstrip()}\n")

    pdf_count = sum(1 for item in entries if item["type"] == ".pdf")
    bundle = "".join(sections).encode("utf-8")
    output_file = destination / "NOTEBOOKLM-SOURCES.md"
    write_atomic(output_file, bundle)
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "generator": "notebooklm_pack.py",
        "source_root_name": source.name,
        "text_sources_embedded": len(embedded),
        "pdfs_listed_not_embedded": pdf_count,
        "links_catalogued": links,
        "skipped_count": len(skipped),
        "sources": entries,
        "skipped": skipped,
        "outputs": {output_file.name: {"sha256": sha256(bundle), "bytes": len(bundle)}},
        "limitations": [
            "No Chrome profile, browser history, cookies, Google account, private cloud, GitHub, Drive, or Notion access is performed.",
            "Links are listed only; their destinations are not fetched, checked, or proven accessible.",
            "The pack is a point-in-time snapshot. Rerun the exporter to refresh it.",
            "PDF files are listed but not extracted or embedded.",
            "Secret-pattern filtering is heuristic and cannot guarantee that no sensitive data remains.",
            "Priority scores are keyword counts, not evidence of scientific validity or importance.",
        ],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    write_atomic(destination / "MANIFEST.sha256.json", manifest_bytes)
    print(f"Created {output_file}")
    print(f"Embedded text files: {len(embedded)}; listed PDFs: {pdf_count}; URLs: {len(links)}; skipped: {len(skipped)}")
    print(f"Bundle SHA-256: {sha256(bundle)}")
    return 0


def verify(destination: Path) -> int:
    destination = destination.resolve(strict=True)
    manifest = json.loads((destination / "MANIFEST.sha256.json").read_text(encoding="utf-8"))
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
    print("Hashes establish byte integrity, not truth, completeness, accessibility, or safety of source content.")
    return 0


def self_test() -> int:
    assert sha256(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert classify_url("https://github.com/example/repo") == "GitHub"
    assert classify_url("https://drive.google.com/drive/folders/example") == "Google Drive / Docs"
    assert classify_url("https://example.notion.site/page") == "Notion"
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        src, out = base / "src", base / "out"
        src.mkdir()
        (src / "math-willow.md").write_text(
            "# Willow qubit algorithm\nEquation and algorithm. https://github.com/example/repo\n",
            encoding="utf-8",
        )
        (src / "ordinary.txt").write_bytes(b"second\r\nline\r")
        (src / "secret.txt").write_text("api_key=example_secret_123", encoding="utf-8")
        links = base / "links.txt"
        links.write_text("https://drive.google.com/drive/folders/demo\nhttps://example.notion.site/page\n", encoding="utf-8")
        assert build(src, out, DEFAULT_MAX_BYTES, links) == 0
        bundle = (out / "NOTEBOOKLM-SOURCES.md").read_text(encoding="utf-8")
        assert bundle.index("math-willow.md") < bundle.index("ordinary.txt")
        assert "example_secret_123" not in bundle
        assert "Google Drive / Docs" in bundle and "Notion" in bundle and "GitHub" in bundle
        assert verify(out) == 0
    print("Self-test passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and verify a local NotebookLM source pack.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="Build one Markdown source pack")
    build_parser.add_argument("source", type=Path, help="Authorized local source directory")
    build_parser.add_argument("destination", type=Path, help="Output directory")
    build_parser.add_argument("--links", type=Path, help="Optional UTF-8 text file: one HTTP(S) URL per line")
    build_parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    verify_parser = subparsers.add_parser("verify", help="Verify generated output hashes")
    verify_parser.add_argument("destination", type=Path)
    subparsers.add_parser("self-test", help="Run deterministic tests")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            if args.max_bytes <= 0:
                raise ValueError("--max-bytes must be positive")
            return build(args.source, args.destination, args.max_bytes, args.links)
        if args.command == "verify":
            return verify(args.destination)
        return self_test()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
