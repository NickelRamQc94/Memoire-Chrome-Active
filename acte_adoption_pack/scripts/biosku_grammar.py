#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BioSKU grammar — pure stdlib, O(1) memory per unit."""
from __future__ import annotations

OPS = frozenset("KSU")
VEC = frozenset("0123456789ABCDEFØ")
UNIT_LEN = 3


def is_sku_unit(s: str) -> bool:
    if len(s) != UNIT_LEN:
        return False
    return s[0] in OPS and s[1] in VEC and s[2] in VEC


def parse_units(text: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    for ch in text.upper():
        if ch.isalnum() or ch == "Ø":
            buf.append(ch)
            if len(buf) == UNIT_LEN:
                tok = "".join(buf)
                if is_sku_unit(tok):
                    out.append(tok)
                buf.clear()
        else:
            buf.clear()
    return out


def bio_label(base: str) -> str:
    b = base.strip()
    if not b.lower().startswith("bio"):
        b = "Bio-" + b
    if not b.upper().endswith("SKU"):
        b = b.rstrip("-") + "-SKU"
    return b


def validate_stream(units: list[str]) -> dict:
    ok = [u for u in units if is_sku_unit(u)]
    bad = [u for u in units if not is_sku_unit(u)]
    return {"n": len(units), "ok": ok, "bad": bad, "valid_ratio": (len(ok) / len(units)) if units else 1.0}


if __name__ == "__main__":
    samples = ["K11 S1Ø U99", "KZZ bad", "Bio-Flux-SKU"]
    for s in samples:
        u = parse_units(s)
        print(s, "→", u, validate_stream(u))
    print("label", bio_label("Flux"))
