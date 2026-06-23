# Syncthing 101

Een praktische handleiding voor het synchroniseren van bestanden tussen Windows, Linux, Android en iPhone.

> **Doel binnen DeCli:** bonnetjes die je op je telefoon fotografeert automatisch naar een `receipts/inbox` op je PC of server laten verschijnen, klaar voor OCR-verwerking. Geen cloud, geen account, geen kosten.

---

## Snelstart (TL;DR)

Voor wie meteen aan de slag wil — de vier stappen, details staan verderop:

1. **Installeren** op beide apparaten (PC + telefoon) — zie [Installatie](#installatie).
2. **Koppelen** via Device ID of QR-code — zie [Apparaten koppelen](#apparaten-koppelen).
3. **Map delen** (`Pictures/Receipts` → `receipts/inbox`) — zie [Een map delen](#een-map-delen).
4. **Testen** met een `test.txt` — zie [Synchronisatie testen](#synchronisatie-testen).

```text
Telefoon (foto) → Syncthing → PC/Server: receipts/inbox → OCR → DeCli
```

---

## Inhoud

1. [Wat is Syncthing?](#wat-is-syncthing)
2. [Hoe werkt Syncthing?](#hoe-werkt-syncthing)
3. [Installatie](#installatie) — [Windows](#windows) · [Linux](#linux) · [Android](#android) · [iPhone (iOS)](#iphone-ios)
4. [Device ID vinden](#device-id-vinden)
5. [Apparaten koppelen](#apparaten-koppelen)
6. [Een map delen](#een-map-delen)
7. [Synchronisatie testen](#synchronisatie-testen)
8. [Folder Types](#folder-types)
9. [Aanbevolen structuur voor DeCli](#aanbevolen-structuur-voor-decli)
10. [Workflow voor automatische bonverwerking](#workflow-voor-automatische-bonverwerking)
11. [Problemen oplossen](#problemen-oplossen)
12. [Aanbevolen hardware](#aanbevolen-hardware)
13. [Conclusie](#conclusie)

---

# Wat is Syncthing?

Syncthing is een gratis en open-source programma waarmee bestanden rechtstreeks tussen apparaten worden gesynchroniseerd.

Voordelen:

* Gratis
* Open source
* End-to-end versleuteld
* Geen cloudprovider nodig
* Geen account nodig
* Werkt op Windows, Linux, Android en iPhone (via Mobius Sync)

Voorbeeld:

```text
Telefoon
    ↓
Syncthing
    ↓
Laptop
```

Of:

```text
Android / iPhone
        ↓
Syncthing
        ↓
Linux Server
```

---

# Hoe werkt Syncthing?

Syncthing gebruikt een peer-to-peer model.

```text
Device A
    ↔
Device B
```

Bestanden worden direct tussen apparaten uitgewisseld.

Er is geen centrale cloudserver nodig.

---

# Installatie

## Windows

### Installeren via Winget (aanbevolen)

Open PowerShell:

```powershell
winget install Syncthing.Syncthing
```

Controleer de installatie:

```powershell
winget list Syncthing
```

### Syncthing starten

```powershell
syncthing
```

Of:

```text
Start
→ Syncthing
```

Open vervolgens:

```text
http://127.0.0.1:8384
```

Bij de eerste start worden automatisch:

* Encryptiesleutels aangemaakt
* Een configuratiebestand gegenereerd
* Een Device ID aangemaakt

### Updaten

```powershell
winget upgrade Syncthing.Syncthing
```

### Verwijderen

```powershell
winget uninstall Syncthing.Syncthing
```

### Handmatige installatie

Wanneer Winget niet beschikbaar is:

1. Download Syncthing via https://syncthing.net
2. Pak het ZIP-bestand uit
3. Start:

```text
syncthing.exe
```

4. Open:

```text
http://127.0.0.1:8384
```

---

## Linux

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install syncthing
```

Start:

```bash
syncthing
```

Open:

```text
http://127.0.0.1:8384
```

### Fedora

```bash
sudo dnf install syncthing
```

### Arch Linux

```bash
sudo pacman -S syncthing
```

### Automatisch starten

```bash
systemctl --user enable syncthing
systemctl --user start syncthing
```

Controle:

```bash
systemctl --user status syncthing
```

---

## Android

Installeer:

* Syncthing-Fork via Google Play
* Of Syncthing-Fork via F-Droid

Na installatie:

1. Open de app.
2. Geef bestandstoegang.
3. Schakel batterij-optimalisatie uit.
4. Wacht tot een Device ID verschijnt.

Android ondersteunt continue synchronisatie op de achtergrond.

---

## iPhone (iOS)

### Belangrijke beperking

Apple staat geen volledige achtergrondservices toe zoals Android.

Daarom bestaat er geen officiële Syncthing-app voor iOS.

Gebruik:

```text
Mobius Sync
```

uit de App Store.

### Installatie

1. Installeer Mobius Sync.
2. Open de app.
3. Sta bestandstoegang toe.
4. Maak een synchronisatiemap aan.
5. Noteer het Device ID.

---

# Device ID vinden

Open de Syncthing-webinterface:

```text
http://127.0.0.1:8384
```

Klik:

```text
Actions
→ Show ID
```

Voorbeeld:

```text
ABCDEF1-GHIJKL2-MNOPQR3-STUVWX4
```

Dit Device ID gebruik je om apparaten te koppelen.

---

# Apparaten koppelen

## Stap 1

Op apparaat A:

```text
Add Device
```

Voer het Device ID van apparaat B in.

Of scan de QR-code.

---

## Stap 2

Op apparaat B verschijnt:

```text
New Device Found
```

Klik:

```text
Add Device
```

---

## Stap 3

Controleer dat beide apparaten zichtbaar zijn als:

```text
Connected
```

---

# Een map delen

## Android

Maak:

```text
Pictures/Receipts
```

Voeg toe:

```text
Folders
→ +
```

Instellingen:

```text
Folder Label: Receipts
Folder Path: Pictures/Receipts
```

Selecteer de apparaten waarmee je wilt delen.

---

## iPhone

Maak binnen Mobius Sync:

```text
Receipts
```

of:

```text
Documents/Receipts
```

Deel deze map met andere apparaten.

---

## Windows

Wanneer een gedeelde map wordt aangeboden:

```text
New Folder Offered
```

Klik:

```text
Accept
```

Kies bijvoorbeeld:

```text
C:\Receipts\Inbox
```

of:

```text
D:\Receipts\Inbox
```

---

## Linux

Kies bijvoorbeeld:

```text
/opt/receipts/inbox
```

of:

```text
/home/user/receipts/inbox
```

---

# Synchronisatie testen

Maak een testbestand:

```text
test.txt
```

Plaats dit in de gedeelde map.

Controleer of het bestand verschijnt op de andere apparaten.

---

# Folder Types

## Send & Receive

Standaardinstelling.

```text
A ↔ B
```

Wijzigingen worden beide kanten op gesynchroniseerd.

---

## Send Only

```text
A → B
```

Handig voor backups.

---

## Receive Only

```text
A ← B
```

Handig voor servers.

---

# Aanbevolen structuur voor DeCli

## Android

```text
Pictures/
└── Receipts/
```

---

## iPhone

```text
Mobius Sync/
└── Receipts/
```

---

## Windows

```text
C:\DeCli\
└── receipts\
    ├── inbox
    ├── processing
    ├── archive
    └── failed
```

---

## Linux

```text
/opt/decli/receipts
├── inbox
├── processing
├── archive
└── failed
```

---

# Workflow voor automatische bonverwerking

```text
Android / iPhone
        ↓
Receipts Folder
        ↓
Syncthing
        ↓
Linux Server of Windows PC
        ↓
receipts/inbox
        ↓
Watcher Service
        ↓
PaddleOCR
        ↓
OCR Text
        ↓
Qwen via Ollama
        ↓
Structured JSON
        ↓
DeCli Transaction
```

---

# Problemen oplossen

## Apparaten zien elkaar niet

Controleer:

* Internetverbinding
* Firewall
* Correct Device ID
* Beide apparaten actief

---

## Android synchroniseert niet

Controleer:

```text
Battery Optimization
```

Schakel optimalisatie uit voor:

```text
Syncthing-Fork
```

---

## iPhone synchroniseert niet

Controleer:

* Mobius Sync geopend
* Achtergrondverversing toegestaan
* Bestandstoegang toegestaan

Houd rekening met iOS-beperkingen.

---

## Bestand verschijnt niet

Controleer:

* Gedeelde map correct ingesteld
* Synchronisatie voltooid
* Bestandsrechten correct

---

# Aanbevolen hardware

## Klein

```text
Raspberry Pi 5
```

Geschikt voor:

* Syncthing
* DeCli
* Basis OCR

---

## Gemiddeld

```text
Intel NUC
Mini PC
```

Geschikt voor:

* Syncthing
* PaddleOCR
* Ollama
* DeCli

---

## Zwaarder gebruik

```text
Linux Server
```

Geschikt voor:

* Grote aantallen documenten
* OCR-verwerking
* LLM-extractie
* Meerdere gebruikers

---

# Conclusie

Voor een volledig lokale bonnetjesworkflow:

```text
Android / iPhone
        ↓
Receipts Folder
        ↓
Syncthing
        ↓
Linux Server
        ↓
PaddleOCR
        ↓
Qwen via Ollama
        ↓
DeCli
```

Voordelen:

* Gratis
* Open source
* Privacyvriendelijk
* Geen cloudkosten
* Volledig self-hosted
* Geschikt voor automatische verwerking van bonnetjes en facturen

