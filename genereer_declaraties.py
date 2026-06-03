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
import qrcode
from datetime import datetime
from collections import defaultdict

# ===== CONFIGURATIE (voorbeeld — zelf invullen) =====
BASE = r"/pad/naar/declaraties"
REKENINGHOUDER = "J. Doe"
IBAN = "NL00 BANK 0000 0000 00"
# =========================

CATEGORIE_MAPPEN = {
    "1-eten": os.path.join(BASE, "eten"),
    "2-reizen": os.path.join(BASE, "reizen"),
    "3-accomodaties": os.path.join(BASE, "accomodaties"),
    "4-PBMs-overig": os.path.join(BASE, "PBMs-overig"),
}

STATE_FILE = os.path.join(BASE, "declaratie_overzichten", ".state.json")
OUT_DIR = os.path.join(BASE, "declaratie_overzichten")

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
    with open(txt_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = line.lstrip("- ").strip()
            # Eerst datum eruit (staat achteraan, na @)
            dt, raw = parse_date_from_suffix(raw)
            # Dan bedrag eruit
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
                "is_bank": False, "source": txt_path
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

def gen_qr_png(iban, holder, amount_eur, description):
    # EPC QR code (ISO 20022) — punt als decimaalscheiding (volgens standaard)
    bare_iban = iban.replace(" ", "")
    bedrag = f"EUR{amount_eur:.2f}"
    qr_data = "\r\n".join([
        "BCD",
        "002",
        "1",
        "SCT",
        "",
        bare_iban,
        holder,
        bedrag,
        "EUR",
        description[:140],
        "",
        ""
    ])
    img = qrcode.make(qr_data, box_size=4)
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
    import hashlib
    warns = []
    hash_gezien = {}
    refs_gezien = {}

    def bestands_hash(pad):
        h = hashlib.md5()
        with open(pad, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

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

def dh(page, project, cat_label):
    page.draw_rect((M, M, W - M, M + 35), color=CA, fill=CA)
    page.insert_text((M + 15, M + 24), "Declaraties", fontsize=10, color=(1, 1, 1), fontname="Helvetica-Bold")
    cw = fitz.get_text_length(project, fontname="Helvetica-Bold", fontsize=10)
    page.insert_text(((W - cw) / 2, M + 24), project, fontsize=10, color=(1, 1, 1), fontname="Helvetica-Bold")
    rw = fitz.get_text_length(cat_label, fontname="Helvetica-Bold", fontsize=10)
    page.insert_text((W - M - 15 - rw, M + 24), cat_label, fontsize=10, color=(1, 1, 1), fontname="Helvetica-Bold")

def df(page, pn, subtitle=""):
    page.draw_rect((M, H - M - 20, W - M, H - M), color=CL, fill=CL)
    left = f"Pagina {pn}"
    if subtitle:
        left += f" - {subtitle}"
    page.insert_text((M + 10, H - M - 6), left, fontsize=8, color=(0.5, 0.5, 0.5), fontname="Helvetica")
    nw = datetime.now().strftime("%d-%m-%Y %H:%M")
    page.insert_text((W - M - 80, H - M - 6), nw, fontsize=8, color=(0.5, 0.5, 0.5), fontname="Helvetica")

def dwh(page, label, y):
    page.draw_rect((M, y - 10, W - M, y + 16), color=CL, fill=CL)
    page.insert_text((M + 10, y + 5), label, fontsize=12, color=CA, fontname="Helvetica-Bold")

def dtb(page, t, y):
    if y > H - M - 120:
        return False
    mer_lines = wrap_text_lines(t["merchant"], max_chars=60)
    for i, mer_line in enumerate(mer_lines):
        page.insert_text((M + 15, y), mer_line, fontsize=10, color=CD, fontname="Helvetica-Bold")
        if i == 0:
            page.insert_text((W - M - 80, y), f"- {t['amount']}", fontsize=10, color=(0.6, 0.0, 0.0), fontname="Helvetica-Bold")
        y += 16
    y += 2
    if t["is_bank"]:
        page.insert_text((M + 15, y), "AF", fontsize=8, color=(0.5, 0.5, 0.5), fontname="Helvetica")
    else:
        page.insert_text((M + 15, y), "Contant/Anders", fontsize=8, color=(0.6, 0.4, 0.0), fontname="Helvetica-Bold")
    y += 14
    if t["omschrijving"]:
        lbl = "Omschrijving" if t["is_bank"] else "Opmerking"
        oms_lines = wrap_text_lines(f"{lbl}: {t['omschrijving']}")
        for oms_line in oms_lines:
            page.insert_text((M + 15, y), oms_line, fontsize=8, color=(0.3, 0.3, 0.3), fontname="Helvetica")
            y += 12
    if t["rentedatum"]:
        page.insert_text((M + 15, y), f"Rentedatum: {t['rentedatum']}", fontsize=8, color=(0.3, 0.3, 0.3), fontname="Helvetica")
        page.insert_text((M + 200, y), f"Verwerkingsdatum: {t['verwerkingsdatum']}", fontsize=8, color=(0.3, 0.3, 0.3), fontname="Helvetica")
    else:
        page.insert_text((M + 15, y), "Geen banktransactie", fontsize=8, color=(0.5, 0.5, 0.5), fontname="Helvetica-Oblique")
    y += 10
    page.draw_line((M + 5, y), (W - M - 5, y), color=(0.85, 0.85, 0.85))
    return y + 20

def dwt(page, txs, y):
    total = sum(parse_amount(t["amount"]) for t in txs)
    y += 5
    page.draw_rect((M, y - 5, W - M, y + 15), color=(0.95, 0.95, 0.95), fill=(0.95, 0.95, 0.95))
    page.insert_text((M + 10, y + 5), "Week totaal:", fontsize=10, color=CD, fontname="Helvetica-Bold")
    page.insert_text((W - M - 80, y + 5), f"EUR {total:.2f}", fontsize=10, color=(0.0, 0.4, 0.0), fontname="Helvetica-Bold")
    return y + 25

def generate_category_pdf(category_name, transactions, output_path, project, client, show_qr=True):
    doc = fitz.open()
    page = doc.new_page()
    page_num = 1
    dh(page, project, short_cat_name(category_name))
    y = M + 65

    sorted_txs = sorted(transactions, key=lambda t: t["date_obj"] or datetime.min)
    gt = sum(parse_amount(t["amount"]) for t in sorted_txs)

    tx_count = 0
    for t in sorted_txs:
        if tx_count >= 6:
            df(page, page_num, short_cat_name(category_name))
            page = doc.new_page()
            page_num += 1
            dh(page, project, short_cat_name(category_name))
            y = M + 65
            tx_count = 0
        ny = dtb(page, t, y)
        if ny:
            y = ny
            tx_count += 1
        else:
            df(page, page_num, short_cat_name(category_name))
            page = doc.new_page()
            page_num += 1
            dh(page, project, short_cat_name(category_name))
            y = M + 65
            y = dtb(page, t, y) or (y + 20)
            tx_count = 1

    y += 15
    page.draw_rect((M, y - 5, W - M, y + 18), color=CA, fill=CA)
    page.insert_text((M + 10, y + 6), "EINDTOTAAL", fontsize=11, color=(1, 1, 1), fontname="Helvetica-Bold")
    page.insert_text((W - M - 80, y + 6), f"EUR {gt:.2f}", fontsize=11, color=(1, 1, 1), fontname="Helvetica-Bold")
    y += 30

    page.insert_text((M + 10, y), f"Project: {project}", fontsize=9, color=CD, fontname="Helvetica-Bold")
    y += 14
    page.insert_text((M + 10, y), f"Opdrachtgever: {client}", fontsize=9, color=CD, fontname="Helvetica-Bold")
    y += 14
    if os.path.exists(STATE_FILE):
        st = lees_state()
        if st.get("last_run"):
            page.insert_text((M + 10, y), f"Eerder gegenereerd: {st['last_run']}", fontsize=8, color=(0.5, 0.5, 0.5), fontname="Helvetica")

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
            page.insert_text((info_x, y + i * 14), line, fontsize=8, color=CD, fontname="Helvetica")
        page.insert_text((W - M - 85, y + 85), "Scan met bank app", fontsize=8, color=(0.5, 0.5, 0.5), fontname="Helvetica")

    df(page, page_num)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    p = tmp.name
    tmp.close()
    doc.save(p)
    doc.close()
    os.replace(p, output_path)
    print(f"  [PDF] {output_path}")

def generate_combined_pdf(all_categories, output_path, project, client, show_qr=True, tree_text=""):
    doc = fitz.open()
    page_num = 0
    grand_total = 0

    # Tree pages first — "Deze zip bevat:"
    if tree_text:
        for chunk in [tree_text[i:i+5000] for i in range(0, len(tree_text), 5000)]:
            page = doc.new_page()
            page_num += 1
            dh(page, project, "INHOUD")
            y = M + 20
            page.insert_text((M + 15, y), "Deze zip bevat:", fontsize=10, color=CA, fontname="Helvetica-Bold")
            y += 20
            for line in chunk.split("\n"):
                if y > H - M - 30:
                    df(page, page_num, "Bestandsstructuur")
                    page = doc.new_page()
                    page_num += 1
                    dh(page, project, "INHOUD")
                    y = M + 20
                page.insert_text((M + 15, y), line, fontsize=7, color=(0.2, 0.2, 0.2), fontname="Courier")
                y += 10
            df(page, page_num, "Bestandsstructuur")

    for cat_idx, (cat_name, transactions) in enumerate(all_categories):
        cat_total = sum(parse_amount(t["amount"]) for t in transactions)
        grand_total += cat_total
        sorted_txs = sorted(transactions, key=lambda t: t["date_obj"] or datetime.min)

        page = doc.new_page()
        page_num += 1
        dh(page, project, short_cat_name(cat_name))
        y = M + 65

        tx_count = 0
        for t in sorted_txs:
            if tx_count >= 6:
                df(page, page_num, short_cat_name(cat_name))
                page = doc.new_page()
                page_num += 1
                dh(page, project, short_cat_name(cat_name))
                y = M + 65
                tx_count = 0
            ny = dtb(page, t, y)
            if ny:
                y = ny
                tx_count += 1
            else:
                df(page, page_num, short_cat_name(cat_name))
                page = doc.new_page()
                page_num += 1
                dh(page, project, short_cat_name(cat_name))
                y = M + 65
                y = dtb(page, t, y) or (y + 20)
                tx_count = 1

        # Subtotaal per categorie
        y += 8
        page.draw_rect((M, y - 5, W - M, y + 15), color=(0.9, 0.92, 0.95), fill=(0.9, 0.92, 0.95))
        page.insert_text((M + 10, y + 5), f"Subtotaal {short_cat_name(cat_name)}:", fontsize=10, color=CD, fontname="Helvetica-Bold")
        page.insert_text((W - M - 80, y + 5), f"EUR {cat_total:.2f}", fontsize=10, color=CD, fontname="Helvetica-Bold")
        y += 25

        # QR code
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
                page.insert_text((info_x, y + i * 14), line, fontsize=8, color=CD, fontname="Helvetica")
            page.insert_text((W - M - 85, y + 85), "Scan met bank app", fontsize=8, color=(0.5, 0.5, 0.5), fontname="Helvetica")

        df(page, page_num, short_cat_name(cat_name))

    # Eindtotaal pagina
    page = doc.new_page()
    page_num += 1
    dh(page, project, "TOTAAL")
    y = M + 65
    page.insert_text((M + 20, y), "EINDTOTAAL ALLE CATEGORIEEN", fontsize=14, color=CA, fontname="Helvetica-Bold")
    y += 100
    page.draw_line((M + 20, y), (W - M - 20, y), color=CA)
    y += 40
    page.insert_text((W - M - 100, y), f"EUR {grand_total:.2f}", fontsize=16, color=(0.0, 0.4, 0.0), fontname="Helvetica-Bold")
    y += 120
    page.draw_line((M + 20, y), (W - M - 20, y), color=CA)
    y += 40
    page.insert_text((M + 20, y), f"Project: {project}", fontsize=10, color=CD, fontname="Helvetica-Bold")
    y += 25
    page.insert_text((M + 20, y), f"Opdrachtgever: {client}", fontsize=10, color=CD, fontname="Helvetica-Bold")
    y += 16
    page.insert_text((M + 20, y), f"Gegenereerd: {datetime.now().strftime('%d-%m-%Y %H:%M')}", fontsize=9, color=(0.5, 0.5, 0.5), fontname="Helvetica")
    df(page, page_num)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    p = tmp.name
    tmp.close()
    doc.save(p)
    doc.close()
    os.replace(p, output_path)
    print(f"  [PDF] {output_path}")

# ----- Tables -----

SEP = 88

def generate_txt_table(all_categories, project, client):
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
    lines.append("")
    return "\n".join(lines)

# ----- Zip -----

def create_project_zip(pdf_files, txt_files, bron_pdfs, table_text, output_zip, project, tree=None):
    entries = []

    def add_entry(path):
        entries.append(path)

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf in pdf_files:
            arc = os.path.join("declaratie_pdfs", os.path.basename(pdf))
            zf.write(pdf, arc)
            add_entry(arc)
        for cat_name, pdf_path in bron_pdfs:
            arc = os.path.join("bronbestanden", "bankafschriften", cat_name, os.path.basename(pdf_path))
            zf.write(pdf_path, arc)
            add_entry(arc)
        for txt in txt_files:
            rel = os.path.relpath(txt, BASE)
            arc = os.path.join("bronbestanden", rel)
            zf.write(txt, arc)
            add_entry(arc)
        table_arc = f"declaratie_table_{project}.txt"
        zf.writestr(table_arc, table_text)
        add_entry(table_arc)

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

    # --help / -h moet direct werken, zonder enige andere output
    if "--help" in sys.argv or "-h" in sys.argv:
        print("  Gebruik: py genereer_declaraties.py [opties]")
        print()
        print("  Opties:")
        print("    --project <naam>    Projectnaam")
        print("    --client <naam>     Opdrachtgever")
        print("    --weken <nrs>       Weeknummers (bijv. 20 21)")
        print("    --map <mappen>      Categorieen om uit te sluiten (nummers of namen, bijv. 1 4)")
        print("    --auto              Auto-classificatie o.b.v. transactiegegevens")
        print("    --inbox <pad>       Scan een aparte map met PDFs, classificeer auto")
        print("    --move              Verplaats bestanden uit inbox (ipv kopiëren)")
        print("    --rekening          Toon bankrekeninggegevens")
        print("    --qr <bedrag>       Genereer QR code PNG voor een bedrag (bv. 112.55)")
        print("    --no-qr             Geen QR codes in PDFs")
        print("    --reset             Wis verwerkingstracking")
        print("    --help, -h          Dit overzicht")
        print()
        print("  Categorieen:")
        for i, (k, v) in enumerate(CATEGORIE_MAPPEN.items(), 1):
            print(f"    {i}. {k} ({os.path.basename(v)})")
        print()
        return

    print()
    print("  Declaratie Generator")
    print("  ====================")
    print()

    state = lees_state()
    default_project = state.get("last_project", "")
    default_client = state.get("last_client", "")

    # CLI args: --project, --client, --weken, --map, --auto, --inbox, --reset, --rekening, --qr, --no-qr
    args = sys.argv[1:]
    arg_project = ""
    arg_client = ""
    arg_weken = None
    arg_maps = None
    arg_auto = False
    arg_inbox = None
    arg_move = False
    arg_reset = False
    arg_rekening = False
    arg_qr = False
    arg_no_qr = False

    i = 0
    while i < len(args):
        if args[i] == "--project" and i + 1 < len(args):
            arg_project = args[i + 1]
            i += 2
        elif args[i] == "--client" and i + 1 < len(args):
            arg_client = args[i + 1]
            i += 2
        elif args[i] == "--weken" and i + 1 < len(args):
            arg_weken = args[i + 1].split()
            i += 2
        elif args[i] == "--map" and i + 1 < len(args):
            raw_maps = args[i + 1].split()
            beschikbaar = list(CATEGORIE_MAPPEN.keys())
            skip = []
            for m in raw_maps:
                if m.isdigit():
                    skip.append(int(m))
                else:
                    skip.extend(i + 1 for i, k in enumerate(beschikbaar) if k.startswith(m))
            arg_maps = [k for i, k in enumerate(beschikbaar, 1) if i not in set(skip)]
            i += 2
        elif args[i] == "--auto":
            arg_auto = True
            i += 1
        elif args[i] == "--inbox" and i + 1 < len(args):
            arg_inbox = args[i + 1]
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
        elif args[i] == "--reset":
            arg_reset = True
            i += 1
        else:
            i += 1

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

    print()

    # Mapfilter bepalen (index-based uitsluiten)
    maps_te_verwerken = arg_maps
    if maps_te_verwerken is None and not arg_inbox:
        beschikbare_maps = [n for n, p in CATEGORIE_MAPPEN.items() if os.path.isdir(p)]
        print("  Mappen:")
        for i, m in enumerate(beschikbare_maps, 1):
            print(f"    {i}. {m}")
        try:
            map_inp = input(f"  Niet meenemen (nummers, bijv. 1 3, of leeg = alles): ").strip()
            if map_inp:
                skip = [int(x) for x in map_inp.split() if x.isdigit()]
                maps_te_verwerken = [m for i, m in enumerate(beschikbare_maps, 1) if i not in skip]
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
        inbox_txs = []
        for f in sorted(os.listdir(inbox_path)):
            if f.endswith(".pdf") and "Details-afschrijving" in f:
                path = os.path.join(inbox_path, f)
                t = extract_transaction(path)
                if t["merchant"]:
                    t["categorie"] = classificeer_transactie(t) or "4-PBMs-overig"
                    inbox_txs.append(t)

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
    all_categories = []
    pdf_files = []
    txt_files = []
    all_processed_refs = set(state.get("processed_refs", []))
    new_refs = set()

    if arg_auto:
        # Auto-classificatie: scan ALLE mappen, classificeer per transactie
        alle_txs = []
        for cat_name, cat_path in CATEGORIE_MAPPEN.items():
            if os.path.isdir(cat_path):
                txs = collect_transactions(cat_path, arg_weken)
                for t in txs:
                    t["categorie"] = classificeer_transactie(t) or "4-PBMs-overig"
                alle_txs.extend(txs)

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
            output = os.path.join(OUT_DIR, f"Declaratie_{cat_name}_{project}_{timestamp}.pdf")
            generate_category_pdf(cat_name, txs, output, project, client, show_qr=not arg_no_qr)
            pdf_files.append(output)
            all_categories.append((cat_name, txs))

            for t in txs:
                ref = t["transactiereferentie"]
                if ref:
                    new_refs.add(ref)

    else:
        for cat_name, cat_path in CATEGORIE_MAPPEN.items():
            if not os.path.isdir(cat_path):
                continue
            if maps_te_verwerken and cat_name not in maps_te_verwerken:
                continue
            print(f"=== {cat_name} ===")
            txs = collect_transactions(cat_path, week_filter)
            if not txs:
                print("  Geen transacties in geselecteerde weken.")
                continue

            print(f"  {len(txs)} transacties")
            for t in txs:
                tag = "BANK" if t["is_bank"] else "CONTANT"
                print(f"    [{tag}] {t['merchant'][:35]:35s} {t['amount']:>8s}")

            output = os.path.join(OUT_DIR, f"Declaratie_{cat_name}_{project}_{timestamp}.pdf")
            generate_category_pdf(cat_name, txs, output, project, client, show_qr=not arg_no_qr)
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
    table = generate_txt_table(all_categories, project, client)
    print(table)

    table_path = os.path.join(OUT_DIR, f"Declaratie_table_{project}_{timestamp}.txt")
    with open(table_path, "w", encoding="utf-8") as f:
        f.write(table)
    print(f"\n  [TABLE] {table_path}")

    # Tree listing voor list.txt en PDF
    tree_entries = []
    for pdf in pdf_files:
        tree_entries.append(os.path.join("declaratie_pdfs", os.path.basename(pdf)))
    for cat_name, pdf_path in bron_pdfs:
        tree_entries.append(os.path.join("bronbestanden", "bankafschriften", cat_name, os.path.basename(pdf_path)))
    for txt in txt_files:
        rel = os.path.relpath(txt, BASE)
        tree_entries.append(os.path.join("bronbestanden", rel))
    tree_entries.append(f"declaratie_table_{project}.txt")
    tree_text = build_zip_tree(tree_entries)

    # Gecombineerde PDF (met tree als eerste pagina's, zonder zichzelf in de tree)
    combined_output = os.path.join(OUT_DIR, f"Declaratie_gecombineerd_{project}_{timestamp}.pdf")
    generate_combined_pdf(all_categories, combined_output, project, client, show_qr=not arg_no_qr, tree_text=tree_text)
    pdf_files.append(combined_output)

    # Zip — tree opnieuw opbouwen met combined PDF erbij
    zip_tree_entries = tree_entries + [os.path.join("declaratie_pdfs", os.path.basename(combined_output))]
    zip_tree_text = build_zip_tree(zip_tree_entries)
    zip_path = os.path.join(BASE, f"{project}_declaraties_{timestamp}.zip")
    create_project_zip(pdf_files, txt_files, bron_pdfs, table, zip_path, project, zip_tree_text)

    # State opslaan
    all_processed_refs.update(new_refs)
    schrijf_state(all_processed_refs, project, client)

    print(f"\nGereed! Alles staat in: {OUT_DIR}")
    print(f"Zip bestand: {zip_path}")
    print()

if __name__ == "__main__":
    main()
