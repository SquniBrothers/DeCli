#!/usr/bin/env python3
"""
ocr_bon.py - OCR een bonnetje met PaddleOCR.

Doel (issue #5): ruwe tekst uit een echte bon-foto in de terminal.
Extra: haalt de DATUM (zoals op de bon) + BETAALMETHODE + ETABLISSEMENT eruit en
stelt een bestandsnaam voor in de conventie
    YYMMDD-betaalmethode-etablissement.ext   (bv. 260621-pin-ah.png).

Gebruik:
    python ocr_bon.py bon.jpg              # OCR + tekst + voorgestelde naam
    python ocr_bon.py bon.jpg --rename     # hernoem het bestand ook echt
    python ocr_bon.py bon.jpg --lang nl    # taalmodel (default: latin)

Werkt met PaddleOCR 2.x (.ocr) en 3.x (.predict).
"""
import argparse
import datetime as dt
import os
import re
import sys
import unicodedata
from pathlib import Path

# Skip de online model-bron-check (modellen zijn lokaal gecachet na 1e run).
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

# Betaalmethoden: (label, regex). Volgorde = prioriteit (specifiek eerst).
BETAALMETHODEN = [
    ("ideal", r"ideal"),
    ("applepay", r"apple\s*pay"),
    ("googlepay", r"google\s*pay"),
    ("creditcard", r"credit|mastercard|master\s*card|visa|amex|american express"),
    ("pin", r"\bpin\b|pinbetaling|pinnen|betaald met pin|maestro|v[\s.]?pay"),
    ("contant", r"contant|\bcash\b"),
]

MAANDEN = {
    "jan": 1, "feb": 2, "mrt": 3, "maa": 3, "mar": 3, "apr": 4, "mei": 5,
    "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "okt": 10, "oct": 10,
    "nov": 11, "dec": 12,
}


def ocr_lines(image_path, lang="en"):
    """Geef OCR-regels (in leesvolgorde) terug; werkt op Paddle 2.x en 3.x."""
    from paddleocr import PaddleOCR

    # enable_mkldnn=False omzeilt de oneDNN/PIR-crash op CPU (paddlepaddle 3.x).
    ocr = None
    for kwargs in ({"lang": lang, "enable_mkldnn": False}, {"lang": lang}, {}):
        try:
            ocr = PaddleOCR(**kwargs)
            break
        except (TypeError, ValueError):
            continue
    if ocr is None:
        raise RuntimeError("Kon PaddleOCR niet initialiseren")

    # 3.x pad (.predict -> lijst van resultaat-objecten met rec_texts)
    if hasattr(ocr, "predict"):
        try:
            res = ocr.predict(str(image_path))
            lines = []
            for page in res:
                texts = page.get("rec_texts") if hasattr(page, "get") else getattr(page, "rec_texts", None)
                if texts:
                    lines.extend(list(texts))
            if lines:
                return lines
        except Exception:
            pass

    # 2.x pad (.ocr -> [[ [box, (text, conf)], ... ]])
    res = ocr.ocr(str(image_path))
    if res and res[0]:
        return [line[1][0] for line in res[0]]
    return []


def parse_datum(text):
    """Zoek een datum in de OCR-tekst, geef (date, ruwe_string) of (None, None)."""
    # 1) numeriek: 21-06-2026 / 21/06/26 / 21.06.2026
    for m in re.finditer(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b", text):
        d, mo, y = (int(x) for x in m.groups())
        y += 2000 if y < 100 else 0
        try:
            return dt.date(y, mo, d), m.group(0)
        except ValueError:
            continue
    # 2) ISO: 2026-06-21
    for m in re.finditer(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", text):
        y, mo, d = (int(x) for x in m.groups())
        try:
            return dt.date(y, mo, d), m.group(0)
        except ValueError:
            continue
    # 3) tekst-maand: 21 jun 2026 / 21 JUNI 2026
    for m in re.finditer(r"\b(\d{1,2})[\s.]+([a-zA-Z]{3,})[\s.]+(\d{2,4})\b", text):
        d, mon, y = m.group(1), m.group(2)[:3].lower(), m.group(3)
        if mon in MAANDEN:
            y = int(y) + (2000 if int(y) < 100 else 0)
            try:
                return dt.date(y, MAANDEN[mon], int(d)), m.group(0)
            except ValueError:
                continue
    return None, None


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "", s).lower()
    return s


def parse_betaalmethode(text):
    """Herken de betaalmethode uit de OCR-tekst; 'onbekend' als geen match."""
    low = text.lower()
    for naam, pat in BETAALMETHODEN:
        if re.search(pat, low):
            return naam
    return "onbekend"


def parse_etablissement(lines):
    """Heuristiek: eerste betekenisvolle, overwegend alfabetische bovenregel."""
    for ln in lines[:6]:
        letters = sum(c.isalpha() for c in ln)
        if letters >= 3 and letters >= len(ln.replace(" ", "")) * 0.5:
            if not re.search(r"\d{2}[-/.]\d{2}", ln):  # geen datumregel
                return slugify(ln)[:24]
    return "onbekend"


def main():
    ap = argparse.ArgumentParser(description="OCR een bonnetje met PaddleOCR.")
    ap.add_argument("image", help="pad naar bon-foto (jpg/png)")
    ap.add_argument("--lang", default="en", help="taalmodel (default: en; werkt voor NL/Latijns schrift)")
    ap.add_argument("--rename", action="store_true", help="hernoem bestand naar YYMMDD-etablissement.ext")
    args = ap.parse_args()

    path = Path(args.image).expanduser()
    if not path.exists():
        sys.exit(f"[!] Bestand niet gevonden: {path}")

    print(f"[i] OCR ({args.lang}) op {path.name} ...", file=sys.stderr)
    lines = ocr_lines(path, args.lang)
    if not lines:
        sys.exit("[!] Geen tekst herkend.")

    text = "\n".join(lines)
    print("\n===== RUWE OCR-TEKST =====")
    print(text)
    print("==========================\n")

    datum, ruw = parse_datum(text)
    etab = parse_etablissement(lines)
    betaal = parse_betaalmethode(text)
    print(f"Etablissement : {etab}")
    print(f"Betaalmethode : {betaal}")
    ext = path.suffix.lower()
    if datum:
        print(f"Datum (bon)   : {datum.isoformat()}  (ruw: '{ruw}')")
        naam = f"{datum:%y%m%d}-{betaal}-{etab}{ext}"
    else:
        print("Datum (bon)   : NIET GEVONDEN")
        naam = f"GEENDATUM-{betaal}-{etab}{ext}"
    print(f"Voorgestelde naam: {naam}")

    if args.rename:
        doel = path.with_name(naam)
        if doel.exists():
            sys.exit(f"[!] Bestaat al, niet hernoemd: {doel.name}")
        path.rename(doel)
        print(f"[ok] Hernoemd -> {doel.name}")


if __name__ == "__main__":
    main()
