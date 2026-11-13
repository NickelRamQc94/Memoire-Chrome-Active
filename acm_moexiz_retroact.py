#!/usr/bin/env python3
"""Deterministic, local-only ACM / MoExiZ / RetroAct prototype.

This tool reads a user-selected UTF-8 text file. It does not fetch URLs,
execute extracted code, access browser profiles, or connect to cloud accounts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SCHEMA_VERSION = 1
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,;:!?"
EXPERT_TERMS = {
    "cartographer": ("url", "link", "repo", "repository", "dépôt", "catalogue", "source", "index"),
    "analyst": ("algorithm", "algorithme", "equation", "équation", "moe", "moexiz", "retroact", "architecture", "code", "script"),
    "verifier": ("preuve", "proof", "test", "verify", "vérif", "hash", "sha-256", "falsifiable", "reproductible", "source primaire"),
    "statistician": ("statistique", "statistics", "mesure", "metric", "métrique", "count", "compte", "benchmark"),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonicalize_url(raw: str) -> str | None:
    """Trim prose punctuation and normalize only URL scheme/host/default port."""
    value = raw.rstrip(TRAILING_PUNCTUATION)
    # Closing punctuation is usually Markdown/prose, not part of the URL.
    for closing, opening in ((")", "("), ("]", "["), ("}", "{")):
        while value.endswith(closing) and value.count(closing) > value.count(opening):
            value = value[:-1]
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        if parts.username is not None or parts.password is not None:
            return None  # Do not export URLs embedding credentials.
        host = parts.hostname.lower()
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = parts.port
        if port and not ((parts.scheme.lower() == "https" and port == 443) or
                         (parts.scheme.lower() == "http" and port == 80)):
            host = f"{host}:{port}"
        return urlunsplit((parts.scheme.lower(), host, parts.path or "/", parts.query, parts.fragment))
    except (ValueError, UnicodeError):
        return None


def classify_url(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host == "github.com" or host.endswith(".github.com"):
        return "github"
    if host == "huggingface.co" or host.endswith(".huggingface.co"):
        return "huggingface"
    if host in {"drive.google.com", "docs.google.com"}:
        return "google_drive_docs"
    if host == "colab.research.google.com":
        return "google_colab"
    if host == "notebooklm.google.com":
        return "notebooklm"
    if any(host == d or host.endswith("." + d) for d in (
        "youtube.com", "youtu.be", "linkedin.com", "instagram.com", "facebook.com",
        "medium.com", "suno.com", "snapchat.com")):
        return "media_or_social"
    return "other_web"


def expert_mix(text: str) -> dict[str, float]:
    """Transparent keyword-based routing weights; not a trained neural MoE."""
    folded = text.casefold()
    scores = {name: sum(folded.count(term.casefold()) for term in terms)
              for name, terms in EXPERT_TERMS.items()}
    total = sum(scores.values())
    if total == 0:
        return {name: 0.0 for name in scores}
    return {name: round(score / total, 6) for name, score in scores.items()}


def extract_records(text: str) -> tuple[list[dict], int]:
    found: dict[str, dict] = {}
    rejected = 0
    for match in URL_RE.finditer(text):
        url = canonicalize_url(match.group(0))
        if url is None:
            rejected += 1
            continue
        start, end = match.span()
        snippet = text[max(0, start - 100):min(len(text), end + 100)].replace("\n", " ").strip()
        if url not in found:
            found[url] = {
                "id": "url:" + sha256_bytes(url.encode("utf-8"))[:16],
                "url": url,
                "category": classify_url(url),
                "verification_status": "user_supplied_unverified",
                "occurrences": 0,
                "first_offset": start,
                "context_examples": [],
                "expert_mix": expert_mix(snippet),
            }
        row = found[url]
        row["occurrences"] += 1
        if len(row["context_examples"]) < 3 and snippet not in row["context_examples"]:
            row["context_examples"].append(snippet)
    records = sorted(found.values(), key=lambda row: row["url"])
    return records, rejected


def analyze(text: str, raw_bytes: bytes) -> tuple[dict, dict]:
    records, rejected = extract_records(text)
    categories = Counter(row["category"] for row in records)
    stats = {
        "source_bytes": len(raw_bytes),
        "source_sha256": sha256_bytes(raw_bytes),
        "url_occurrences_accepted": sum(row["occurrences"] for row in records),
        "unique_urls": len(records),
        "rejected_url_candidates": rejected,
        "unique_by_category": dict(sorted(categories.items())),
        "expert_routing_document": expert_mix(text),
    }
    database = {
        "schema_version": SCHEMA_VERSION,
        "title": "ACM / MoExiZ / RetroAct — extracted source index",
        "provenance": "Extracted locally from the user-selected text file; URL reachability and content were not checked.",
        "access_policy": "No network requests, browser access, account access, or source-code execution.",
        "statistics": stats,
        "sources": records,
    }
    return database, stats


def compare_previous(current: dict, previous_path: Path | None) -> dict:
    if previous_path is None:
        return {"baseline": None, "added": [r["url"] for r in current["sources"]], "removed": [], "unchanged": []}
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    old = {r["url"] for r in previous.get("sources", []) if isinstance(r, dict) and isinstance(r.get("url"), str)}
    new = {r["url"] for r in current["sources"]}
    return {
        "baseline": str(previous_path),
        "added": sorted(new - old),
        "removed": sorted(old - new),
        "unchanged": sorted(new & old),
    }


def render_report(stats: dict, diff: dict) -> str:
    lines = [
        "# ACM / MoExiZ / RetroAct — rapport d’extraction",
        "",
        "> Prototype local et déterministe. Les URL sont extraites du fichier fourni; leur disponibilité, leur contenu et leur autorisation de partage ne sont pas vérifiés.",
        "> MoExiZ utilise ici un routage explicable par mots-clés, pas un modèle neuronal MoE entraîné.",
        "",
        "## Statistiques",
        "",
        f"- Taille de la source : {stats['source_bytes']} octets",
        f"- SHA-256 de la source : `{stats['source_sha256']}`",
        f"- Occurrences d’URL retenues : {stats['url_occurrences_accepted']}",
        f"- URL uniques : {stats['unique_urls']}",
        f"- Candidats rejetés (URL invalide ou contenant des identifiants) : {stats['rejected_url_candidates']}",
        "",
        "### Répartition par catégorie",
        "",
    ]
    lines += [f"- {key}: {value}" for key, value in stats["unique_by_category"].items()] or ["- Aucune URL extraite."]
    lines += ["", "### MoExiZ — poids de routage documentaire (heuristique)", ""]
    lines += [f"- {key}: {value:.6f}" for key, value in stats["expert_routing_document"].items()]
    lines += ["", "## RetroAct — comparaison au catalogue précédent", "", f"- Baseline : {diff['baseline'] or 'aucune'}",
              f"- Ajouts : {len(diff['added'])}", f"- Retraits : {len(diff['removed'])}", f"- Inchangés : {len(diff['unchanged'])}", "",
              "Cette comparaison est une proposition de révision; elle ne modifie pas le fichier source ni le catalogue précédent.", "",
              "## Limites et falsifiabilité", "",
              "- La complétude dépend des octets fournis en entrée et du motif d’extraction HTTP(S).",
              "- Comparer `unique_urls` et les URL exportées à un échantillon manuel; corriger le parseur si des URL sont manquées ou mal formées.",
              "- Le classement MoExiZ est falsifiable par des tests de cas attendus; les poids ne sont ni probabilités de vérité ni performance d’agents.",
              "- Les fichiers générés ne doivent pas être publiés avant vérification de confidentialité et des droits de partage.", ""]
    return "\n".join(lines)


def write_outputs(database: dict, stats: dict, diff: dict, out_dir: Path, input_name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "sources.json": (json.dumps(database, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        "report.md": render_report(stats, diff).encode("utf-8"),
        "retroact-diff.json": (json.dumps(diff, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    }
    for name, content in outputs.items():
        (out_dir / name).write_bytes(content)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "input_name": input_name,
        "input_sha256": stats["source_sha256"],
        "outputs_sha256": {name: sha256_bytes(content) for name, content in sorted(outputs.items())},
        "reproducibility_note": "Same input bytes, program version, and baseline produce byte-identical outputs.",
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local ACM/MoExiZ/RetroAct URL inventory and reproducible report")
    parser.add_argument("input", type=Path, help="UTF-8 text source, e.g. 'texte 105.txt'")
    parser.add_argument("--out", type=Path, default=Path("acm-output"), help="Output directory (default: acm-output)")
    parser.add_argument("--previous", type=Path, help="Previous sources.json for a read-only RetroAct diff")
    args = parser.parse_args(argv)
    try:
        raw = args.input.read_bytes()
        text = raw.decode("utf-8-sig")
        database, stats = analyze(text, raw)
        diff = compare_previous(database, args.previous)
        write_outputs(database, stats, diff, args.out, args.input.name)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2
    print(f"OK: {stats['unique_urls']} URL uniques; résultats dans {args.out}")
    print(f"SHA-256 source: {stats['source_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
