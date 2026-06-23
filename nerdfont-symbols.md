# Nerd Font-symbolen — index voor DeCli

Symbolen die in de gegenereerde PDF's gebruikt worden (of bedoeld zijn) naast
transacties, bonnetjes en metadata. De glyphs worden getekend met het patroon in
`DeCli.py` (`page.insert_text((x, y), GLYPH, fontsize=8, fontfile=nerd_file)`), met een
vaste icoonkolom van 14px. Vereist een Nerd Font (Tinos Nerd Font of JetBrainsMono Nerd
Font); zonder font valt de code terug op tekst zonder icoon (`nf = os.path.exists(...)`).

## Inhoud

- [Bestaande symbolen](#bestaande-symbolen-declipy-r3644)
- [Nieuwe symbolen (deze branch) — voor bonnetjes/OCR](#nieuwe-symbolen-deze-branch--voor-bonnetjesocr)
- [Alternatieve codepoints (fallback per font-build)](#alternatieve-codepoints-fallback-per-font-build)
- [Verificatie tegen geïnstalleerd font](#verificatie-tegen-geïnstalleerd-font)

## Bestaande symbolen (`DeCli.py` r.36–44)

| Constante | Glyph | Codepoint | Nerd-naam | Gebruikt in |
|---|---|---|---|---|
| `NERD_GLYPH_GITHUB` | `` | U+EA84 | nf-dev-github_badge | voorpagina / eindtotaal-link |
| `NERD_GLYPH_FOLDER` | `` | U+F07C | nf-fa-folder | (vrij) |
| `NERD_GLYPH_CALENDAR` | `` | U+F073 | nf-fa-calendar | week-header `dwh()` |
| `NERD_GLYPH_EURO` | `` | U+F155 | nf-fa-euro | week-totaal `dwt()` |
| `NERD_GLYPH_MONEY` | `` | U+F0D6 | nf-fa-money | — |
| `NERD_GLYPH_FILE` | `` | U+F016 | nf-fa-file_o | — |
| `NERD_GLYPH_BANK` | `` | U+F09C | nf-fa-credit_card | transactie "AF" `dtb()` |
| `NERD_GLYPH_CASH` | `` | U+F0D6 | nf-fa-money | transactie "Contant" `dtb()` |
| `NERD_GLYPH_TAG` | `` | U+F02B | nf-fa-tag | voorpagina-matrix |

## Nieuwe symbolen (deze branch) — voor bonnetjes/OCR

| Constante | Glyph | Codepoint | Nerd-naam | Bedoeld gebruik | Status |
|---|---|---|---|---|---|
| `NERD_GLYPH_LINK_IMG` | `` | U+F0C6 | nf-fa-paperclip | gekoppelde foto/bijlage op de bonnetjes-rij | **gewired** in `dtb()` |
| `NERD_GLYPH_JSON` | `` | U+EB0F | nf-cod-json | transactie met OCR JSON-metadata | wacht op OCR (P2) |
| `NERD_GLYPH_LOCATION` | `` | U+F041 | nf-fa-map_marker | GPS/locatie uit EXIF | wacht op EXIF (P2) |
| `NERD_GLYPH_IMAGE` | `` | U+F03E | nf-fa-image | afbeelding (algemeen) | beschikbaar |
| `NERD_GLYPH_RECEIPT` | `` | U+F543 | nf-fa-receipt | kassabon/bonnetje | beschikbaar |
| `NERD_GLYPH_CHECK` | `` | U+F00C | nf-fa-check | bon ↔ banktransactie gematcht | wacht op auto-match |

### Inplug-punten in de code
- **Foto-koppeling** (`NERD_GLYPH_LINK_IMG`): `dtb()` bonnetjes-lus (r.~663) — al actief.
- **JSON-metadata / locatie**: zodra de EXIF/OCR-feature (TODO P2) per bon een dict met
  `gps` / `json_meta` oplevert, een conditioneel icoon vóór de bonnetjes-label tekenen
  (zelfde 14px-kolompatroon). Nu nog geen data → bewust niet gewired.
- **Match-vinkje** (`NERD_GLYPH_CHECK`): bij de auto-match bon↔banktransactie (brainstorm).

## Alternatieve codepoints (fallback per font-build)
Material-Design-glyphs (5-hex, bv. `U+F0626` md-code_json, `U+F034E` md-map_marker,
`U+F0824` md-receipt) zien er moderner uit maar zitten niet altijd in de **serif** Tinos-
patch. Font-Awesome/Codicon/Octicon (4-hex) zijn breder aanwezig → daarom de defaults
hierboven. Verifieer altijd tegen het font dat je daadwerkelijk gebruikt:

## Verificatie tegen geïnstalleerd font
Draai dit met het pad naar jouw Nerd Font; het meldt per glyph of die aanwezig is.

```python
import fitz  # pymupdf

FONT = "fonts/TinosNerdFont-Regular.ttf"  # of JetBrainsMonoNerdFont-Regular.ttf
GLYPHS = {
    "LINK_IMG": "", "JSON": "", "LOCATION": "",
    "IMAGE": "", "RECEIPT": "", "CHECK": "",
    "EURO": "", "CALENDAR": "",
}
font = fitz.Font(fontfile=FONT)
for name, ch in GLYPHS.items():
    ok = bool(font.has_glyph(ord(ch)))
    print(f"{name:10} U+{ord(ch):04X}  {'OK' if ok else 'ONTBREEKT'}")
```

Ontbreekt een glyph? Kies het alternatief uit de tabel of een ander Nerd-Font-build.
