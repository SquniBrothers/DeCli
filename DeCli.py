#!/usr/bin/env python3
"""
Declaratie Generator CLI
========================
Genereert declaratie-PDF's per categorie op basis van Rabobank-transactie-PDF's
en handmatige (contante) uitgaven via nb.txt bestanden.

Gebruik: py genereer_declaraties.py
"""

import fitz
import os
import re
import shutil
import zipfile
import tempfile
import json
import io
import hashlib
import qrcode
import yaml
from datetime import datetime
from collections import defaultdict

# ===== CONFIGURATIE (wordt geladen in main()) =====
BASE = ""
SRC = ""
REKENINGHOUDER = ""
IBAN = ""
CATEGORIE_MAPPEN = {}
STATE_FILE = ""
OUT_DIR = ""
REPO_URL = "https://github.com/G2LB/DeCli/"
BIC_LOOKUP = {}  # wordt aangevuld uit config, daarna met defaults
NERD_FONT_PATH = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "Fonts", "JetBrainsMonoNerdFont-Regular.ttf")
NERD_GLYPH_GITHUB = "\uea84"  # nf-dev-github_badge
NERD_GLYPH_FOLDER = "\uf07c"   # nf-fa-folder
NERD_GLYPH_CALENDAR = "\uf073" # nf-fa-calendar
NERD_GLYPH_EURO = "\uf155"    # nf-fa-euro
NERD_GLYPH_MONEY = "\uf0d6"   # nf-fa-money
NERD_GLYPH_FILE = "\uf016"    # nf-fa-file_o
NERD_GLYPH_BANK = "\uf09c"    # nf-fa-credit_card
NERD_GLYPH_CASH = "\uf0d6"    # nf-fa-money
NERD_GLYPH_TAG = "\uf02b"     # nf-fa-tag
# Index van symbolen voor bonnetjes/OCR \u2014 zie nerdfont-symbols.md
NERD_GLYPH_JSON = "\ueb0f"     # nf-cod-json \u2014 JSON-metadata
NERD_GLYPH_LOCATION = "\uf041" # nf-fa-map_marker \u2014 GPS/locatie
NERD_GLYPH_IMAGE = "\uf03e"    # nf-fa-image \u2014 afbeelding
NERD_GLYPH_LINK_IMG = "\uf0c6" # nf-fa-paperclip \u2014 gekoppelde foto/bijlage
NERD_GLYPH_RECEIPT = "\uf543"  # nf-fa-receipt \u2014 bonnetje/kassabon
NERD_GLYPH_CHECK = "\uf00c"    # nf-fa-check \u2014 gematcht/geverifieerd

TINOS_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

FONTS_MODERN = {
    "body": "Helvetica",
    "bold": "Helvetica-Bold",
    "italic": "Helvetica-Oblique",
    "bold_italic": "Helvetica-BoldOblique",
    "mono": "Courier",
    "mono_bold": "Courier-Bold",
    "header": "Helvetica-Bold",
    "title": "Helvetica-Bold",
}

FONTS_CLASSIC = {
    "body": "Times-Roman",
    "bold": "Times-Bold",
    "italic": "Times-Italic",
    "bold_italic": "Times-BoldItalic",
    "mono": "Courier",
    "mono_bold": "Courier-Bold",
    "header": "Times-Bold",
    "title": "Times-Bold",
}

TINOS_KEYS = {"body_file", "bold_file", "italic_file", "body_name"}

def resolve_tinos_fonts():
    """Zoek Tinos Nerd Font in fonts/ naast het script.
    Valt terug op Times-Roman als font niet beschikbaar is."""
    reg = os.path.join(TINOS_FONT_DIR, "TinosNerdFont-Regular.ttf")
    bold = os.path.join(TINOS_FONT_DIR, "TinosNerdFont-Bold.ttf")
    italic = os.path.join(TINOS_FONT_DIR, "TinosNerdFont-Italic.ttf")
    if os.path.exists(reg) and os.path.exists(bold) and os.path.exists(italic):
        return {
            "body_file": reg,
            "bold_file": bold,
            "italic_file": italic,
            "body": "TinosNerdFont",
            "bold": "TinosNerdFont-Bold",
            "italic": "TinosNerdFont-Italic",
            "nerd_file": reg,
        }
    return None

def load_config(path):
    global BASE, SRC, REKENINGHOUDER, IBAN, CATEGORIE_MAPPEN, STATE_FILE, OUT_DIR, BIC_LOOKUP
    for enc in ("utf-8-sig", "utf-16"):
        try:
            with open(path, "r", encoding=enc) as f:
                cfg = yaml.safe_load(f)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise UnicodeDecodeError(f"Kan {path} niet lezen (geen UTF-8 of UTF-16)")
    BASE = os.path.expanduser(cfg["base"])
    SRC = os.path.expanduser(cfg.get("src", BASE))
    REKENINGHOUDER = cfg["rekeninghouder"]
    IBAN = cfg["iban"]
    CATEGORIE_MAPPEN = {k: os.path.join(BASE, v) for k, v in cfg["categorie_mappen"].items()}
    STATE_FILE = os.path.join(BASE, "declaratie_overzichten", ".state.json")
    OUT_DIR = os.path.join(BASE, "declaratie_overzichten")

    # BIC lookup: config overrides defaults
    user_bic = cfg.get("bic_lookup", {})
    defaults = {
        "RABO": "RABONL2U",
        "INGB": "INGBNL2A",
        "ABNA": "ABNANL2A",
        "SNSB": "SNSBNL2A",
        "KNAB": "KNABNL2H",
        "BUNQ": "BUNQNL2A",
        "ASNB": "ASNBNL2A",
        "TRIO": "TRIONL2U",
        "REVO": "REVOLT21",
        "N26": "NTSBDEB1",
    }
    defaults.update(user_bic)
    BIC_LOOKUP = defaults

month_map = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12
}

def parse_dutch_date(date_str):
    parts = date_str.strip().split()
    if len(parts) == 3:
        return datetime(int(parts[2]), month_map[parts[1].lower()], int(parts[0]))
    return None

# ----- State management -----

def lees_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed_refs": [], "last_project": "", "last_client": ""}

