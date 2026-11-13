#!/usr/bin/env python3
"""Fast local bridge from a text archive to searchable ACM/NotebookLM notes.

No network, browser, account credentials, or remote writes are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import acm_moexiz_retroact as acm

TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def tokens(value: str) -> list[str]:
    return [t.casefold() for t in TOKEN_RE.findall(value)]


def build_index(source: Path) -> dict:
    raw = source.read_bytes()
    text = raw.decode("utf-8-sig")
    records, rejected = acm.extract_records(text)
    postings: dict[str, dict[str, int]] = defaultdict(dict)
    for row in records:
        host = urlsplit(row["url"]).hostname or ""
        searchable = " ".join([row["url"], host, row["category"], *row["context_examples"]])
        counts = Counter(tokens(searchable))
        for term, count in counts.items():
            postings[term][row["id"]] = count
    return {
        "schema_version": 1,
        "source_name": source.name,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "unique_urls": len(records),
        "rejected_url_candidates": rejected,
        "records": records,
        "postings": {term: dict(sorted(rows.items())) for term, rows in sorted(postings.items())},
    }


def search(index: dict, query: str, limit: int = 20) -> list[dict]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    records = {row["id"]: row for row in index["records"]}
    q = query.strip()
    if not q:
        return []

    # URL/domain lookup gets a deterministic exact/prefix boost.
    normalized_query = acm.canonicalize_url(q)
    query_host = (urlsplit(normalized_query).hostname or "").casefold() if normalized_query else ""
    query_terms = list(dict.fromkeys(tokens(q)))
    doc_count = max(1, len(records))
    scores: dict[str, float] = defaultdict(float)
    for term in query_terms:
        rows = index["postings"].get(term, {})
        df = len(rows)
        idf = math.log(1.0 + (doc_count - df + 0.5) / (df + 0.5))
        for record_id, tf in rows.items():
            # BM25-like lexical relevance; transparent, local ranking, not truth confidence.
            scores[record_id] += idf * (tf * 2.2) / (tf + 1.2)

    hits = []
    for record_id, row in records.items():
        url = row["url"].casefold()
        host = (urlsplit(row["url"]).hostname or "").casefold()
        score = scores.get(record_id, 0.0)
        if normalized_query and url == normalized_query.casefold():
            score += 1000.0
        elif normalized_query and (url.startswith(normalized_query.casefold()) or host == query_host):
            score += 100.0
        if query_host and (host == query_host or host.endswith("." + query_host)):
            score += 50.0
        if score > 0:
            hits.append({"score": round(score, 6), **row})
    return sorted(hits, key=lambda row: (-row["score"], row["url"]))[:limit]


def notebooklm_note(index: dict, query: str, hits: list[dict]) -> str:
    lines = [
        "# ACM — Note de recherche exportée pour NotebookLM",
        "",
        f"- Archive d’origine : `{index['source_name']}`",
        f"- SHA-256 de l’archive : `{index['source_sha256']}`",
        f"- Requête : {query}",
        f"- Résultats exportés : {len(hits)} / {index['unique_urls']} URL uniques détectées",
        "- Statut : liens extraits du texte fourni; disponibilité, contenu et droits non vérifiés.",
        "",
        "> Cette note est un export statique. Elle ne connecte pas NotebookLM à Chrome, à un compte Google ou à des ressources privées. Vérifier les liens et autorisations avant partage.",
        "> Le score sert uniquement à classer les correspondances lexicales; il n’est pas une probabilité de vérité.",
        "",
    ]
    for number, row in enumerate(hits, start=1):
        lines += [
            f"## {number}. {row['category']} — score {row['score']:.4f}",
            "",
            f"- URL : {row['url']}",
            f"- ID : `{row['id']}`; occurrences dans la source : {row['occurrences']}",
            f"- Offset initial dans le texte : {row['first_offset']} octets/caractères environ",
        ]
        for context in row.get("context_examples", []):
            lines += [f"- Contexte fourni : {context}"]
        lines.append("")
    lines += [
        "## Protocole d’usage",
        "",
        "1. Relire cette note et retirer toute référence sensible ou non autorisée.",
        "2. Ajouter/importer manuellement le fichier Markdown dans NotebookLM selon les options disponibles dans le compte.",
        "3. Demander des réponses avec citations et distinguer fait explicite, interprétation et hypothèse.",
        "4. Pour une nouvelle version, reconstruire l’index depuis l’archive mise à jour et comparer les empreintes.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build/search a local URL index and export a NotebookLM-ready note")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Extract links and save a local search index")
    build.add_argument("source", type=Path)
    build.add_argument("--index", type=Path, default=Path("acm-index.json"))
    find = sub.add_parser("search", help="Search URL, domain, topic, or keyword")
    find.add_argument("index", type=Path)
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=20)
    export = sub.add_parser("export", help="Export search results as a NotebookLM-importable Markdown note")
    export.add_argument("index", type=Path)
    export.add_argument("query")
    export.add_argument("--limit", type=int, default=40)
    export.add_argument("--out", type=Path, default=Path("NOTEBOOKLM-ACM-EXPORT.md"))
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            index = build_index(args.source)
            args.index.write_text(json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            print(f"Index créé: {args.index} — {index['unique_urls']} URL uniques; SHA-256 source {index['source_sha256']}")
        else:
            index = json.loads(args.index.read_text(encoding="utf-8"))
            hits = search(index, args.query, args.limit)
            if args.command == "search":
                print(json.dumps(hits, ensure_ascii=False, indent=2))
            else:
                args.out.write_text(notebooklm_note(index, args.query, hits), encoding="utf-8")
                print(f"Note créée: {args.out} — {len(hits)} résultats. Import manuel requis.")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
