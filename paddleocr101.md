# PaddleOCR 101

Een praktische handleiding om bonnetjes/facturen met **PaddleOCR** om te zetten naar
tekst, en die tekst via een LLM (Qwen via Ollama) om te zetten naar een
DeCli-transactie in `nb.txt`.

Past in de bonnetjes-workflow uit [`syncthing101.md`](syncthing101.md):

```text
Receipts Folder → Syncthing → inbox → PaddleOCR → OCR-tekst → Qwen (Ollama) → JSON → nb.txt → DeCli
```

---

# Wat is PaddleOCR?

PaddleOCR is een gratis, open-source OCR-engine (door Baidu/PaddlePaddle).

Voordelen ten opzichte van Tesseract:

* Beter op foto's van bonnetjes (scheef, slechte belichting, thermisch papier)
* Ingebouwde tekstdetectie + rotatie-correctie
* Meertalig (incl. Nederlands via Latijns model)
* Volledig lokaal, geen cloudkosten, privacyvriendelijk

Nadelen:

* Zwaardere installatie dan Tesseract (PaddlePaddle runtime)
* Eerste run downloadt modellen (~10–50 MB per model)

---

# Installatie

## Vereisten

* Python 3.8 – 3.12
* `pip`
* ~1 GB schijfruimte voor modellen + runtime

## Windows

> **Let op:** PaddlePaddle heeft (nog) geen wheels voor Python 3.14. Gebruik 3.12.
> Met `uv` haal je die automatisch op.

Open PowerShell in de DeCli-map:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe paddlepaddle paddleocr
```

Zonder `uv` (klassiek, vereist een geïnstalleerde Python 3.12):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install paddlepaddle paddleocr
```

> CPU-only is prima voor bonnetjes. GPU (`paddlepaddle-gpu`) is alleen zinvol bij
> grote batches. Geteste versies: **paddlepaddle 3.3 + paddleocr 3.7**.

## Linux (Ubuntu/Debian)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install paddlepaddle paddleocr
```

Mogelijk extra systeembibliotheken nodig:

```bash
sudo apt install libgl1 libglib2.0-0
```

## Controleren

```bash
python -c "from paddleocr import PaddleOCR; print('paddleocr ok')"
```

Bij de eerste echte run worden de detectie-, rotatie- en herkenningsmodellen
automatisch gedownload naar `~/.paddleocr/`.

---

# Snelle test

Het kant-en-klare script `ocr_bon.py` (in de repo) doet alles ineens — ruwe tekst
+ datum + etablissement + voorgestelde bestandsnaam:

```powershell
.\.venv\Scripts\python.exe ocr_bon.py "test\bon.jpg"
.\.venv\Scripts\python.exe ocr_bon.py "test\bon.jpg" --rename   # hernoem ook echt
```

Uitvoer (voorbeeld, echte bon):

```text
===== RUWE OCR-TEKST =====
Groszek Delicatessen
21-6-2026 20:50:18
Totaal bedrag/    11,40
Totaal BTW         1,21
==========================
Etablissement : groszekdelicatessen
Betaalmethode : pin
Datum (bon)   : 2026-06-21  (ruw: '21-6-2026')
Voorgestelde naam: 260621-pin-groszekdelicatessen.jpeg
```

> De eerste run downloadt de PP-OCR-modellen (eenmalig, ~enkele tientallen MB)
> naar `C:\Users\<jij>\.paddlex\official_models\`.

---

# Tekst extraheren naar platte regels

Voor DeCli wil je de OCR-regels samenvoegen tot één tekstblok dat de LLM kan lezen:

```python
from paddleocr import PaddleOCR

def ocr_to_text(image_path: str) -> str:
    # enable_mkldnn=False vermijdt de oneDNN/PIR-crash op CPU (paddle 3.x)
    ocr = PaddleOCR(lang="en", enable_mkldnn=False)
    lines = []
    for page in ocr.predict(image_path):           # 3.x API: .predict()
        lines.extend(page.get("rec_texts") or [])
    return "\n".join(lines)

print(ocr_to_text("bon.jpg"))
```

> `lang="en"` werkt prima voor Nederlands (Latijns schrift + cijfers).
> `lang="latin"` bestaat **niet** meer in de PP-OCRv5/v6-modellen van paddleocr 3.x.

---

# Velden herkennen (heuristiek, zonder LLM)

Voor simpele bonnen volstaat regex. Dit pakt **totaal**, **BTW** en **datum**:

```python
import re

def parse_velden(text: str) -> dict:
    bedrag = r"(\d+[.,]\d{2})"
    totaal = re.search(rf"totaal\D*{bedrag}", text, re.IGNORECASE)
    btw    = re.search(rf"btw\D*{bedrag}", text, re.IGNORECASE)
    datum  = re.search(r"(\d{2})[-/](\d{2})[-/](\d{4})", text)
    return {
        "totaal": totaal.group(1).replace(".", ",") if totaal else None,
        "btw":    btw.group(1).replace(".", ",") if btw else None,
        "datum":  "-".join(datum.groups()) if datum else None,
    }
```

Heuristiek is broos bij rommelige bonnen — gebruik dan de LLM-stap hieronder.

---

# Velden herkennen met de LLM (Qwen via Ollama)

Robuuster dan regex. De LLM krijgt de OCR-tekst en geeft gestructureerde JSON terug.

## Ollama + Qwen installeren

```bash
# https://ollama.com
ollama pull qwen2.5:7b
```

## Extractie

```python
import json, requests

PROMPT = """Je krijgt OCR-tekst van een bon. Geef ALLEEN JSON terug:
{"merchant": str, "datum": "dd-mm-jjjj", "totaal": "12,45", "btw": "1,03", "categorie": str|null}
OCR-tekst:
""" + "{tekst}"

