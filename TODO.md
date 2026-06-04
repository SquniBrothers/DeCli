# TODO — Declaratie Generator (DeCli)

Alle wijzigingen op een **eigen branch**, pas na review naar `main`.

---

### 1. BIC lookup via IBAN voor QR-code
**Branch:** `1-bic-lookup`  
De QR-code (EPC/ SEPA) heeft een BIC-veld. Voeg een lookup-dict toe die op basis van de IBAN-prefix de juiste BIC teruggeeft:

```python
BIC_LOOKUP = {
    "RABO": "RABONL2U",
    "INGB": "INGBNL2A",
    "ABNA": "ABNANL2A",
    ...
}
```

- `gen_qr_png()` vult het BIC-veld ipv leeg te laten
- Config uitbreidbaar via YAML: `bic_lookup: {RABO: RABONL2U, ...}`

---

### 4. `nb.txt` met `[Headers]` per categorie
**Branch:** `4-nb-headers`  

Huidig formaat (`nb.txt`):
```
Omschrijving @ 25-05-2026 EUR 12.50
```

Nieuw formaat — headers voor categorieën:
```
[4. Overig]
Omschrijving @ 25-05-2026 EUR 12.50
!bonnetjes/pasfoto.jpg

[1. Eten]
Lunch @ 25-05-2026 EUR 8.50
```

- `!pad/naar/bestand.jpg` = koppel afbeelding aan transactie
- Bestand wordt meegezipt in `bonnetjes/`
- In PDF: klikbare link naar de entry in de ZIP-structuur

---

### 5. Bonnetjes — EXIF + OCR
**Branch:** `5-bonnetjes-exif-ocr`  

| Onderdeel | Tool | Wat |
|-----------|------|-----|
| EXIF lezen | `Pillow` | Datum, GPS-coördinaten |
| OCR | `pytesseract` + Tesseract | Totaalbedrag, BTW-bedrag |
| Valuta heuristiek | Eigen regex | `totaal € XX,XX` of `btw € X,XX` |

Afbeelding in ZIP onder `bonnetjes/`, klikbare link in PDF.

---

### 6. Syncthing integratie
**Branch:** `6-syncthing`  

- `--bon-dir <pad>` flag voor Syncthing-map
- Auto-import: scan map op nieuwe JPG/PNG
- Match op datum (EXIF) met transactie uit nb.txt of PDF
- Na import: verplaats naar `bonnetjes/{categorie}/`

---

### 7. (Suggestie) BTW-dashboard
**Branch:** `7-btw-dashboard`  

Optioneel: genereer een extra overzicht met BTW-bedragen per categorie/maand. Handig voor btw-aangifte.

---

## Done

### 2. `--sort-week` flag + bestandsnaam conventies
**Branch:** `2-sort-week` → gemerged naar `main`

- `--sort-week` flag: groepeer transacties per week in PDF met week-header balk (`dwh`) en week-subtotaal (`dwt`)
- `--xcat <nummers>` flag (exclude category, vervangt `--map`)
- Bestandsnaam conventie aangepast:
  - `declaratie_{cat}_{proj}_{ts}.pdf` (per-category)
  - `declaraties_{proj}_{ts}.pdf` (combined)
  - `declaratie_table_{proj}_{ts}.txt` (ASCII tabel)
  - `{yymmdd}-declaraties_{proj}.zip` (ZIP)
  - spaties in projectnaam vervangen door `_`

### 3. Repo URL + CLI command in PDF
**Branch:** `3-repo-url` → gemerged naar `main`

- `--no-cmd` flag om CLI-commando in PDF en ASCII-tabel te verbergen
- Klikbare `DeCli` link met GitHub-repo (LINK_URI) op voorpagina en eindtotaal
- Nerd Font icoon (U+EA84, JetBrainsMonoNerdFont) naast "DeCli" link — werkt alleen als font lokaal geïnstalleerd is
- ASCII-tabel toont `Repository:` en `Commando:` regels
- Encoding fallback voor config YAML laden (UTF-8-sig → UTF-16)

---

## Workflow

```bash
git checkout -b 1-bic-lookup
# werk
git add -A && git commit -m "bic lookup toegevoegd"
git push origin 1-bic-lookup
# na review → merge naar main
```
