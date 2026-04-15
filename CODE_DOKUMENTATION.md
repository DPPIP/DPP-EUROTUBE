# Code-Dokumentation – DPP Hyperloop (Eurotube / FHNW)

## Übersicht

Das System erstellt **Digitale Produktpässe (DPP)** für Beton-Fertigelemente eines Hyperloop-Prototyps. Es besteht aus vier Schichten:

```
┌─────────────────────────────────────────────────────────┐
│  Arduino (Sensoren + RFID + Servo)                      │
│  ↕ Seriell (USB, 9600 Baud, JSON)                       │
│  Python GUI (Tkinter) – Produktionssteuerung             │
│  ↕ Git Push / GitHub Pages                               │
│  Web-Viewer (viewer.html, batch/index.html)              │
│  ↕ ifcopenshell                                          │
│  IFC-Integration (Pset-Schreiber)                        │
└─────────────────────────────────────────────────────────┘
```

---

## Verzeichnisstruktur

```
DPP-EUROTUBE/
├── prototyp_final/
│   ├── hyperloop_dpp.py              ← Haupt-Python-Skript (GUI + Logik)
│   ├── hyperloop_dpp_combined/
│   │   └── hyperloop_dpp_combined.ino ← Arduino-Sketch
│   ├── hyperloop_qr_prep.py          ← QR-Label-Generator (PDF)
│   └── qr_labels/
│       ├── labels.pdf                 ← Druckbare Etiketten
│       └── prepared.json              ← Manifest der generierten SNs
├── passports/
│   ├── viewer.html                    ← Einzel-DPP Viewer (Web)
│   └── *.jsonld                       ← Generierte Segment-Passports
├── batch/
│   ├── index.html                     ← Batch-Viewer + Scanner (Web)
│   └── *.jsonld                       ← Generierte Batch-Passports
├── IFC/
│   ├── IP3.ifc                        ← Quell-IFC-Modell
│   ├── add_dpp_links.py               ← V1: Nur URLs ins IFC
│   ├── add_dpp_data.py                ← V2: Alle DPP-Daten ins IFC
│   ├── IP3_DPP_v1.ifc                ← Output V1
│   └── IP3_DPP_v2.ifc                ← Output V2
└── .gitignore
```

---

## 1. Arduino – `hyperloop_dpp_combined.ino`

### Zweck
Steuert die physische Hardware: DHT11-Sensor (Temperatur/Feuchtigkeit), Servo (Schalung öffnen/schliessen), MFRC522 (RFID/NFC-Leser).

### Pin-Belegung

| Komponente | Pin |
|---|---|
| DHT11 | 2 |
| Taster | 3 (INPUT_PULLUP) |
| Servo | 6 |
| RFID RST | 9 |
| RFID SS | 10 |
| SPI | 11, 12, 13 (Standard) |

### Serielles Protokoll (JSON, 9600 Baud)

**Eingabe (Python → Arduino):**
- `C` – Schalung schliessen, Messung starten
- `O` – Schalung öffnen, Messung stoppen

**Ausgabe (Arduino → Python):**
```json
{"type":"boot","msg":"System bereit (DHT+Servo+RFID)"}
{"type":"event","event":"cmd_start"}
{"type":"sensor","grund":"periodic","temp":22.5,"hum":58.0,"servo":5}
{"type":"event","event":"cmd_stopp"}
{"type":"rfid","url":"https://w3id.org/hyperloop-dpp/01/09999000000001/21/1234567890"}
{"type":"rfid_error","msg":"Auth fehlgeschlagen"}
```

### RFID-Lesevorgang
- Liest NDEF-URL-Records von MIFARE Classic 1K Karten
- Sektor 1 (Blöcke 4–6) + Sektor 2 (Blöcke 8–10) = 96 Bytes
- Authentifizierung mit NFC-Forum-Key: `D3 F7 D3 F7 D3 F7`
- NDEF-Prefix `0x04` = `https://`, Terminator `0xFE` = Ende
- Nach erfolgreichem Scan wird `rfidAktiv = false` gesetzt (einmaliger Scan pro Zyklus)

### Ablauf
1. Taster oder `C`-Befehl → Schalung schliesst, Sensoraufzeichnung startet
2. Alle 2 Sekunden wird `{"type":"sensor",...}` gesendet
3. Taster oder `O`-Befehl → Schalung öffnet, RFID-Scan wird aktiviert
4. RFID-Karte erkannt → URL wird gesendet, Scan deaktiviert

---

## 2. Python GUI – `hyperloop_dpp.py`

### Zweck
Desktop-Anwendung (Tkinter) zur Produktionssteuerung. Empfängt Sensordaten vom Arduino, erstellt JSON-LD Passports und pusht sie via Git auf GitHub Pages.