def extract_llm(tekst: str) -> dict:
    r = requests.post("http://localhost:11434/api/generate", json={
        "model": "qwen2.5:7b",
        "prompt": PROMPT.format(tekst=tekst),
        "format": "json",
        "stream": False,
    })
    return json.loads(r.json()["response"])
```

---

# Bestandsnaam-conventie: `YYMMDD-betaalmethode-etablissement.ext`

`ocr_bon.py` hernoemt een bon naar de **datum zoals op de bon** + betaalmethode +
etablissement:

```text
WhatsApp Image 2026-06-21 at 21.41.30.jpeg
        ↓ ocr_bon.py --rename
260621-pin-groszekdelicatessen.jpeg
```

* `YYMMDD` komt uit de OCR-datum op de bon (niet de bestandsdatum/EXIF)
* `betaalmethode` ∈ pin / contant / ideal / creditcard / applepay / googlepay / onbekend
* etablissement = bovenste, overwegend alfabetische regel (geslugd, lowercase)
* sorteert chronologisch in de map en is direct herkenbaar
* deze naam gebruik je daarna in de `!`-link in `nb.txt`

---

# Omzetten naar een `nb.txt`-entry

DeCli leest `nb.txt`. Format (zie [`README.md`](README.md)):

* `[<nr>. <naam>]` — categorie-header voor alle regels eronder
* `<omschrijving>; <opmerking> EUR <bedrag>` — transactie
* `!pad/naar/bon.jpg` — koppelt de afbeelding aan de **voorgaande** transactie

Voorbeeld-generator:

```python
def naar_nb_entry(velden: dict, bon_pad: str) -> str:
    return (
        f"{velden['merchant']}; bon EUR {velden['totaal']}\n"
        f"!{bon_pad}"
    )
```

Resultaat in `nb.txt`:

```text
[2. reiskosten]
Albert Heijn; bon EUR 12,45
!bonnetjes/reiskosten/bon.jpg
```

DeCli zipt `bon.jpg` mee onder `bonnetjes/` en zet een klikbare link in de PDF.

---

# Volledige pijplijn (inbox-watcher)

```python
import os, shutil

INBOX   = "receipts/inbox"
ARCHIEF = "bonnetjes"

def verwerk_inbox():
    for naam in os.listdir(INBOX):
        if not naam.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        pad = os.path.join(INBOX, naam)
        tekst = ocr_to_text(pad)
        velden = extract_llm(tekst)          # of parse_velden(tekst)
        cat = velden.get("categorie") or "overig"
        doel_dir = os.path.join(ARCHIEF, cat)
        os.makedirs(doel_dir, exist_ok=True)
        shutil.move(pad, os.path.join(doel_dir, naam))
        with open("nb.txt", "a", encoding="utf-8") as f:
            f.write("\n" + naar_nb_entry(velden, f"{doel_dir}/{naam}") + "\n")
```

Draai dit periodiek (cron / systemd-timer / Taakplanner) op de Syncthing-doelmap.

---

# Problemen oplossen

## `NotImplementedError: ConvertPirAttribute2RuntimeAttribute` (oneDNN)

Crash tijdens inference op CPU met paddlepaddle 3.x + PIR-modellen. Zet MKLDNN uit:

```python
ocr = PaddleOCR(lang="en", enable_mkldnn=False)
```

`ocr_bon.py` doet dit al automatisch.

## `ValueError: No models are available for lang='latin'`

De PP-OCRv5/v6-modellen (paddleocr 3.x) kennen geen `latin`-taalcode. Gebruik
`lang="en"` (dekt NL/Latijns schrift).

## `paddlepaddle` installeert niet / geen wheel

Vrijwel altijd een te nieuwe Python (3.13/3.14). Maak een venv op 3.12:

```powershell
uv venv --python 3.12 .venv
```

## `ModuleNotFoundError: paddle`

`paddlepaddle` is niet (correct) geïnstalleerd:

```bash
uv pip install --python .venv\Scripts\python.exe --reinstall paddlepaddle
```

## Linux: `libGL.so.1: cannot open shared object file`

```bash
sudo apt install libgl1 libglib2.0-0
```

## Eerste run hangt / traag

PaddleOCR downloadt modellen bij de eerste run. Eenmalig; daarna gecachet in
`~/.paddleocr/`.

## Slechte herkenning

* Gebruik `use_angle_cls=True` voor scheve foto's
* Fotografeer recht van boven, met contrast
* Kies het juiste taalmodel (`lang="latin"` voor NL)
* Schaal kleine bonnen op naar min. ~1000 px breed vóór OCR

## Bedragen verkeerd (`.` vs `,`)

Nederlandse bonnen gebruiken `12,45`. Normaliseer altijd naar komma vóór je
naar `nb.txt` schrijft (zie `parse_velden`).

---

# Aanbevolen hardware

| Niveau | Hardware | Geschikt voor |
|--------|----------|---------------|
| Klein | Raspberry Pi 5 | PaddleOCR CPU, lage volumes (LLM-stap traag) |
| Gemiddeld | Intel NUC / Mini-PC | PaddleOCR + Ollama (Qwen 7B) |
| Zwaar | Server met GPU | Grote batches, snelle LLM-extractie |

---

# Conclusie

```text
bon.jpg → PaddleOCR → tekst → (regex of Qwen) → velden → nb.txt → DeCli → declaratie-PDF
```

Voordelen:

* Gratis & open source
* Volledig lokaal en privacyvriendelijk
* Robuuster dan Tesseract op fotobonnen
* Sluit naadloos aan op de DeCli `nb.txt`-workflow
