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
uv run DeCli.py --project "Project X" --client "Opdrachtgever"
uv run DeCli.py --project "Project X" --client "Opdrachtgever" --auto
uv run DeCli.py --project "Project X" --client "Opdrachtgever" --auto --cat 1,3
uv run DeCli.py --project "Project X" --client "Opdrachtgever" --auto --xcat 4
uv run DeCli.py --project "Project X" --client "Opdrachtgever" --auto --month 5
uv run DeCli.py --project "Project X" --client "Opdrachtgever" --auto --sort-week
uv run DeCli.py --project "Project X" --client "Opdrachtgever" --auto --inbox src
uv run DeCli.py --project "Project X" --client "Opdrachtgever" --classic
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
src: "/pad/naar/TeDeclareren"     # optioneel, default = base
rekeninghouder: "J. Doe"
iban: "NL00 BANK 0000 0000 00"
categorie_mappen:
  1-eten: "eten"
  2-reizen: "reizen"
  3-accomodaties: "accomodaties"
  4-overig: "overig"
bic_lookup:                       # optioneel, defaults voor NL banken
  RABO: RABONL2U
  INGB: INGBNL2A
```

## Mapstructuur

```
declaraties/
|-- .gitignore
|-- pyproject.toml
|-- DeCli.py
|-- config.yaml              # persoonlijk -- niet in git
|-- config.example.yaml
|-- README.md
|-- LICENSE
|-- TODO.md
|-- TeDeclareren/            # inbox (src) -- optioneel
|-- eten/                    # w20/ w21/ ... of losse PDF's
|-- reizen/
|-- accomodaties/
|-- overig/
|-- bonnetjes/               # Syncthing target -- niet in git
\-- declaratie_overzichten/  # output -- niet in git
```

## Features

### Invoer
- Parse Rabobank `Details-afschrijving` PDF's
- Parse handmatige uitgaven uit `nb.txt`
- Auto-classificatie o.b.v. handelsnaam (`--auto`)
- Inbox scan: `--inbox <pad>` classificeert en kopieert/verplaatst naar juiste map
- `--src <pad>`: overschrijft `src`-pad uit config (werkt met `--inbox` en `--auto`)
- `--move`: verplaats i.p.v. kopiëren bij inbox scan
- **Hash-based duplicate detectie**: tijdens `--inbox` worden alle PDF's in de categorie-mappen
  gehasht (MD5). Nieuwe PDF's in de inbox worden vergeleken — bij een match wordt de PDF
  overgeslagen (`[DUP]`). Zo voorkom je dubbele verwerking, ook als de bestandsnaam verschilt.

### Filteren & selecteren
- `--cat <spec>`: alleen geselecteerde categorieën (bijv. `1,3` of `1-3`)
- `--xcat <spec>`: sluit categorieën uit (bijv. `1,4` of `2-4`)
- `--weken <nrs>`: filter op weeknummers (bijv. `20 21`)
- `--month <nr/naam>`: filter op maand (bijv. `5` of `mei`)
- Combinaties mogelijk: `--cat 1,2 --xcat 2` = alleen categorie 1

### Weergave
- `--sort-week`: groepeer transacties per week met week-headers
- `--classic`: klassieke stijl (Times-Roman / Tinos Nerd Font)
- `--modern`: moderne stijl (Helvetica, standaard)

### Output
- Per-categorie PDF's met QR-code (EPC/SCT) voor bankoverschrijving
- Gecombineerde PDF met voorpagina (matrix, bronbestanden-tree, bladwijzers)
- QR-code bevat BIC — automatisch opgezocht uit IBAN (RABO → RABONL2U)
- ASCII-tabel voor e-mail
- ZIP-archief met alle bronbestanden + PDF's
- `--pdf-to-front`: kopieer gecombineerde PDF naar de werkmap
- `--no-qr`: geen QR-codes in PDF's
- `--no-cmd`: verberg CLI-commando in PDF

### Overig
- `--rekening`: toon bankrekeninggegevens
- `--qr <bedrag>`: genereer losse QR-code PNG
- `--config <pad>`: eigen configuratiebestand
- `--reset`: wis verwerkingstracking
- `--force-dec`: forceer genereren (testmodus, slaat state-check over, werkt state niet bij)
- BIC lookup via IBAN — configureerbaar in `bic_lookup` in config.yaml

## Alle CLI opties

```
  --config <pad>      Configuratie YAML (standaard: config.yaml)
  --project <naam>    Projectnaam
  --client <naam>     Opdrachtgever
  --weken <nrs>       Weeknummers (bijv. 20 21)
  --cat <spec>        Categorieen om mee te nemen (nummers, bijv. 1,3 of 1-3)
  --xcat <spec>       Categorieen om uit te sluiten (nummers, bijv. 1,4 of 1-3)
  --auto              Auto-classificatie o.b.v. transactiegegevens
  --inbox <pad>       Scan een aparte map met PDFs, classificeer auto
  --src <pad>         Overschrijf src-pad uit config (t.b.v. --inbox / --auto)
  --move              Verplaats bestanden uit inbox (ipv kopiëren)
  --rekening          Toon bankrekeninggegevens
  --qr <bedrag>       Genereer QR code PNG voor een bedrag (bv. 112.55)
  --no-qr             Geen QR codes in PDFs
  --pdf-to-front      Kopieer gecombineerde PDF naar werkmap
  --month <nr/naam>   Filter op maand (bijv. 3 of maart)
  --sort-week         Groepeer transacties per week met week-headers
  --no-cmd            Verberg CLI-commando in PDF
  --classic           Klassieke stijl (Tinos/Times-Roman serif)
  --modern            Moderne stijl (Helvetica, standaard)
  --reset             Wis verwerkingstracking
  --force-dec         Forceer genereren (testmodus, geen state update)
  --help, -h          Dit overzicht
```

## Licentie

MIT -- zie `LICENSE`
