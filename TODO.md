# TODO — Declaratie Generator (DeCli)

Alle wijzigingen op een **eigen branch**, pas na review naar `main`.

---

## Prioritijd

### P1. `nb.txt` met `[Headers]` per categorie
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

### P2. Bonnetjes — EXIF + OCR
**Branch:** `5-bonnetjes-exif-ocr`

| Onderdeel | Tool | Wat |
|-----------|------|-----|
| EXIF lezen | `Pillow` | Datum, GPS-coördinaten |
| OCR | `pytesseract` + Tesseract | Totaalbedrag, BTW-bedrag |
| Valuta heuristiek | Eigen regex | `totaal € XX,XX` of `btw € X,XX` |

Afbeelding in ZIP onder `bonnetjes/`, klikbare link in PDF.

---

### P3. Syncthing integratie
**Branch:** `6-syncthing`

- `--bon-dir <pad>` flag voor Syncthing-map
- Auto-import: scan map op nieuwe JPG/PNG
- Match op datum (EXIF) met transactie uit nb.txt of PDF
- Na import: verplaats naar `bonnetjes/{categorie}/`

---

### P4. (Suggestie) BTW-dashboard
**Branch:** `7-btw-dashboard`

Optioneel: genereer een extra overzicht met BTW-bedragen per categorie/maand. Handig voor btw-aangifte.

---

## Done

### --src flag + tilde expansie + hash-based duplicate check
**Commit:** `f9220c8`

- `--src <pad>` overschrijft `src` uit config voor `--inbox` / `--auto`
- `~` wordt geëxpandeerd naar thuismap op alle pad-argumenten
- **Hash-based duplicate check**: bij `--inbox` wordt van elke PDF in de categorie-mappen een MD5-hash berekend. Nieuwe PDFs in de inbox worden ook gehasht en vergeleken. Bij een match → `[DUP]` + overslaan. Zo voorkom je dat dezelfde bankafschrift per ongeluk opnieuw wordt verwerkt, ook als de bestandsnaam anders is.

### BIC lookup via IBAN voor QR-code
**Commit:** `56a3276`

- `BIC_LOOKUP` dict met 10 Nederlandse banken
- `gen_qr_png()` leest IBAN-prefix (bv. `NL97 RABO...` → `RABO` → `RABONL2U`) en vult BIC-veld in EPC QR-code
- Config uitbreidbaar via YAML: `bic_lookup: {RABO: RABONL2U, ...}`
- Onbekende prefix → BIC blijft leeg (geen crash)

### --month, --classic/--modern, Tinos Nerd Font
**Commits:** `b931214`, `9554589`

- `--month <nr/naam>` filter: transacties op maand selecteren
- `--classic` / `--modern` weergave stijlen (Times-Roman vs Helvetica)
- Tinos Nerd Font ondersteuning (serif met Nerd icons)

### organize_base + auto-classificatie + inbox
**Commits:** `ce271a2`, `cd94583`, `e8da477`

- `organize_base()`: auto-classificeer losse bestanden uit SRC en verplaats naar categorie-mappen in BASE
- `--auto` flag: volledig automatische verwerking op basis van classificatie
- `--inbox <pad>`: scan aparte map, classificeer en kopieer/verplaats naar juiste categorie-map
- Bronbestanden onder `src/`, ZIP naar `export/`
- `src/base` split: src=inbox, base=werkmap; src optioneel in config
- `--move`: verplaats i.p.v. kopiëren bij inbox scan

### --cat flag + --xcat fix + ranges
**Commit:** `6122012`

- `--cat <spec>`: selecteer categorieën om mee te nemen (i.p.v. alles)
- `--xcat` fixed: werd vóór load_config verwerkt, nu erna — werkt eindelijk
- Ranges (`1-3`), komma's en spaties ondersteund voor beide flags
- `parse_cat_spec()` helper voor gedeelde parse-logica

### --month filter in inbox scan
**Commit:** `0e7a252`

- `--month` werd niet toegepast tijdens `--inbox` scan, nu wel
- Overslagen transacties krijgen een melding

### --sort-week flag + bestandsnaam conventies
**Branch:** `2-sort-week` → gemerged naar `main`

- `--sort-week` flag: groepeer transacties per week in PDF met week-header balk (`dwh`) en week-subtotaal (`dwt`)
- `--xcat <nummers>` flag (exclude category, vervangt `--map`)
- Bestandsnaam conventie aangepast:
  - `declaratie_{cat}_{proj}_{ts}.pdf` (per-category)
  - `declaraties_{proj}_{ts}.pdf` (combined)
  - `declaratie_table_{proj}_{ts}.txt` (ASCII tabel)
  - `{yymmdd}-declaraties_{proj}.zip` (ZIP)
  - spaties in projectnaam vervangen door `_`

### Repo URL + CLI command in PDF
**Branch:** `3-repo-url` → gemerged naar `main`

- `--no-cmd` flag om CLI-commando in PDF en ASCII-tabel te verbergen
- Klikbare `DeCli` link met GitHub-repo (LINK_URI) op voorpagina en eindtotaal
- Nerd Font icoon (U+EA84, JetBrainsMonoNerdFont) naast "DeCli" link — werkt alleen als font lokaal geïnstalleerd is
- ASCII-tabel toont `Repository:` en `Commando:` regels
- Encoding fallback voor config YAML laden (UTF-8-sig → UTF-16)

---

## Workflow

```bash
git checkout -b 4-nb-headers
# werk
git add -A && git commit -m "nb.txt headers toegevoegd"
git push origin 4-nb-headers
# na review → merge naar main
```