def schrijf_state(processed_refs, project, client):
    os.makedirs(OUT_DIR, exist_ok=True)
    data = {
        "processed_refs": list(processed_refs),
        "last_project": project,
        "last_client": client,
        "last_run": datetime.now().strftime("%d-%m-%Y %H:%M")
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ----- PDF parsing -----

def extract_transaction(pdf_path):
    doc = fitz.open(pdf_path)
    text = "".join(page.get_text() for page in doc)
    doc.close()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    merchant = amount = rentedatum = verwerkingsdatum = omschrijving = transactiereferentie = ""

    for i, line in enumerate(lines):
        if line.startswith("- ") and "€" in line:
            amount = line.replace("- ", "").strip()
            if i > 0:
                merchant = lines[i - 1]
            break

    for i, line in enumerate(lines):
        if line == "Rentedatum" and i + 1 < len(lines):
            rentedatum = lines[i + 1]
        if line == "Verwerkingsdatum" and i + 1 < len(lines):
            verwerkingsdatum = lines[i + 1]

    in_oms = False
    oms_lines = []
    for line in lines:
        if line == "Omschrijving":
            in_oms = True
            continue
        if in_oms:
            if line in ("Via", "Betaalautomaat", "iDEAL", "Rentedatum", "Verwerkingsdatum", "Transactiereferentie", "Kenmerk machtiging", "Tegenrekening", "Aangemaakt op"):
                break
            if line.startswith("NL") and len(line) > 15:
                break
            oms_lines.append(line)
    omschrijving = " ".join(oms_lines)

    for i, line in enumerate(lines):
        if line == "Transactiereferentie" and i + 1 < len(lines):
            transactiereferentie = lines[i + 1]
            break

    dt = parse_dutch_date(rentedatum) if rentedatum else None

    return {
        "merchant": merchant, "amount": amount,
        "rentedatum": rentedatum, "verwerkingsdatum": verwerkingsdatum,
        "omschrijving": omschrijving, "transactiereferentie": transactiereferentie,
        "date_obj": dt, "is_bank": True, "source": pdf_path
    }

def parse_date_from_suffix(text):
    """Haal een datum uit '@ DD-MM-YYYY' aan het einde van een string."""
    m = re.search(r"@\s*(\d{1,2})-(\d{1,2})-(\d{4})\s*$", text)
    if m:
        dag, maand, jaar = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(jaar, maand, dag), text[:m.start()].strip()
        except ValueError:
            pass
    return None, text

def parse_text_transactions(txt_path):
    transactions = []
    current_cat = None
    with open(txt_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Category header: [<nr>. <naam>]
            header_m = re.match(r'\[(\d+)\.\s*(.+)\]', line)
            if header_m:
                nr = header_m.group(1)
                name = header_m.group(2).strip().lower().replace(" ", "-")
                current_cat = None
                for cat_key in CATEGORIE_MAPPEN.keys():
                    if cat_key.startswith(nr + "-") or cat_key.endswith("-" + name) or cat_key == name:
                        current_cat = cat_key
                        break
                continue

            # Image attachment: !path/to/image
            if line.startswith("!"):
                img_path = line[1:].strip()
                if transactions:
                    transactions[-1].setdefault("images", []).append(img_path)
                continue

            raw = line.lstrip("- ").strip()
            dt, raw = parse_date_from_suffix(raw)
            m = re.search(r"EUR\s*([\d]+[.,][\d]+)", raw, re.IGNORECASE)
            if not m:
                continue
            amount_str = m.group(1)
            raw = raw[:m.start()].strip().rstrip(".,;")
            parts = raw.split(";", 1)
            description = parts[0].strip()
            comment = parts[1].strip() if len(parts) > 1 else ""
            if not description and comment:
                description = comment
                comment = ""
            amount_norm = amount_str.replace(",", ".")
            maand_nl = ["", "januari", "februari", "maart", "april", "mei", "juni",
                         "juli", "augustus", "september", "oktober", "november", "december"]
            rentedatum_str = f"{dt.day} {maand_nl[dt.month]} {dt.year}" if dt else ""
            transactions.append({
                "merchant": description,
                "amount": f"EUR {amount_norm}",
                "rentedatum": rentedatum_str,
                "verwerkingsdatum": "",
                "omschrijving": f"Contant/Anders - {comment}" if comment else "Contant/Anders",
                "transactiereferentie": f"nb_{os.path.basename(txt_path)}_{len(transactions)}",
                "date_obj": dt or datetime(2026, 1, 1),
                "is_bank": False,
                "source": txt_path,
                "category": current_cat,
                "images": [],
            })
    return transactions

def get_week_number(t):
    if t["date_obj"]:
        return f"w{t['date_obj'].isocalendar()[1]}"
    return "onbekend"

def parse_amount(s):
    m = re.search(r"[\d]+[.,][\d]{2}", s)
    return float(m.group().replace(",", ".")) if m else 0

def format_eur(a):
    return f"EUR {a:>7.2f}".replace(".", ",")

def short_date(dt):
    return dt.strftime("%d-%m-%Y") if dt else ""

def short_cat_name(cat_name):
    parts = cat_name.split("-", 1)
    return parts[1].capitalize() if len(parts) > 1 else cat_name.capitalize()

def bestands_hash(pad):
    h = hashlib.md5()
    with open(pad, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def gen_qr_png(iban, holder, amount_eur, description, bic=None):
    bare_iban = re.sub(r"\s+", "", iban).upper()
    holder = (holder or "").strip()[:70]
    description = (description or "").strip()[:140]
    if not bic:
        # Zoek BIC op basis van IBAN-prefix (bankidentificatie)
        prefix = re.sub(r"\d", "", bare_iban[:8]).lstrip("NL")
        bic = BIC_LOOKUP.get(prefix, "")
    bic = bic.strip().upper()[:11]
    bedrag = f"EUR{amount_eur:.2f}"
    qr_data = "\r\n".join([
        "BCD",
        "002",
        "1",
        "SCT",
        bic,
        holder,
        bare_iban,
        bedrag,
        "",
        description,
        ""
    ])
    qr = qrcode.QRCode(border=4, box_size=6)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def toon_rekening():
    print(f"  IBAN: {IBAN}")
    print(f"  t.n.v.: {REKENINGHOUDER}")
    print()

# ----- Auto-classificatie -----

CLASSIFICATIE_REGELS = [
    ("1-eten",        ["AH to go", "jumbo", "cafetaria", "pizzeria", "restaurant",
                        "doner company", "little india", "ah ", "lidl", "aldi",
                        "supermarkt", "eten", "food", "eethuis"]),
    ("2-reizen",      ["ns ", "ns reizigers", "ns-", "trein", "ov-chip",
                        "ovpay", "retour", "e-ticket", "ns e-ticket"]),
    ("3-accomodaties", ["de prince", "hotel", "booking.com", "appartement",
                        "bnb", "airbnb", "ccv*de prince"]),
    ("4-PBMs-overig",  ["groenhart", "werkkleding", "uniform", "gereedschap",
                        "kantoor", "drukwerk", "postnl", "dhl", "mondriaan"]),
]

def classificeer_transactie(t):
    """Bepaal categorie o.b.v. handelsnaam en omschrijving."""
    tekst = (t["merchant"] + " " + t["omschrijving"]).lower()
    for cat, keywords in CLASSIFICATIE_REGELS:
        for kw in keywords:
            if kw in tekst:
                return cat
    return None  # onbekend

def organize_base():
    """Scan SRC root voor losse bestanden, classificeer en verplaats naar categorie-mappen in BASE."""
    if not os.path.isdir(SRC):
        return
    moved = 0
    for f in sorted(os.listdir(SRC)):
        path = os.path.join(SRC, f)
        if os.path.isdir(path):
            continue
        if not (f.endswith(".pdf") and "Details-afschrijving" in f or
                f.endswith(".txt") and f != "README.txt"):
            continue

        cat = None
        if f.endswith(".pdf"):
            t = extract_transaction(path)
            if not t or not t["merchant"]:
                print(f"  [!] Kan transactie niet lezen: {f}")
                continue
            cat = classificeer_transactie(t)
        elif f.endswith(".txt"):
            txs = parse_text_transactions(path)
            if not txs:
                print(f"  [!] Kan transacties niet lezen: {f}")
                continue
            cat = classificeer_transactie(txs[0])

        # Map classificeer-resultaat naar CATEGORIE_MAPPEN keys
        if cat and cat not in CATEGORIE_MAPPEN:
            prefix = cat.split("-", 1)[0]
            cat = next((k for k in CATEGORIE_MAPPEN if k.startswith(prefix + "-")), None)
        if not cat:
            cat = next((k for k in CATEGORIE_MAPPEN if k.startswith("4-")), None)

        target_dir = CATEGORIE_MAPPEN.get(cat)
        if not target_dir:
            print(f"  [!] Geen doelmap voor '{f}' — overslaan")
            continue

        os.makedirs(target_dir, exist_ok=True)
        dst = os.path.join(target_dir, f)
        if not os.path.exists(dst):
            shutil.move(path, dst)
            print(f"  [MOVE] {f} -> {os.path.basename(target_dir)}/")
            moved += 1
        else:
            print(f"  [OK]   {f} staat al in {os.path.basename(target_dir)}/")
    if moved:
        print()

def toon_classificatie(transacties):
    """Toon per transactie de voorgestelde categorie."""
    rows = []
    for t in transacties:
        cat = classificeer_transactie(t)
        label = cat if cat else "?? ONBEKEND ??"
        d = short_date(t["date_obj"]) if t["rentedatum"] else "      -"
        rows.append((label, d, t["merchant"][:40], t["amount"]))
    # Sorteer op categorie
    rows.sort(key=lambda r: r[0])
    print(f"  {'Categorie':20s} {'Datum':12s} {'Omschrijving':42s} {'Bedrag':>8s}")
    print(f"  {'-'*20} {'-'*12} {'-'*42} {'-'*8}")
    for r in rows:
        print(f"  {r[0]:20s} {r[1]:12s} {r[2]:42s} {r[3]:>8s}")
    return rows

def scan_bron_duplicaten():
    """Scan alle bronmappen op dubbele bestanden voor verwerking."""
    warns = []
    hash_gezien = {}
    refs_gezien = {}

    for cat_name, cat_path in CATEGORIE_MAPPEN.items():
        if not os.path.isdir(cat_path):
            continue
        for root, dirs, files in os.walk(cat_path):
            for f in sorted(files):
                path = os.path.join(root, f)

                if f.endswith(".pdf") and "Details-afschrijving" in f:
                    # Hash-check voor PDFs (zelfde bestand, andere naam)
                    fhash = bestands_hash(path)
                    if fhash in hash_gezien:
                        vorige = hash_gezien[fhash]
                        warns.append(f"  [!] Dubbele PDF (zelfde inhoud, andere naam):")
                        warns.append(f"        {os.path.relpath(path, BASE)}")
                        warns.append(f"        {os.path.relpath(vorige, BASE)}")
                    else:
                        hash_gezien[fhash] = path

                    # Transactie referentie check
                    t = extract_transaction(path)
                    if t["transactiereferentie"]:
                        ref = t["transactiereferentie"]
                        if ref in refs_gezien:
                            vorige_ref = refs_gezien[ref]
                            warns.append(f"  [!] Dubbele transactie (zelfde referentie):")
                            warns.append(f"        {t['merchant'][:40]:40s} {t['amount']:>8s}")
                            warns.append(f"        {os.path.basename(path)}")
                            warns.append(f"        {os.path.basename(vorige_ref)}")
                        else:
                            refs_gezien[ref] = path

                elif f.endswith(".txt") and f != "README.txt":
                    # Dubbele regels binnen 1 txt-bestand
                    with open(path, "r", encoding="utf-8-sig") as fh:
                        regels = [r.strip() for r in fh if r.strip()]
                    gezien = set()
                    for r in regels:
                        norm = r.lower().strip()
                        if norm in gezien:
                            warns.append(f"  [!] Dubbele regel in {os.path.basename(path)}:")
                            warns.append(f"        {r[:70]}")
                        gezien.add(norm)

    return warns

def collect_transactions(base_path, week_filter=None):
    transactions = []
    seen_refs = set()
    for root, dirs, files in os.walk(base_path):
        folder = os.path.basename(root)
        if week_filter:
            wk = re.search(r"w(\d+)", folder)
            if wk and wk.group(1) not in week_filter and wk.group(0) not in week_filter:
                continue
        for f in sorted(files):
            path = os.path.join(root, f)
            if f.endswith(".pdf") and "Details-afschrijving" in f:
                t = extract_transaction(path)
                if t["merchant"]:
                    ref = t["transactiereferentie"]
                    if ref and ref in seen_refs:
                        continue
                    if ref:
                        seen_refs.add(ref)
                    transactions.append(t)
            elif f.endswith(".txt") and f != "README.txt":
                transactions.extend(parse_text_transactions(path))
    return transactions

def group_by_week(transactions):
    groups = {}
    for t in transactions:
        wk = get_week_number(t)
        groups.setdefault(wk, []).append(t)
    return {wk: sorted(groups[wk], key=lambda x: x["date_obj"] or datetime.min) for wk in sorted(groups)}

def vind_beschikbare_weken():
    weken = set()
    for cat_path in CATEGORIE_MAPPEN.values():
        if os.path.isdir(cat_path):
            for entry in os.listdir(cat_path):
                m = re.match(r"w(\d+)", entry)
                if m and os.path.isdir(os.path.join(cat_path, entry)):
                    weken.add(m.group(1))
    return sorted(weken, key=int)

def filter_by_month(txs, month):
    """Filter transacties op maandnummer (1-12). Houdt transacties zonder datum."""
    if month is None:
        return txs
    return [t for t in txs if t["date_obj"] is None or t["date_obj"].month == month]

def parse_cat_spec(raw, beschikbaar):
    """Parse --cat/--xcat waarden: nummers, ranges (1-3), naam-prefixen, komma/spatie gescheiden."""
    result = set()
    parts = [p for p in re.split(r'[,\s]+', raw) if p]
    for part in parts:
        range_m = re.match(r'^(\d+)\s*-\s*(\d+)$', part)
        if range_m:
            start, end = int(range_m.group(1)), int(range_m.group(2))
            result.update(range(start, end + 1))
        elif part.isdigit():
            result.add(int(part))
        else:
            result.update(i + 1 for i, k in enumerate(beschikbaar, 1) if k.startswith(part))
    return result

def check_onverwerkt(week_filter=None):
    state = lees_state()
    processed = set(state.get("processed_refs", []))
    onverwerkt = []
    for cat_name, cat_path in CATEGORIE_MAPPEN.items():
        if not os.path.isdir(cat_path):
            continue
        txs = collect_transactions(cat_path, week_filter)
        for t in txs:
            ref = t["transactiereferentie"]
            if ref and ref not in processed:
                onverwerkt.append((cat_name, t))
    return onverwerkt

# ----- PDF generation -----

def fi(fonts, style):
    """Geef kwargs dict voor insert_text: fontname (en fontfile indien beschikbaar)."""
    fn = fonts.get(style, "Helvetica")
    ff = fonts.get(style + "_file")
    if ff and os.path.exists(ff):
        return {"fontname": fn, "fontfile": ff}
    return {"fontname": fn}

_FALLBACK_BUILTIN = {
    "TinosNerdFont": "Times-Roman",
    "TinosNerdFont-Bold": "Times-Bold",
    "TinosNerdFont-Italic": "Times-Italic",
    "TinosNerdFont-BoldItalic": "Times-BoldItalic",
}

def gtl(text, fonts, style, fontsize):
    """Wrapper voor fitz.get_text_length — gebruikt built-in fallback voor custom fonts."""
    fn = _FALLBACK_BUILTIN.get(fonts.get(style, ""), fonts.get(style, "Helvetica"))
    return fitz.get_text_length(text, fontname=fn, fontsize=fontsize)

W, H, M = 595, 842, 50
CD = (0.15, 0.15, 0.25)
CA = (0.0, 0.3, 0.6)
CL = (0.9, 0.92, 0.95)

def wrap_text_lines(text, max_chars=80):
    lines = []
    while len(text) > max_chars:
        chunk = text[:max_chars]
        split = chunk.rfind('-')
        if split > max_chars - 20:
            lines.append(text[:split + 1])
            text = text[split + 1:].lstrip()
        else:
            lines.append(text[:max_chars])
            text = text[max_chars:]
    if text:
        lines.append(text)
    return lines

def dh(page, project, cat_label, fonts=FONTS_MODERN):
    page.draw_rect((M, M, W - M, M + 35), color=CA, fill=CA)
    page.insert_text((M + 15, M + 24), "Declaraties", fontsize=10, color=(1, 1, 1), **fi(fonts, "bold"))
    cw = gtl(project, fonts, "bold", 10)
    page.insert_text(((W - cw) / 2, M + 24), project, fontsize=10, color=(1, 1, 1), **fi(fonts, "bold"))
    rw = gtl(cat_label, fonts, "bold", 10)
    page.insert_text((W - M - 15 - rw, M + 24), cat_label, fontsize=10, color=(1, 1, 1), **fi(fonts, "bold"))

def df(page, pn, subtitle="", fonts=FONTS_MODERN):
    page.draw_rect((M, H - M - 20, W - M, H - M), color=CL, fill=CL)
    left = f"Pagina {pn}"
    if subtitle:
        left += f" - {subtitle}"
    page.insert_text((M + 10, H - M - 6), left, fontsize=8, color=(0.5, 0.5, 0.5), **fi(fonts, "body"))
    nw = datetime.now().strftime("%d-%m-%Y %H:%M")
    page.insert_text((W - M - 80, H - M - 6), nw, fontsize=8, color=(0.5, 0.5, 0.5), **fi(fonts, "body"))

def dwh(page, label, y, fonts=FONTS_MODERN):
    nerd_file = fonts.get("nerd_file", NERD_FONT_PATH)
    nf = os.path.exists(nerd_file)
    icon_w = 0
    icon_x = M + 10
    if nf:
        page.insert_text((icon_x, y + 5), NERD_GLYPH_CALENDAR, fontsize=10, color=CA, fontfile=nerd_file)
        icon_w = 14
    page.insert_text((icon_x + icon_w, y + 5), label, fontsize=12, color=CA, **fi(fonts, "bold"))
    return y + 26

def dtb(page, t, y, fonts=FONTS_MODERN):
    if y > H - M - 120:
        return False
    nerd_file = fonts.get("nerd_file", NERD_FONT_PATH)
    nf = os.path.exists(nerd_file)
    mer_lines = wrap_text_lines(t["merchant"], max_chars=60)
    for i, mer_line in enumerate(mer_lines):
        page.insert_text((M + 15, y), mer_line, fontsize=10, color=CD, **fi(fonts, "bold"))
        if i == 0:
            page.insert_text((W - M - 80, y), f"- {t['amount']}", fontsize=10, color=(0.6, 0.0, 0.0), **fi(fonts, "bold"))
        y += 16
    y += 2
    if t["is_bank"]:
        icon = NERD_GLYPH_BANK if nf else ""
        if nf:
            page.insert_text((M + 15, y), icon, fontsize=8, color=(0.5, 0.5, 0.5), fontfile=nerd_file)
        page.insert_text((M + 15 + (14 if nf else 0), y), "AF", fontsize=8, color=(0.5, 0.5, 0.5), **fi(fonts, "body"))
    else:
        icon = NERD_GLYPH_CASH if nf else ""
        if nf:
            page.insert_text((M + 15, y), icon, fontsize=8, color=(0.6, 0.4, 0.0), fontfile=nerd_file)
        page.insert_text((M + 15 + (14 if nf else 0), y), "Contant/Anders", fontsize=8, color=(0.6, 0.4, 0.0), **fi(fonts, "bold"))
    y += 14
    if t["omschrijving"]:
        lbl = "Omschrijving" if t["is_bank"] else "Opmerking"
        oms_lines = wrap_text_lines(f"{lbl}: {t['omschrijving']}")
        for oms_line in oms_lines:
            page.insert_text((M + 15, y), oms_line, fontsize=8, color=(0.3, 0.3, 0.3), **fi(fonts, "body"))
            y += 12
    if t["rentedatum"]:
        page.insert_text((M + 15, y), f"Rentedatum: {t['rentedatum']}", fontsize=8, color=(0.3, 0.3, 0.3), **fi(fonts, "body"))
        page.insert_text((M + 200, y), f"Verwerkingsdatum: {t['verwerkingsdatum']}", fontsize=8, color=(0.3, 0.3, 0.3), **fi(fonts, "body"))
    else:
        page.insert_text((M + 15, y), "Geen banktransactie", fontsize=8, color=(0.5, 0.5, 0.5), **fi(fonts, "italic"))
    y += 10
    # Bonnetjes / bijlagen — koppeling-afbeelding symbool (zie nerdfont-symbols.md)
    for img in t.get("images", []):
        icon = NERD_GLYPH_LINK_IMG if nf else ""
        ix = M + 15
        if nf:
            page.insert_text((ix, y), icon, fontsize=8, color=(0.6, 0.4, 0.0), fontfile=nerd_file)
            ix += 14
        arc = img.replace("\\", "/")
        label = f"Bonnetje: {arc}"
        page.insert_text((ix, y), label, fontsize=8, color=(0.3, 0.3, 0.8), **fi(fonts, "body"))
        lw = gtl(label, fonts, "body", 8)
        page.insert_link({
            "kind": fitz.LINK_URI,
            "from": fitz.Rect(ix, y - 8, ix + lw, y + 4),
            "uri": arc,
        })
        y += 12
    page.draw_line((M + 5, y), (W - M - 5, y), color=(0.85, 0.85, 0.85))
    return y + 20

def dwt(page, txs, y, fonts=FONTS_MODERN):
    total = sum(parse_amount(t["amount"]) for t in txs)
    y += 5
    page.draw_rect((M, y - 5, W - M, y + 15), color=(0.95, 0.95, 0.95), fill=(0.95, 0.95, 0.95))
    nerd_file = fonts.get("nerd_file", NERD_FONT_PATH)
    nf = os.path.exists(nerd_file)
    icon_w = 0
    if nf:
        page.insert_text((M + 10, y + 5), NERD_GLYPH_EURO, fontsize=10, color=CD, fontfile=nerd_file)
        icon_w = 14
    page.insert_text((M + 10 + icon_w, y + 5), "Week totaal:", fontsize=10, color=CD, **fi(fonts, "bold"))
    page.insert_text((W - M - 80, y + 5), f"EUR {total:.2f}", fontsize=10, color=(0.0, 0.4, 0.0), **fi(fonts, "bold"))
    return y + 25

def generate_category_pdf(category_name, transactions, output_path, project, client, show_qr=True, sort_week=False, fonts=FONTS_MODERN):
    doc = fitz.open()
    page = doc.new_page()
    page_num = 1
    dh(page, project, short_cat_name(category_name), fonts)
    y = M + 65

    gt = sum(parse_amount(t["amount"]) for t in transactions)

    def new_page():
        nonlocal page, page_num, y, tx_count
        df(page, page_num, short_cat_name(category_name), fonts)
        page = doc.new_page()
        page_num += 1
        dh(page, project, short_cat_name(category_name), fonts)
        y = M + 65
        tx_count = 0

    def draw_tx(t):
        nonlocal y, tx_count
        ny = dtb(page, t, y, fonts)
        if ny:
            y = ny
            tx_count += 1
        else:
            new_page()
            y = dtb(page, t, y, fonts) or (y + 20)
            tx_count = 1

    tx_count = 0
    if sort_week:
        weeks = group_by_week(transactions)
        for wk_label, wk_txs in weeks.items():
            if y > H - M - 160:
                new_page()
            y = dwh(page, f"Week {wk_label}", y, fonts)
            for t in wk_txs:
                if tx_count >= 6:
                    new_page()
                draw_tx(t)
            y = dwt(page, wk_txs, y, fonts)
    else:
        sorted_txs = sorted(transactions, key=lambda t: t["date_obj"] or datetime.min)
        for t in sorted_txs:
            if tx_count >= 6:
                new_page()
            draw_tx(t)

    y += 15
    page.draw_rect((M, y - 5, W - M, y + 18), color=CA, fill=CA)
    nerd_file = fonts.get("nerd_file", NERD_FONT_PATH)
    nf = os.path.exists(nerd_file)
    icon_w = 0
    if nf:
        page.insert_text((M + 10, y + 6), NERD_GLYPH_EURO, fontsize=11, color=(1, 1, 1), fontfile=nerd_file)
        icon_w = 14
    page.insert_text((M + 10 + icon_w, y + 6), "EINDTOTAAL", fontsize=11, color=(1, 1, 1), **fi(fonts, "bold"))
    page.insert_text((W - M - 80, y + 6), f"EUR {gt:.2f}", fontsize=11, color=(1, 1, 1), **fi(fonts, "bold"))
    y += 30

    page.insert_text((M + 10, y), f"Project: {project}", fontsize=9, color=CD, **fi(fonts, "bold"))
    y += 14
    page.insert_text((M + 10, y), f"Opdrachtgever: {client}", fontsize=9, color=CD, **fi(fonts, "bold"))
    y += 14
    if os.path.exists(STATE_FILE):
        st = lees_state()
        if st.get("last_run"):
            page.insert_text((M + 10, y), f"Eerder gegenereerd: {st['last_run']}", fontsize=8, color=(0.5, 0.5, 0.5), **fi(fonts, "body"))

    y += 10
    if show_qr:
        qr_label = f"{project} {short_cat_name(category_name).upper()}"
        qr_bytes = gen_qr_png(IBAN.replace(" ", ""), REKENINGHOUDER, gt, qr_label)
        qr_rect = fitz.Rect(W - M - 90, y, W - M - 10, y + 80)
        page.insert_image(qr_rect, stream=qr_bytes)
        info_x = M + 15
        info_lines = [
            f"Omschrijving: {qr_label}",
            f"Bedrag: EUR {gt:.2f}",
            f"IBAN: {IBAN}",
            f"t.n.v.: {REKENINGHOUDER}",
        ]
        for i, line in enumerate(info_lines):
            page.insert_text((info_x, y + i * 14), line, fontsize=8, color=CD, **fi(fonts, "body"))
        page.insert_text((W - M - 85, y + 85), "Scan met bank app", fontsize=8, color=(0.5, 0.5, 0.5), **fi(fonts, "body"))

    df(page, page_num, fonts=fonts)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    p = tmp.name
    tmp.close()
    doc.save(p)
    doc.close()
    os.replace(p, output_path)
    print(f"  [PDF] {output_path}")

def draw_frontpage_matrix(page, project, client, all_categories, grand_total, script_name, cli_command="", show_cmd=True, fonts=FONTS_MODERN):
    dh(page, project, "Voorpagina", fonts)
    nerd_file = fonts.get("nerd_file", NERD_FONT_PATH)
    nf = os.path.exists(nerd_file)
    y = M + 65
    page.insert_text((M + 15, y), "Declaratie Overzicht", fontsize=18, color=CA, **fi(fonts, "bold"))
    y += 35
    page.draw_line((M + 15, y), (W - M - 15, y), color=CA)
    y += 20
    page.insert_text((M + 15, y), f"Project: {project}", fontsize=11, color=CD, **fi(fonts, "bold"))
    y += 18
    page.insert_text((M + 15, y), f"Opdrachtgever: {client}", fontsize=11, color=CD, **fi(fonts, "bold"))
    y += 18
    page.insert_text((M + 15, y), f"Declarant: {REKENINGHOUDER}", fontsize=11, color=CD, **fi(fonts, "bold"))
    y += 18
    base_x = M + 15
    gegenereerd = f"Gegenereerd: {datetime.now().strftime('%d-%m-%Y %H:%M')} met "
    gw = gtl(gegenereerd, fonts, "body", 9)
    page.insert_text((base_x, y), gegenereerd, fontsize=9, color=(0.5, 0.5, 0.5), **fi(fonts, "body"))
    icon_w = 0
    if nf:
        page.insert_text((base_x + gw, y), NERD_GLYPH_GITHUB, fontsize=9, fontfile=nerd_file)
        icon_w = 10
    link_label = "DeCli"
    lx = base_x + gw + icon_w
    lw = gtl(link_label, fonts, "body", 9)
    page.insert_text((lx, y), link_label, fontsize=9, color=CA, **fi(fonts, "body"))
    page.insert_link({
        "kind": fitz.LINK_URI,
        "from": fitz.Rect(lx, y - 10, lx + lw, y + 4),
        "uri": REPO_URL,
    })
    y += 20
    if show_cmd and cli_command:
        page.insert_text((M + 15, y), cli_command, fontsize=8, color=(0.5, 0.5, 0.5), **fi(fonts, "mono"))
        y += 16
    y += 10
    page.draw_line((M + 15, y), (W - M - 15, y), color=CA)
    y += 10
    page.insert_text((M + 15, y), "Overzicht declaraties per categorie:", fontsize=10, color=CA, **fi(fonts, "bold"))
    y += 5
    page.draw_line((M + 15, y), (W - M - 15, y), color=CL)
    y += 8
    page.insert_text((M + 15, y), "Sectie", fontsize=9, color=CA, **fi(fonts, "bold"))
    page.insert_text((M + 70, y), "Categorie", fontsize=9, color=CA, **fi(fonts, "bold"))
    page.insert_text((M + 230, y), "Aantal", fontsize=9, color=CA, **fi(fonts, "bold"))
    page.insert_text((M + 295, y), "Bedrag", fontsize=9, color=CA, **fi(fonts, "bold"))
    page.insert_text((M + 430, y), "Pagina", fontsize=9, color=CA, **fi(fonts, "bold"))
    y += 5
    page.draw_line((M + 15, y), (W - M - 15, y), color=CL)
    y += 8
    row_info = []
    for i, (cat_name, txs) in enumerate(all_categories):
        cat_total = sum(parse_amount(t["amount"]) for t in txs)
        by = y
        icon_x = M + 15
        if nf:
            page.insert_text((icon_x, y), NERD_GLYPH_TAG, fontsize=10, color=CD, fontfile=nerd_file)
            icon_x += 14
        page.insert_text((icon_x, y), str(i + 1), fontsize=10, color=CD, **fi(fonts, "body"))
        page.insert_text((M + 70, y), short_cat_name(cat_name), fontsize=10, color=CD, **fi(fonts, "body"))
        page.insert_text((M + 230, y), str(len(txs)), fontsize=10, color=CD, **fi(fonts, "body"))
        page.insert_text((M + 295, y), f"EUR {cat_total:.2f}".replace(".", ","), fontsize=10, color=(0.0, 0.4, 0.0), **fi(fonts, "bold"))
        row_info.append((cat_name, by))
        y += 16
    page.draw_line((M + 15, y), (W - M - 15, y), color=CL)
    y += 8
    n_total = sum(len(txs) for _, txs in all_categories)
    by_total = y + 4
    page.insert_text((M + 70, y), "Totaal", fontsize=10, color=CA, **fi(fonts, "bold"))
    page.insert_text((M + 230, y), str(n_total), fontsize=10, color=CA, **fi(fonts, "bold"))
    page.insert_text((M + 295, y), f"EUR {grand_total:.2f}".replace(".", ","), fontsize=10, color=CA, **fi(fonts, "bold"))
    row_info.append(("EINDTOTAAL", by_total))
    y += 5
    page.draw_line((M + 15, y), (W - M - 15, y), color=CA)
    return row_info, y

def generate_combined_pdf(all_categories, output_path, project, client, show_qr=True, tree_text="", script_name="", cli_command="", show_cmd=True, sort_week=False, fonts=FONTS_MODERN):
    doc = fitz.open()
    nerd_file = fonts.get("nerd_file", NERD_FONT_PATH)
    nf = os.path.exists(nerd_file)
    grand_total = sum(parse_amount(t["amount"]) for _, txs in all_categories for t in txs)

    # ===== PASS 1: Create all pages =====

    # 1. Frontpage (matrix + bronbestanden tree)
    page = doc.new_page()
    row_info, y_after = draw_frontpage_matrix(page, project, client, all_categories, grand_total, script_name, cli_command, show_cmd, fonts)

    if tree_text:
        y = y_after + 15
        page.draw_line((M + 15, y), (W - M - 15, y), color=CL)
        y += 10
        page.insert_text((M + 15, y), "Bronbestanden:", fontsize=10, color=CA, **fi(fonts, "bold"))
        y += 20
        for line in tree_text.split("\n"):
            if y > H - M - 30:
                df(page, len(doc), "Voorpagina", fonts)
                page = doc.new_page()
                dh(page, project, "Voorpagina", fonts)
                y = M + 20
            page.insert_text((M + 15, y), line, fontsize=7, color=(0.2, 0.2, 0.2), **fi(fonts, "mono"))
            y += 10
    df(page, len(doc), "Voorpagina", fonts)

    # 2. Category pages with section numbers
    cat_start_pages = {}
    for cat_idx, (cat_name, transactions) in enumerate(all_categories):
        cat_total = sum(parse_amount(t["amount"]) for t in transactions)
        section_label = f"{cat_idx + 1}. {short_cat_name(cat_name)}"

        cat_start_pages[cat_name] = len(doc) + 1

        page = doc.new_page()
        dh(page, project, section_label, fonts)
        y = M + 65

        def combined_new_page():
            nonlocal page, y, tx_count
            df(page, len(doc), section_label, fonts)
            page = doc.new_page()
            dh(page, project, section_label, fonts)
            y = M + 65
            tx_count = 0

        def combined_draw_tx(t):
            nonlocal y, tx_count
            ny = dtb(page, t, y, fonts)
            if ny:
                y = ny
                tx_count += 1
            else:
                combined_new_page()
                y = dtb(page, t, y, fonts) or (y + 20)
                tx_count = 1

        tx_count = 0
        if sort_week:
            weeks = group_by_week(transactions)
            for wk_label, wk_txs in weeks.items():
                if y > H - M - 160:
                    combined_new_page()
                y = dwh(page, f"Week {wk_label}", y, fonts)
                for t in wk_txs:
                    if tx_count >= 6:
                        combined_new_page()
                    combined_draw_tx(t)
                y = dwt(page, wk_txs, y, fonts)
        else:
            sorted_txs = sorted(transactions, key=lambda t: t["date_obj"] or datetime.min)
            for t in sorted_txs:
                if tx_count >= 6:
                    combined_new_page()
                combined_draw_tx(t)

        y += 8
        page.draw_rect((M, y - 5, W - M, y + 15), color=(0.9, 0.92, 0.95), fill=(0.9, 0.92, 0.95))
        icon_x = M + 10
        if nf:
            page.insert_text((icon_x, y + 5), NERD_GLYPH_TAG, fontsize=10, color=CD, fontfile=nerd_file)
            icon_x += 14
        page.insert_text((icon_x, y + 5), f"Subtotaal {short_cat_name(cat_name)}:", fontsize=10, color=CD, **fi(fonts, "bold"))
        amt_text = f"EUR {cat_total:.2f}"
        aw = gtl(amt_text, fonts, "bold", 10)
        page.insert_text((W - M - 15 - aw, y + 5), amt_text, fontsize=10, color=CD, **fi(fonts, "bold"))
        y += 25

        if show_qr:
            qr_label = f"{project} {short_cat_name(cat_name).upper()}"
            qr_bytes = gen_qr_png(IBAN.replace(" ", ""), REKENINGHOUDER, cat_total, qr_label)
            qr_rect = fitz.Rect(W - M - 90, y, W - M - 10, y + 80)
            page.insert_image(qr_rect, stream=qr_bytes)
            info_x = M + 15
            info_lines = [
                f"Omschrijving: {qr_label}",
                f"Bedrag: EUR {cat_total:.2f}",
                f"IBAN: {IBAN}",
                f"t.n.v.: {REKENINGHOUDER}",
            ]
            for i, line in enumerate(info_lines):
                page.insert_text((info_x, y + i * 14), line, fontsize=8, color=CD, **fi(fonts, "body"))
            page.insert_text((W - M - 85, y + 85), "Scan met bank app", fontsize=8, color=(0.5, 0.5, 0.5), **fi(fonts, "body"))

        df(page, len(doc), section_label, fonts)

    total_page = len(doc) + 1

    # 3. Eindtotaal pagina
    page = doc.new_page()
    dh(page, project, "TOTAAL", fonts)
    y = M + 65
    page.insert_text((M + 20, y), "EINDTOTAAL ALLE CATEGORIEEN", fontsize=14, color=CA, **fi(fonts, "bold"))
    y += 100
    page.draw_line((M + 20, y), (W - M - 20, y), color=CA)
    y += 40
    page.insert_text((W - M - 100, y), f"EUR {grand_total:.2f}", fontsize=16, color=(0.0, 0.4, 0.0), **fi(fonts, "bold"))
    y += 120
    page.draw_line((M + 20, y), (W - M - 20, y), color=CA)
    y += 40
    page.insert_text((M + 20, y), f"Project: {project}", fontsize=10, color=CD, **fi(fonts, "bold"))
    y += 25
    page.insert_text((M + 20, y), f"Opdrachtgever: {client}", fontsize=10, color=CD, **fi(fonts, "bold"))
    y += 16
    base_x = M + 20
    gegenereerd = f"Gegenereerd: {datetime.now().strftime('%d-%m-%Y %H:%M')} met "
    gw_t = gtl(gegenereerd, fonts, "body", 9)
    page.insert_text((base_x, y), gegenereerd, fontsize=9, color=(0.5, 0.5, 0.5), **fi(fonts, "body"))
    icon_w = 0
    if nf:
        page.insert_text((base_x + gw_t, y), NERD_GLYPH_GITHUB, fontsize=9, fontfile=nerd_file)
        icon_w = 10
    link_label = "DeCli"
    lx = base_x + gw_t + icon_w
    lw = gtl(link_label, fonts, "body", 9)
    page.insert_text((lx, y), link_label, fontsize=9, color=CA, **fi(fonts, "body"))
    page.insert_link({
        "kind": fitz.LINK_URI,
        "from": fitz.Rect(lx, y - 10, lx + lw, y + 4),
        "uri": REPO_URL,
    })
    y += 18
    if show_cmd and cli_command:
        page.insert_text((M + 20, y), cli_command, fontsize=8, color=(0.5, 0.5, 0.5), **fi(fonts, "mono"))
    df(page, len(doc), fonts=fonts)

    # ===== PASS 2: Add page numbers -X- underlined + links =====
    fp = doc[0]
    all_keys = set(cat_start_pages.keys()) | {"EINDTOTAAL"}
    page_map = {**cat_start_pages, "EINDTOTAAL": total_page}
    for cat_name, by in row_info:
        if cat_name in all_keys:
            sp = page_map[cat_name]
            pg_text = f"-{sp}-"
            pw = gtl(pg_text, fonts, "body", 10)
            px = M + 430
            fp.insert_text((px, by), pg_text, fontsize=10, color=CD, **fi(fonts, "body"))
            fp.draw_line((px, by + 2), (px + pw, by + 2), color=CD)
            fp.insert_link({
                "kind": fitz.LINK_GOTO,
                "from": fitz.Rect(px - 2, by - 8, px + pw + 2, by + 6),
                "page": sp - 1,
            })

    # PDF bookmarks
    toc = []
    for cat_idx, (cat_name, _) in enumerate(all_categories):
        sp = cat_start_pages[cat_name]
        toc.append([1, f"{cat_idx + 1}. {short_cat_name(cat_name)}", sp])
    toc.append([1, "Eindtotaal", total_page])
    doc.set_toc(toc)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    p = tmp.name
    tmp.close()
    doc.save(p)
    doc.close()
    os.replace(p, output_path)
    print(f"  [PDF] {output_path}")

# ----- Tables -----

SEP = 88

def generate_txt_table(all_categories, project, client, cli_command=""):
    lines = []
    lines.append("Declaratie Overzicht - " + project)
    lines.append("=" * SEP)
    lines.append("")

    grand_total = 0
    for cat_name, txs in all_categories:
        lines.append(cat_name.upper())
        lines.append("-" * SEP)
        groups = group_by_week(txs)
        for week_label, week_txs in groups.items():
            lines.append(f"Week {week_label.replace('w', '')}")
            lines.append("-" * SEP)
            week_total = 0
            for t in week_txs:
                d = short_date(t["date_obj"]) if t["rentedatum"] else "      -"
                amt = format_eur(parse_amount(t["amount"]))
                typ = "B" if t["is_bank"] else "C"
                lines.append(f"  {d:>12s}  {t['merchant'][:36]:36s}  {amt:>10s}  [{typ}]")
                week_total += parse_amount(t["amount"])
            lines.append(f"  {'':>12s}  {'Week totaal:':36s}  {format_eur(week_total):>10s}")
            lines.append("")
        cat_total = sum(parse_amount(t["amount"]) for t in txs)
        grand_total += cat_total
        lines.append(f"  Totaal {cat_name}: {format_eur(cat_total)}")
        lines.append("-" * SEP)
        lines.append("")

    lines.append("=" * SEP)
    lines.append(f"EINDTOTAAL: {format_eur(grand_total)}")
    lines.append("=" * SEP)
    lines.append(f"Project: {project}")
    lines.append(f"Opdrachtgever: {client}")
    lines.append(f"Gegenereerd: {datetime.now().strftime('%d-%m-%Y %H:%M')}")
    lines.append(f"Repository: {REPO_URL}")
    if cli_command:
        lines.append(f"Commando: {cli_command}")
    lines.append("")
    return "\n".join(lines)

# ----- Zip -----

def create_project_zip(pdf_files, txt_files, bron_pdfs, table_text, output_zip, project, tree=None, bonnetjes=None):
    entries = []

    def add_entry(path):
        entries.append(path)

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf in pdf_files:
            arc = os.path.join("declaratie_pdfs", os.path.basename(pdf))
            zf.write(pdf, arc)
            add_entry(arc)
        for cat_name, pdf_path in bron_pdfs:
            arc = os.path.join("src", cat_name, os.path.basename(pdf_path))
            zf.write(pdf_path, arc)
            add_entry(arc)
        for txt in txt_files:
            rel = os.path.relpath(txt, BASE)
            parts = rel.split(os.sep)
            arc = os.path.join("src", *parts)
            zf.write(txt, arc)
            add_entry(arc)
        table_arc = f"declaratie_table_{project}.txt"
        zf.writestr(table_arc, table_text)
        add_entry(table_arc)

        # Bonnetjes bijlagen (arc_name behoudt de relatieve structuur uit nb.txt)
        for src_path, arc_name in (bonnetjes or []):
            if os.path.exists(src_path):
                zf.write(src_path, arc_name)
                add_entry(arc_name)
            else:
                print(f"  [!] Bonnetje niet gevonden: {src_path}")

        if tree is None:
            tree = build_zip_tree(entries)
        zf.writestr("list.txt", tree)

    print(f"  [ZIP] {output_zip}")

def build_zip_tree(entries):
    root = {}
    for e in sorted(entries):
        parts = e.replace("\\", "/").split("/")
        node = root
        for p in parts:
            node = node.setdefault(p, {})
    lines = []
    def walk(node, prefix, name, is_last):
        lines.append(f"{prefix}{name}")
        items = sorted(node.items())
        child_prefix = prefix + ("    " if is_last else "|   ")
        for i, (k, v) in enumerate(items):
            walk(v, child_prefix, k, i == len(items) - 1)
    items = sorted(root.items())
    for i, (k, v) in enumerate(items):
        walk(v, "", k, i == len(items) - 1)
    return "\n".join(lines)

# ----- CLI -----

def main():
    import sys

    # --help / -h check — na config laden zodat CATEGORIE_MAPPEN bekend is
    show_help = "--help" in sys.argv or "-h" in sys.argv

    cli_command = " ".join(sys.argv)

    print()
    print("  Declaratie Generator")
    print("  ====================")
    print()

    state = lees_state()
    default_project = state.get("last_project", "")
    default_client = state.get("last_client", "")

    # CLI args
    args = sys.argv[1:]
    arg_config = "config.yaml"
    arg_project = ""
    arg_client = ""
    arg_weken = None
    arg_cat_raw = None
    arg_xcat_raw = None
    arg_force_dec = False
    arg_auto = False
    arg_inbox = None
    arg_src_raw = None
    arg_move = False
    arg_reset = False
    arg_rekening = False
    arg_qr = False
    arg_no_qr = False
    arg_pdf_to_front = False
    arg_no_cmd = False
    arg_sort_week = False
    arg_month = None
    arg_classic = False
    arg_modern = False

    i = 0
    while i < len(args):
        if args[i] == "--no-cmd":
            arg_no_cmd = True
            i += 1
        elif args[i] == "--sort-week":
            arg_sort_week = True
            i += 1
        elif args[i] == "--config" and i + 1 < len(args):
            arg_config = args[i + 1]
            i += 2
        elif args[i] == "--project" and i + 1 < len(args):
            arg_project = args[i + 1]
            i += 2
        elif args[i] == "--client" and i + 1 < len(args):
            arg_client = args[i + 1]
            i += 2
        elif args[i] == "--weken" and i + 1 < len(args):
            arg_weken = args[i + 1].split()
            i += 2
        elif args[i] == "--cat" and i + 1 < len(args):
            arg_cat_raw = args[i + 1]
            i += 2
        elif args[i] == "--xcat" and i + 1 < len(args):
            arg_xcat_raw = args[i + 1]
            i += 2
        elif args[i] == "--auto":
            arg_auto = True
            i += 1
        elif args[i] == "--inbox" and i + 1 < len(args):
            arg_inbox = args[i + 1]
            i += 2
        elif args[i] == "--src" and i + 1 < len(args):
            arg_src_raw = args[i + 1]
            i += 2
        elif args[i] == "--move":
            arg_move = True
            i += 1
        elif args[i] == "--rekening":
            arg_rekening = True
            i += 1
        elif args[i] == "--qr" and i + 1 < len(args):
            arg_qr = args[i + 1]
            i += 2
        elif args[i] == "--no-qr":
            arg_no_qr = True
            i += 1
        elif args[i] == "--pdf-to-front":
            arg_pdf_to_front = True
            i += 1
        elif args[i] == "--month" and i + 1 < len(args):
            raw = args[i + 1]
            if raw.isdigit():
                arg_month = int(raw)
            elif raw.lower() in month_map:
                arg_month = month_map[raw.lower()]
            i += 2
        elif args[i] == "--classic":
            arg_classic = True
            i += 1
        elif args[i] == "--modern":
            arg_modern = True
            i += 1
        elif args[i] == "--reset":
            arg_reset = True
            i += 1
        elif args[i] == "--force-dec":
            arg_force_dec = True
            i += 1
        else:
            i += 1

    arg_config = os.path.expanduser(arg_config)
    load_config(arg_config)

    # Tilde expansion voor path argumenten
    if arg_inbox:
        arg_inbox = os.path.expanduser(arg_inbox)
    if arg_src_raw:
        arg_src_raw = os.path.expanduser(arg_src_raw)
        SRC = arg_src_raw  # overschrijf config-waarde

    tinos_paths = resolve_tinos_fonts()
    if arg_classic:
        fonts = {**FONTS_CLASSIC}
        if tinos_paths:
            fonts.update(tinos_paths)
    elif arg_modern:
        fonts = {**FONTS_MODERN}
    else:
        fonts = {**FONTS_MODERN}

    # Verwerk --cat en --xcat (ná load_config zodat CATEGORIE_MAPPEN bekend is)
    beschikbaar = list(CATEGORIE_MAPPEN.keys())
    if arg_cat_raw is not None:
        include = parse_cat_spec(arg_cat_raw, beschikbaar)
        maps_te_verwerken = [k for i, k in enumerate(beschikbaar, 1) if i in include]
        if arg_xcat_raw is not None:
            exclude = parse_cat_spec(arg_xcat_raw, beschikbaar)
            maps_te_verwerken = [k for i, k in enumerate(beschikbaar, 1) if i not in exclude and k in maps_te_verwerken]
    elif arg_xcat_raw is not None:
        exclude = parse_cat_spec(arg_xcat_raw, beschikbaar)
        maps_te_verwerken = [k for i, k in enumerate(beschikbaar, 1) if i not in exclude]
    else:
        maps_te_verwerken = None

    if show_help:
        print("  Gebruik: py DeCli.py [opties]")
        print()
        print("  Opties:")
        print("    --config <pad>      Configuratie YAML (standaard: config.yaml)")
        print("    --project <naam>    Projectnaam")
        print("    --client <naam>     Opdrachtgever")
        print("    --weken <nrs>       Weeknummers (bijv. 20 21)")
        print("    --cat <spec>        Categorieen om mee te nemen (nummers, bijv. 1,3 of 1-3)")
        print("    --xcat <spec>       Categorieen om uit te sluiten (nummers, bijv. 1,4 of 1-3)")
        print("    --auto              Auto-classificatie o.b.v. transactiegegevens")
        print("    --inbox <pad>       Scan een aparte map met PDFs, classificeer auto")
        print("    --src <pad>         Overschrijf src-pad uit config (t.b.v. --inbox / --auto)")
        print("    --move              Verplaats bestanden uit inbox (ipv kopiëren)")
        print("    --rekening          Toon bankrekeninggegevens")
        print("    --qr <bedrag>       Genereer QR code PNG voor een bedrag (bv. 112.55)")
        print("    --no-qr             Geen QR codes in PDFs")
        print("    --pdf-to-front      Kopieer gecombineerde PDF naar werkmap")
        print("    --month <nr/naam>   Filter op maand (bijv. 3 of maart)")
        print("    --sort-week         Groepeer transacties per week met week-headers")
        print("    --no-cmd            Verberg CLI-commando in PDF")
        print("    --classic           Klassieke stijl (Tinos/Times-Roman serif)")
        print("    --modern            Moderne stijl (Helvetica, standaard)")
        print("    --reset             Wis verwerkingstracking")
        print("    --force-dec         Forceer genereren (testmodus, geen state update)")
        print("    --help, -h          Dit overzicht")
        print()
        print("  Categorieen:")
        for i, (k, v) in enumerate(CATEGORIE_MAPPEN.items(), 1):
            print(f"    {i}. {k} ({os.path.basename(v)})")
        print()
        return

    if arg_rekening:
        print("  Bankrekeninggegevens:")
        print("  =====================")
        toon_rekening()
        if not arg_qr and not arg_project and not arg_inbox:
            return

    if arg_qr:
        try:
            bedrag = float(arg_qr)
        except ValueError:
            bedrag = parse_amount(f"EUR {arg_qr.replace(',', '.')}")
        qr_bytes = gen_qr_png(IBAN.replace(" ", ""), REKENINGHOUDER, bedrag, "QR betaling")
        qr_path = os.path.join(OUT_DIR, f"qr_{IBAN[:4]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(qr_path, "wb") as f:
            f.write(qr_bytes)
        print(f"  [QR] {qr_path}")
        print()
        if not arg_project and not arg_inbox:
            return

    if arg_reset:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
            print("  Tracking gereset. Alle declaraties worden als nieuw behandeld.\n")
        else:
            print("  Geen tracking om te resetten.\n")

    try:
        project = arg_project or input(f"  Projectnaam [{default_project}]: ").strip()
        if not project:
            project = default_project
        client = arg_client or input(f"  Opdrachtgever [{default_client}]: ").strip()
        if not client:
            client = default_client
    except (EOFError, OSError):
        project = arg_project or default_project or "declaraties"
        client = arg_client or default_client or "-"

    print()

    # Beschikbare weken tonen
    beschikbaar = vind_beschikbare_weken()
    if beschikbaar:
        print(f"  Beschikbare weken: {', '.join('w' + w for w in beschikbaar)}")
    else:
        print(f"  Geen weekmappen gevonden in {', '.join(CATEGORIE_MAPPEN.keys())}")

    # Scan op dubbele bronbestanden
    bron_dups = scan_bron_duplicaten()
    if bron_dups:
        print("  [!] DUPLICATEN GEVONDEN IN BRONBESTANDEN:")
        for w in bron_dups:
            print(w)
        print()

    # Onverwerkte transacties checken
    if arg_force_dec:
        print("  [!] FORCED modus — state wordt niet gelezen of bijgewerkt.\n")
    else:
        onverwerkt = check_onverwerkt()
        if onverwerkt:
            print(f"  Niet-verwerkte declaraties: {len(onverwerkt)}")
            for cat, t in onverwerkt[:5]:
                tag = "BANK" if t["is_bank"] else "CONTANT"
                print(f"    [{tag}] [{cat}] {t['merchant'][:40]:40s} {t['amount']}")
            if len(onverwerkt) > 5:
                print(f"    ... en {len(onverwerkt) - 5} meer")
        else:
            print("  Alle transacties zijn al verwerkt.")

    week_filter = arg_weken
    if week_filter is None and not arg_inbox:
        try:
            week_inp = input(f"\n  Te verwerken weken (bijv. 20 21, of leeg = alle): ").strip()
            week_filter = week_inp.split() if week_inp else None
        except (EOFError, OSError):
            week_filter = None

    month_filter = arg_month
    if month_filter is None and not arg_inbox:
        try:
            month_inp = input(f"  Maand (1-12, of leeg = alle): ").strip()
            if month_inp.isdigit():
                month_filter = int(month_inp)
        except (EOFError, OSError):
            month_filter = None

    print()

    # Mapfilter bepalen (index-based uitsluiten)
    if maps_te_verwerken is None and not arg_inbox:
        beschikbare_maps = [n for n, p in CATEGORIE_MAPPEN.items() if os.path.isdir(p)]
        print("  Mappen:")
        for i, m in enumerate(beschikbare_maps, 1):
            print(f"    {i}. {m}")
        try:
            map_inp = input(f"  Niet meenemen (nummers, bijv. 1,3 of 1-3, of leeg = alles): ").strip()
            if map_inp:
                exclude = parse_cat_spec(map_inp, beschikbare_maps)
                maps_te_verwerken = [m for i, m in enumerate(beschikbare_maps, 1) if i not in exclude]
        except (EOFError, OSError):
            maps_te_verwerken = None

    print()

    # Inbox handling: scan, classify, kopieer naar categorie mappen
    if arg_inbox:
        inbox_path = arg_inbox
        if not os.path.isdir(inbox_path):
            print(f"  [!] Inbox map niet gevonden: {inbox_path}\n")
            return

        print(f"  === INBOX SCAN: {inbox_path} ===")

        # Bouw hash-set van bestaande PDFs in categorie-mappen
        bekende_hashes = set()
        for cat_path in CATEGORIE_MAPPEN.values():
            if not os.path.isdir(cat_path):
                continue
            for root, dirs, files in os.walk(cat_path):
                for f in files:
                    if f.endswith(".pdf") and "Details-afschrijving" in f:
                        bekende_hashes.add(bestands_hash(os.path.join(root, f)))

        inbox_txs = []
        for f in sorted(os.listdir(inbox_path)):
            if f.endswith(".pdf") and "Details-afschrijving" in f:
                path = os.path.join(inbox_path, f)
                fhash = bestands_hash(path)
                if fhash in bekende_hashes:
                    print(f"  [DUP] {f} — staat al in categorie-mappen (overslaan)")
                    continue
                t = extract_transaction(path)
                if t["merchant"]:
                    t["categorie"] = classificeer_transactie(t) or "4-PBMs-overig"
                    inbox_txs.append(t)

        if month_filter is not None:
            before = len(inbox_txs)
            inbox_txs = filter_by_month(inbox_txs, month_filter)
            after = len(inbox_txs)
            if after < before:
                print(f"  ({before - after} transacties buiten maand {month_filter} overgeslagen)")
            elif after == 0:
                print("  Geen transacties in geselecteerde maand.\n")
                return

        if not inbox_txs:
            print("  Geen transacties gevonden in inbox.\n")
        else:
            print(f"  {len(inbox_txs)} transacties gevonden, classificatie:")
            print()
            toon_classificatie(inbox_txs)
            print()

            per_cat_inbox = defaultdict(list)
            for t in inbox_txs:
                per_cat_inbox[t["categorie"]].append(t)

            for cat, txs in per_cat_inbox.items():
                if cat in CATEGORIE_MAPPEN:
                    target_dir = CATEGORIE_MAPPEN[cat]
                    os.makedirs(target_dir, exist_ok=True)
                for t in txs:
                    src = t["source"]
                    if cat in CATEGORIE_MAPPEN:
                        dst = os.path.join(CATEGORIE_MAPPEN[cat], os.path.basename(src))
                        label = "MOVE" if arg_move else "COPY"
                        if not os.path.exists(dst):
                            if arg_move:
                                shutil.move(src, dst)
                            else:
                                shutil.copy2(src, dst)
                            print(f"  [{label}] {os.path.basename(src)} -> {cat}/")
                        else:
                            print(f"  [OK]   {os.path.basename(src)} staat al in {cat}/")
            print()

        arg_auto = True

    # Verwerking
    os.makedirs(OUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    proj = project.replace(" ", "_")
    yyyymmdd = datetime.now().strftime("%y%m%d")
    all_categories = []
    pdf_files = []
    txt_files = []
    all_processed_refs = set(state.get("processed_refs", []))
    new_refs = set()

    if arg_auto:
        organize_base()
        # Auto-classificatie: scan ALLE mappen, classificeer per transactie
        # Header-categorie uit nb.txt heeft voorrang op auto-classificatie
        alle_txs = []
        for cat_name, cat_path in CATEGORIE_MAPPEN.items():
            if os.path.isdir(cat_path):
                txs = collect_transactions(cat_path, arg_weken)
                for t in txs:
                    if t.get("category"):
                        t["categorie"] = t["category"]
                    else:
                        t["categorie"] = classificeer_transactie(t) or "4-PBMs-overig"
                alle_txs.extend(txs)

        alle_txs = filter_by_month(alle_txs, month_filter)

        if not alle_txs:
            print("  Geen transacties gevonden.")
            return

        print(f"  {len(alle_txs)} transacties gevonden, classificatie:")
        print()
        toon_classificatie(alle_txs)
        print()

        # Groepeer op geclassificeerde categorie
        per_cat = defaultdict(list)
        for t in alle_txs:
            per_cat[t["categorie"]].append(t)

        for cat_name in CATEGORIE_MAPPEN:
            if cat_name not in per_cat:
                continue
            if maps_te_verwerken and cat_name not in maps_te_verwerken:
                continue
            txs = per_cat[cat_name]
            print(f"=== {cat_name} ({len(txs)} transacties) ===")
            output = os.path.join(OUT_DIR, f"declaratie_{cat_name}_{proj}_{timestamp}.pdf")
            generate_category_pdf(cat_name, txs, output, project, client, show_qr=not arg_no_qr, sort_week=arg_sort_week, fonts=fonts)
            pdf_files.append(output)
            all_categories.append((cat_name, txs))

            for t in txs:
                ref = t["transactiereferentie"]
                if ref:
                    new_refs.add(ref)

        # Forced fallback: als cat/xcat filter alles uitsloot, neem alle categorieën
        if not all_categories and arg_force_dec and per_cat:
            print("  [FORCED] Geen categorieën geselecteerd — verwerk alle beschikbare:")
            for cat_name, txs in sorted(per_cat.items()):
                print(f"  + {cat_name} ({len(txs)} transacties)")
                output = os.path.join(OUT_DIR, f"declaratie_{cat_name}_{proj}_{timestamp}.pdf")
                generate_category_pdf(cat_name, txs, output, project, client, show_qr=not arg_no_qr, sort_week=arg_sort_week, fonts=fonts)
                pdf_files.append(output)
                all_categories.append((cat_name, txs))
                for t in txs:
                    ref = t["transactiereferentie"]
                    if ref:
                        new_refs.add(ref)

    else:
        # Collect all transactions, determine effective category per transaction
        alle_txs = []
        for cat_name, cat_path in CATEGORIE_MAPPEN.items():
            if not os.path.isdir(cat_path):
                continue
            if maps_te_verwerken and cat_name not in maps_te_verwerken:
                continue
            txs = collect_transactions(cat_path, week_filter)
            for t in txs:
                t["effective_category"] = t.get("category") or cat_name
            alle_txs.extend(txs)

        alle_txs = filter_by_month(alle_txs, month_filter)

        if not alle_txs:
            print("  Geen transacties gevonden.")
            return

        # Group by effective category
        per_cat = defaultdict(list)
        for t in alle_txs:
            per_cat[t["effective_category"]].append(t)

        for cat_name in CATEGORIE_MAPPEN:
            if cat_name not in per_cat:
                continue
            txs = per_cat[cat_name]
            print(f"=== {cat_name} ({len(txs)} transacties) ===")
            for t in txs:
                tag = "BANK" if t["is_bank"] else "CONTANT"
                print(f"    [{tag}] {t['merchant'][:35]:35s} {t['amount']:>8s}")

            output = os.path.join(OUT_DIR, f"declaratie_{cat_name}_{proj}_{timestamp}.pdf")
            generate_category_pdf(cat_name, txs, output, project, client, show_qr=not arg_no_qr, sort_week=arg_sort_week, fonts=fonts)
            pdf_files.append(output)
            all_categories.append((cat_name, txs))

            for t in txs:
                ref = t["transactiereferentie"]
                if ref:
                    new_refs.add(ref)

        # Forced fallback in non-auto path
        if not all_categories and arg_force_dec and per_cat:
            print("  [FORCED] Geen categorieën geselecteerd — verwerk alle beschikbare:")
            for cat_name, txs in sorted(per_cat.items()):
                print(f"  + {cat_name} ({len(txs)} transacties)")
                for t in txs:
                    tag = "BANK" if t["is_bank"] else "CONTANT"
                    print(f"      [{tag}] {t['merchant'][:35]:35s} {t['amount']:>8s}")
                output = os.path.join(OUT_DIR, f"declaratie_{cat_name}_{proj}_{timestamp}.pdf")
                generate_category_pdf(cat_name, txs, output, project, client, show_qr=not arg_no_qr, sort_week=arg_sort_week, fonts=fonts)
                pdf_files.append(output)
                all_categories.append((cat_name, txs))
                for t in txs:
                    ref = t["transactiereferentie"]
                    if ref:
                        new_refs.add(ref)

    if not all_categories:
        print("\nGeen declaraties om te verwerken.")
        return

    # Bron bestanden verzamelen (bankafschrift PDFs uit verwerkte mappen)
    bron_pdfs = []
    for cat_name, cat_path in CATEGORIE_MAPPEN.items():
        if not os.path.isdir(cat_path):
            continue
        if maps_te_verwerken and cat_name not in maps_te_verwerken:
            continue
        for root, dirs, files in os.walk(cat_path):
            for f in files:
                if f.endswith(".pdf") and "Details-afschrijving" in f:
                    bron_pdfs.append((cat_name, os.path.join(root, f)))
                elif f.endswith(".txt") and f != "README.txt":
                    txt_files.append(os.path.join(root, f))

    # Tabel
    print("\n=== ASCII TABLE (voor e-mail) ===")
    table = generate_txt_table(all_categories, project, client, cli_command if not arg_no_cmd else "")
    print(table)

    table_path = os.path.join(OUT_DIR, f"declaratie_table_{proj}_{timestamp}.txt")
    with open(table_path, "w", encoding="utf-8") as f:
        f.write(table)
    print(f"\n  [TABLE] {table_path}")

    # Tree listing voor list.txt en PDF
    tree_entries = []
    for pdf in pdf_files:
        tree_entries.append(os.path.join("declaratie_pdfs", os.path.basename(pdf)))
    for cat_name, pdf_path in bron_pdfs:
        tree_entries.append(os.path.join("src", cat_name, os.path.basename(pdf_path)))
    for txt in txt_files:
        rel = os.path.relpath(txt, BASE)
        tree_entries.append(os.path.join("src", rel))
    tree_entries.append(f"declaratie_table_{proj}.txt")
    tree_text = build_zip_tree(tree_entries)

    # Gecombineerde PDF
    combined_output = os.path.join(OUT_DIR, f"declaraties_{proj}_{timestamp}.pdf")
    generate_combined_pdf(all_categories, combined_output, project, client, show_qr=not arg_no_qr, tree_text=tree_text, script_name=os.path.basename(__file__), cli_command=cli_command, show_cmd=not arg_no_cmd, sort_week=arg_sort_week, fonts=fonts)
    pdf_files.append(combined_output)

    # Verzamel bonnetjes uit alle transacties
    bonnetjes = []
    for _, txs in all_categories:
        for t in txs:
            for img_rel in t.get("images", []):
                src = os.path.join(os.path.dirname(t["source"]), img_rel)
                # Normaliseer pad naar forward slashes voor ZIP
                arc = img_rel.replace("\\", "/")
                bonnetjes.append((src, arc))

    # Zip - tree opnieuw opbouwen met combined PDF + bonnetjes erbij
    zip_tree_entries = tree_entries + [os.path.join("declaratie_pdfs", os.path.basename(combined_output))]
    for _, arc_name in bonnetjes:
        zip_tree_entries.append(arc_name)
    zip_tree_text = build_zip_tree(zip_tree_entries)
    EXPORT_DIR = os.path.join(BASE, "export")
    os.makedirs(EXPORT_DIR, exist_ok=True)
    zip_path = os.path.join(EXPORT_DIR, f"{yyyymmdd}-declaraties_{proj}.zip")
    create_project_zip(pdf_files, txt_files, bron_pdfs, table, zip_path, project, zip_tree_text, bonnetjes=bonnetjes)

    # --pdf-to-front: kopieer gecombineerde PDF naar werkmap
    if arg_pdf_to_front:
        front_path = os.path.join(os.getcwd(), os.path.basename(combined_output))
        shutil.copy2(combined_output, front_path)
        print(f"  [FRONT] {front_path}")

    # State opslaan (niet in forced modus)
    if arg_force_dec:
        print("  [FORCED] State niet bijgewerkt.")
    else:
        all_processed_refs.update(new_refs)
        schrijf_state(all_processed_refs, project, client)

    print(f"\nGereed! Alles staat in: {OUT_DIR}")
    print(f"Zip bestand: {zip_path}")
    print()

if __name__ == "__main__":
    main()