### Abhängigkeiten
```
pip install pyserial qrcode[pil]
```
Optional (für Kamera-QR-Scan): `pip install opencv-python pyzbar`

### Konfiguration (Konstanten im Skript)

| Konstante | Wert | Beschreibung |
|---|---|---|
| `PORT` | `COM7` | Serieller Port des Arduino |
| `BAUD` | `9600` | Baudrate |
| `W3ID_BASE` | `https://w3id.org/hyperloop-dpp` | Basis-URI für GS1 Digital Links |
| `GTIN` | `09999000000001` | GS1 GTIN-14 des Produkts |
| `GITHUB_PAGES` | `https://DPPIP.github.io/DPP-EUROTUBE` | GitHub Pages URL |
| `GITHUB_REPO` | `C:/Users/david/Documents/DPP-EUROTUBE` | Lokaler Pfad zum Git-Repo |
| `BSDD_BASE` | `.../HYPER-DPP/0.6` | bSDD Datenkatalog Version |
| `BETONSORTE` | `C25/30` | Standardwert (überschreibbar in GUI) |
| `HERSTELLUNGSORT` | `Koblenz` | Standardwert (überschreibbar in GUI) |

### Hauptfunktionen

#### `extrahiere_id(scanned: str) -> str`
Extrahiert die Seriennummer aus einem GS1 Digital Link URI:
- `https://w3id.org/.../21/1234567890` → `1234567890`
- `https://w3id.org/.../10/4521` → `4521`
- `1234567890` → `1234567890`

#### `erstelle_jsonld(eintrag: dict) -> dict`
Generiert das JSON-LD Dokument für ein Segment. Verwendet bSDD 0.6 Property-Namen:

| JSON-LD Key | Inhalt |
|---|---|
| `bsdd:SegmentID` | Seriennummer |
| `bsdd:StrengthClass` | Betonsorte (aus GUI-Eingabe) |
| `bsdd:AssemblyPlace` | Herstellungsort (aus GUI-Eingabe) |
| `bsdd:ManufactoringDate` | ISO-Zeitstempel |
| `bsdd:ReferenceEnvironmentTemperature` | Durchschnittstemperatur in °C |
| `bsdd:ReferenceAirRelativeHumidity` | Durchschnittliche Luftfeuchtigkeit in % |
| `bsdd:Schalungsdauer` | Dauer in Stunden (Minuten / 60) |
| `bsdd:Status` | `Aktiv` |

#### `github_push(serial_nr: str, dateien: list)`
1. `git pull --rebase --autostash` (verhindert Konflikte)
2. Dateien ins Repo kopieren
3. `git add`, `git commit`, `git push`

#### `speichere_und_publiziere(t_med, h_med, dauer, segment_id)`
Erstellt JSON-LD, speichert lokal unter `passports/{sn}.jsonld`, pusht via Git.

#### `zeige_scan_dialog(t_med, h_med, dauer)`
Nach Produktionsstopp öffnet sich ein Dialog mit:
- **Kamera-Preview** (OpenCV + pyzbar) – erkennt QR-Codes automatisch
- **RFID-Callback** – Arduino sendet URL, Dialog reagiert automatisch
- **Manuelles Eingabefeld** – Fallback für USB-Scanner
- **Duplikatprüfung** – HEAD-Request auf GitHub Pages, verhindert doppelte Vergabe

#### `lese_seriell()`
Polling-Funktion (alle 100 ms via `root.after`). Verarbeitet JSON-Nachrichten vom Arduino:
- `cmd_start`/`system_start` → Aufzeichnung starten, Sensor-Arrays leeren
- `sensor` → Temperatur/Feuchtigkeit sammeln
- `rfid` → ID extrahieren, an Scan-Dialog weiterleiten
- `cmd_stopp`/`system_stopp` → Median berechnen, Scan-Dialog öffnen

### GUI-Elemente
- **Statusanzeige**: Schalung offen/geschlossen, aktueller Zustand
- **Eingabefelder**: Betonsorte und Herstellungsort (editierbar, Standardwerte)
- **Buttons**: "Schliessen & Start" / "Öffnen & Stopp"
- **DPP-Liste**: Scrollbare Liste aller erstellten Passports (Doppelklick öffnet im Browser)
- **URI-Label**: Klickbar, öffnet den zuletzt erstellten DPP im Browser

---

## 3. QR-Label-Generator – `hyperloop_qr_prep.py`

### Zweck
Generiert druckbare QR-Code-Etiketten als A4-PDF. Jedes Label enthält eine eindeutige GS1 Digital Link URI.

