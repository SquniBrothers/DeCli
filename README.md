# Declaratie Generator (DeCli)

Genereert declaratie-PDF's per categorie op basis van Rabobank-transactie-PDF's
en handmatige uitgaven via `nb.txt` bestanden.

## Snelstart (uv)

```bash
# Installeer uv (zie https://docs.astral.sh/uv/)
# Of via pip: pip install uv

# Clone + setup
git clone https://github.com/G2LB/DeCli.git
cd decli
uv sync

# Config aanmaken
cp config.example.yaml config.yaml
# Vul config.yaml in met IBAN, naam, paden

# Draaien
uv run DeCli.py --project "Project X" --client "Opdrachtgever" --auto
uv run DeCli.py --project "Project X" --client "Opdrachtgever" --auto --xcat 4
uv run DeCli.py --project "Project X" --client "Opdrachtgever" --auto --sort-week
uv run DeCli.py --project "Project X" --client "Opdrachtgever" --auto --pdf-to-front
```

## Zonder uv (pip)

```bash
pip install pymupdf qrcode pyyaml
py DeCli.py --project "Project X" --client "Opdrachtgever" --auto
```

## Configuratie

```yaml
# config.yaml (kopieer van config.example.yaml en vul aan)
base: "/pad/naar/declaraties"
rekeninghouder: "J. Doe"
iban: "NL00 BANK 0000 0000 00"
categorie_mappen:
  1-eten: "eten"
  2-reizen: "reizen"
  3-accomodaties: "accomodaties"
  4-overig: "overig"
```

## Mapstructuur

```
declaraties/
|-- .gitignore
|-- pyproject.toml
|-- DeCli.py
|-- config.yaml          # persoonlijk -- niet in git
|-- config.example.yaml
|-- README.md
|-- LICENSE
|-- TODO.md
|-- eten/                # w20/ w21/ ... of losse PDF's
|-- reizen/
|-- accomodaties/
|-- overig/
|-- bonnetjes/           # Syncthing target -- niet in git
\-- declaratie_overzichten/   # output -- niet in git
```

## Features

- Parse Rabobank `Details-afschrijving` PDF's
- Parse handmatige uitgaven uit `nb.txt`
- Auto-classificatie o.b.v. handelsnaam
- Per-categorie PDF's met QR-code voor bankoverschrijving
- Gecombineerde PDF met voorpagina (matrix, bronbestanden-tree, bladwijzers)
- ASCII-tabel voor e-mail
- ZIP-archief met alle bronbestanden + PDF's
- `--pdf-to-front`: kopieer gecombineerde PDF naar de werkmap
- `--config <pad>`: eigen configuratiebestand
- `--no-cmd`: verberg CLI-commando in PDF
- `--sort-week`: groepeer transacties per week met week-headers
- `--xcat <nummers>`: sluit categorieen uit (bijv. --xcat 4)

## Licentie

MIT -- zie `LICENSE`
