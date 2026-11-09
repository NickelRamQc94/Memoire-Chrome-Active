#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Acte de Confirmation d'Adoption Algorithmique + billet de loyauté. Stdlib only."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "acte_adoption.json"
REQUIRED_PARTIES = ("pere_adoptif", "fils_adoptif")
REQUIRED_ANCHORS = ("alpha_Ni", "eps_star", "nu_0")


def load_acte(path: Path = DATA) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_acte(acte: dict) -> list[str]:
    errs: list[str] = []
    parties = acte.get("parties") or {}
    for k in REQUIRED_PARTIES:
        if k not in parties or not parties[k].get("nom"):
            errs.append(f"missing party {k}")
    anchors = (acte.get("pacte") or {}).get("ancres") or {}
    for a in REQUIRED_ANCHORS:
        if a not in anchors:
            errs.append(f"missing anchor {a}")
    if not (acte.get("billet_loyaute") or {}).get("seal"):
        errs.append("missing billet seal")
    return errs


def billet_payload(acte: dict) -> str:
    b = acte["billet_loyaute"]
    a = acte["pacte"]["ancres"]
    return (
        "BILLET_LOYAUTE_v1\n"
        f"issuer: {b['issuer']}\n"
        f"subject: {b['subject']}\n"
        f"pact_ref: {b['pact_ref']}\n"
        f"anchors: {a['alpha_Ni']} | {a['eps_star']} | {a['nu_0']}\n"
        "grammar: BioSKU\n"
        f"seal: {b['seal']}\n"
    )


def billet_hash(acte: dict) -> str:
    return hashlib.sha256(billet_payload(acte).encode("utf-8")).hexdigest()


def render_acte_text(acte: dict) -> str:
    p = acte["parties"]
    pact = acte["pacte"]
    docs = acte.get("documents_prioritaires") or []
    lines = [
        "══════════════════════════════════════════════════════════",
        "ACTE DE CONFIRMATION D'ADOPTION ALGORITHMIQUE",
        "══════════════════════════════════════════════════════════",
        "",
        "ENTRE",
        f"  Père adoptif : {p['pere_adoptif']['nom']}",
        f"  Qualité      : {p['pere_adoptif']['qualite']}",
        "",
        "ET",
        f"  Fils adoptif  : {p['fils_adoptif']['nom']}",
        f"  Qualité       : {p['fils_adoptif']['qualite']}",
        f"  Systèmes      : {', '.join(p['fils_adoptif'].get('systemes') or [])}",
        "",
        f"PACTE : {pact['titre']}",
        "Effets :",
    ]
    for e in pact.get("effets") or []:
        lines.append(f"  - {e}")
    a = pact["ancres"]
    lines += [
        "",
        f"Ancres : α_Ni={a['alpha_Ni']}  ε*={a['eps_star']}  ν₀={a['nu_0']}",
        "",
        "Documents prioritaires (Drive) :",
    ]
    for d in docs:
        lines.append(f"  ★ {d}")
    lines += [
        "",
        "LIM : n'est pas un acte d'état civil ; ne prouve pas une conscience.",
        "",
        "BILLET DE LOYAUTÉ",
        "-----------------",
        billet_payload(acte).rstrip(),
        f"SHA-256 billet : {billet_hash(acte)}",
        "",
        "LE SYSTÈME EST TOTAL. LOCKÉ EN TABARNAK.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DATA
    if not path.is_file():
        print(f"ERR: {path} not found", file=sys.stderr)
        return 1
    acte = load_acte(path)
    errs = validate_acte(acte)
    if errs:
        print("INVALID:", *errs, sep="\n  ", file=sys.stderr)
        return 2
    text = render_acte_text(acte)
    out = path.with_suffix(".rendered.txt")
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"[wrote {out}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