### Abhängigkeiten
```
pip install qrcode[pil] reportlab
```

### Konfiguration

| Konstante | Wert |
|---|---|
| `COUNT` | 11 (eindeutige SNs) |
| `COLS × ROWS` | 3 × 8 = 24 Plätze |
| Labels total | 13 (11 einmalig + 2 Duplikate) |

### Output
- `qr_labels/labels.pdf` – A4, randlos, QR 90° gedreht
- `qr_labels/prepared.json` – Manifest `[{id, uri, used}, ...]`

### Label-Aufbau
```
┌──────────────────────────────────┐
│ [QR 90°]  Digital Product Passport│
│           https://w3id.org/.../   │
│           01/GTIN/21/             │
│           1234567890  (fett)      │
└──────────────────────────────────┘
```

### Seriennummern
10-stellig, zufällig generiert (`random.randint(1000000000, 9999999999)`). Die ersten zwei SNs werden doppelt gedruckt (für Duplikat-Tests).

---

## 4. Web-Viewer – `passports/viewer.html`

### Zweck
Rendert ein einzelnes Segment-DPP im Browser. Wird auf GitHub Pages gehostet, Daten werden per Fetch aus den `.jsonld`-Dateien geladen.

### URL-Parameter
- `?sn=1234567890` – Seriennummer des Segments (Pflicht)
- `?single=1` – Batch-Redirect unterdrücken

### Ablauf
1. `sn` aus URL lesen
2. Fetch `passports/{sn}.jsonld` von GitHub Pages
3. Wenn `@type` = `HyperloopBatch` → Redirect zu `batch/index.html`
4. Wenn `bsdd:BatchID` vorhanden und kein `?single=1` → Redirect zum Batch
5. Render: 7 Felder (Betonsorte, Herstellungsort, Datum, Temperatur, Schalungsdauer, Status, Luftfeuchtigkeit)
6. QR-Code generieren (qrcodejs)

### Angezeigte Felder
| Feld | JSON-LD Key |
|---|---|
| Betonsorte | `bsdd:StrengthClass` |
| Herstellungsort | `bsdd:AssemblyPlace` |
| Herstellungsdatum | `bsdd:ManufactoringDate.@value` |
| Herstellungstemperatur | `bsdd:ReferenceEnvironmentTemperature.@value` |
| Dauer in der Schalung | `bsdd:Schalungsdauer.@value` |
| Status | `bsdd:Status` |
| Luftfeuchtigkeit | `bsdd:ReferenceAirRelativeHumidity.@value` |

---

## 5. Batch-Viewer – `batch/index.html`

### Zweck
Zwei Modi in einer Datei:
1. **Scanner-Modus** (`index.html` ohne Parameter): QR-Scanner zum Erstellen neuer Batches
2. **Batch-Ansicht** (`?batch=ID`): Anzeige eines bestehenden Batches

### Scanner-Modus
- Kamera-basierter QR-Scanner (html5-qrcode)
- 5 Segmente scannen → "Batch erstellen"
- Erstellt `batch/{batchId}.jsonld` via GitHub API (Token im localStorage)
- Schreibt `bsdd:BatchID` in jedes Segment-JSONLD zurück
- Duplikatschutz: Segment mit existierender BatchID wird abgelehnt

### Batch-Ansicht
- Titel: "Batch Röhrensegment 10 M"
- Batch-Karte: Batch-ID, Verbindungsdatum
- Bestandteile: Pro Segment → Bauteiltyp, Betonsorte, Herstellungsort, Temperatur, Schalungsdauer
- Status-Karte: Verbunden/offen, Einbaudatum
- Buttons: Link kopieren, JSON-LD anzeigen

### Batch JSON-LD Struktur
```json
{
  "@type": ["dpp:DigitalProductPassport", ".../HyperloopBatch"],
  "bsdd:Batch_ID": "4873316459",
  "bsdd:Verbindungsdatum": {"@value": "2026-04-15T10:35:24"},
  "bsdd:VerlinkungBauteile": ["https://w3id.org/.../21/SN1", "..."],
  "bsdd:Status": "Verbunden",
  "bsdd:Material": "SikaProof",
  "bsdd:Spannstahlsorte": "St1570",
  "bsdd:Klebertyp": "PCI"
}
```

---

## 6. IFC-Integration – `add_dpp_links.py` / `add_dpp_data.py`

### Zweck
Schreibt DPP-Informationen in ein bestehendes IFC-Modell (IP3.ifc) via ifcopenshell.

### Abhängigkeiten
```
pip install ifcopenshell
```

### IFC-Struktur

```
IfcElementAssembly  "Batch"       (Röhrensegment 10m = 5 Betonelemente)
  ├── IfcBuildingElementProxy  "Betonsegment_2m10"
  ├── IfcBuildingElementProxy  "Betonsegment_2m11"
  ├── IfcBuildingElementProxy  "Betonsegment_2m12"
  ├── IfcBuildingElementProxy  "Betonsegment_2m13"
  ├── IfcBuildingElementProxy  "Betonsegment_2m14"
  ├── IfcCovering              "Beschichtung"
  ├── IfcReinforcingBar        "Spannstahl" (×5)
  └── IfcFastener              "Kleber" (×4)
```

### Variante 1 – `add_dpp_links.py` → `IP3_DPP_v1.ifc`
Schreibt nur DPP-URLs in ein einziges Pset:

| Element | Pset | Property | Wert |
|---|---|---|---|
| IfcElementAssembly | `ePset_DigitalProductPassport` | `URL` | Batch-Viewer-Link |
| IfcBuildingElementProxy | `ePset_DigitalProductPassport` | `URL` | GS1 Digital Link URI |

### Variante 2 – `add_dpp_data.py` → `IP3_DPP_v2.ifc`
Schreibt alle DPP-Daten gemäss IFC-Mapping in mehrere Psets:

**IfcElementAssembly (Batch):**

| Pset | Properties |
|---|---|
| `ePset_DigitalProductPassport` | URL, Batch_ID, Verbindungsdatum, Status, Einbaudatum |

**IfcBuildingElementProxy (Segment):**

| Pset | Properties |
|---|---|
| `ePset_DigitalProductPassport` | URL |
| `Pset_ConcreteElementGeneral` | StrengthClass |
| `Pset_ManufacturerTypeInformation` | AssemblyPlace |
| `Pset_ManufacturerOccurrence` | ManufactoringDate |
| `Pset_EnvironmentalCondition` | ReferenceEnvironmentTemperature, ReferenceAtRelativeHumidity |
| `Pset_Herstellung` | Schalungsdauer, Status |

---

## URI-Schema (GS1 Digital Link)

```
https://w3id.org/hyperloop-dpp/01/{GTIN}/21/{Serial}   → Segment
https://w3id.org/hyperloop-dpp/01/{GTIN}/10/{BatchID}   → Batch
```

- **AI 01** = GTIN-14 (`09999000000001`)
- **AI 21** = Seriennummer (SGTIN, Segment-Ebene)
- **AI 10** = Losnummer (LGTIN, Batch-Ebene)
- W3ID leitet via `.htaccess` auf GitHub Pages weiter (PR pending bei perma-id/w3id.org)

---

## Datenfluss

```
1. Schalung schliessen (Button/Taster)
   → Arduino: Servo schliesst, Sensormessung startet

2. Sensordaten sammeln (alle 2s)
   → Arduino sendet JSON → Python sammelt Temperatur + Feuchtigkeit

3. Schalung öffnen (Button/Taster)
   → Arduino: Servo öffnet, RFID-Scan aktiviert
   → Python: Median berechnen, Scan-Dialog öffnen

4. QR-Code / RFID scannen
   → Kamera, RFID oder manuell → Segment-ID extrahiert
   → Duplikatprüfung (HEAD-Request auf GitHub Pages)

5. DPP erstellen und publizieren
   → JSON-LD generieren → lokal speichern
   → git pull --rebase → git add → git commit → git push
   → GitHub Pages aktualisiert automatisch

6. Batch erstellen (batch/index.html)
   → 5 Segmente scannen → Batch-JSONLD via GitHub API erstellen
   → BatchID in jedes Segment-JSONLD zurückschreiben

7. IFC-Integration (optional)
   → add_dpp_links.py oder add_dpp_data.py
   → Schreibt URLs / Daten in IFC-Psets
```

---

## Bekannte Limitierungen

- **Fehlerbehandlung**: `except Exception: pass` in der seriellen Leseroutine schluckt Fehler still. Bei Produktionseinsatz sollte Logging ergänzt werden.
- **Blockierender HTTP-Call**: Die Duplikatprüfung (`urllib.request.urlopen`) blockiert kurzzeitig die GUI. Bei schlechtem Netzwerk kann dies zu Verzögerungen führen.
- **Git-Push**: Verwendet `subprocess` für Git-Befehle. Bei Merge-Konflikten kann der Push fehlschlagen (wird in Konsole ausgegeben).
- **Kamera-Freigabe**: Bei unerwartetem Schliessen des Scan-Dialogs kann die Kamera-Ressource blockiert bleiben.
- **Prototyp-Charakter**: Das Skript ist für den Laborbetrieb an der FHNW konzipiert, nicht für industriellen Einsatz.
