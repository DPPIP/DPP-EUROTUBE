"""
Hyperloop DPP – Digital Product Passport System
================================================
Vollständiges System: Serieller Logger → JSON-LD → HTML → GitHub Push

Abhängigkeiten installieren:
    pip install pyserial qrcode[pil] gitpython

Konfiguration: Abschnitt CONFIG unten anpassen.
"""

import serial
import json
import time
import os
import glob
import datetime
import base64
import subprocess
import threading
import urllib.request
import tkinter as tk
import webbrowser
from io import BytesIO

# ─── CONFIG ──────────────────────────────────────────────────────────────────

PORT        = "COM7"            # Serieller Port (Windows: COM7, Linux: /dev/ttyUSB0)
BAUD        = 9600

# GS1-Struktur (Prototyp: Präfix 9999 = reserviert für Tests)
GTIN        = "9999000000001"   # 13-stellige Test-GTIN eures Produkts
W3ID_BASE      = "https://w3id.org/hyperloop-dpp"          # PR #5843 gemergt 19.03.2026
GITHUB_PAGES   = "https://DPPIP.github.io/DPP-EUROTUBE"   # Fallback wenn w3id nicht erreichbar
GITHUB_REPO    = "C:/Users/david/Documents/DPP-EUROTUBE"  # ← lokaler Git-Pfad

# Unterordner für Passport-Dateien (HTML + JSON-LD)
PASSPORT_DIR = "passports"

# Hersteller-Metadaten (erscheinen im JSON-LD)
HERSTELLER  = "Eurotube – FHNW"
PRODUKT     = "Beton-Fertigelement Typ A"
LAND        = "CH"
MATERIAL    = "Beton C40/50, Bewehrungsstahl B500B"

# bSDD Dictionary (buildingSMART Data Dictionary)
BSDD_BASE   = "https://identifier.buildingsmart.org/uri/demo2026/HYPER-DPP/0.1"

# ─────────────────────────────────────────────────────────────────────────────


def oeffne_dpp(uri: str):
    """Öffnet w3id.org URI – fällt auf GitHub Pages zurück wenn nicht erreichbar."""
    sn = uri.split("/")[-1]
    github_url = f"{GITHUB_PAGES}/{PASSPORT_DIR}/{sn}.html"
    def _open():
        try:
            urllib.request.urlopen(urllib.request.Request(uri, method="HEAD"), timeout=3)
            webbrowser.open(uri)
        except Exception:
            webbrowser.open(github_url)
    threading.Thread(target=_open, daemon=True).start()


def gs1_uri(gtin: str, batch: str, serial_nr: str) -> str:
    """Erzeugt eine W3ID URI für den DPP."""
    return f"{W3ID_BASE}/{serial_nr}"


def serial_nummer(timestamp: int) -> str:
    """Eindeutige Seriennummer aus Unix-Timestamp."""
    return f"SN-{timestamp}"


def batch_nummer() -> str:
    """Batch-Nummer aus aktuellem Datum (ISO-Woche)."""
    now = datetime.datetime.now()
    return f"LOT-{now.year}-{now.isocalendar()[1]:02d}"


# ─── JSON-LD Generator ───────────────────────────────────────────────────────

def erstelle_jsonld(eintrag: dict) -> dict:
    """
    Erzeugt einen EU-DPP-konformen JSON-LD Eintrag.
    Basiert auf: GS1 Web Vocabulary + Schema.org + bSDD (HYPER-DPP/0.1).
    """
    uri = eintrag["uri"]
    return {
        "@context": {
            "@vocab": "https://schema.org/",
            "gs1":    "https://www.gs1.org/voc/",
            "xsd":    "http://www.w3.org/2001/XMLSchema#",
            "qudt":   "http://qudt.org/schema/qudt/",
            "bsdd":   f"{BSDD_BASE}/prop/"
        },
        "@type": ["Product", f"{BSDD_BASE}/class/HyperloopSegment"],
        "@id":   uri,

        # ── Identifikation ──────────────────────────────────────────────────
        "gs1:gtin":           eintrag["GTIN"],
        "gs1:batchLotNumber": eintrag["Batch"],
        "gs1:serialNumber":   eintrag["Serial"],
        "gs1:digitalLink":    uri,

        # ── Produkt ─────────────────────────────────────────────────────────
        "name":        PRODUKT,
        "description": "Beton-Fertigelement, hergestellt im Hyperloop-Schalungsprozess.",

        "manufacturer": {
            "@type":   "Organization",
            "name":    HERSTELLER,
            "address": {"@type": "PostalAddress", "addressCountry": LAND}
        },

        # ── bSDD Tabelle 1: Segment-Parameter ───────────────────────────────
        "bsdd:SegmentID":    eintrag["Serial"],

        "bsdd:Herstellungsdatum": {
            "@value": eintrag["Datum"],
            "@type":  "xsd:dateTime"
        },

        "bsdd:DauerInSchalung": {
            "@value":    str(eintrag["Dauer"]),
            "@type":     "xsd:decimal",
            "qudt:unit": "qudt:MIN"
        },

        "bsdd:AussentemperaturSchalung": {
            "@value":    str(eintrag["Temperatur"]),
            "@type":     "xsd:decimal",
            "qudt:unit": "qudt:DEG_C"
        },

        "bsdd:Materialzusammensetzung": MATERIAL,

        "bsdd:SegmentStatus": "Produced",

        # ── bSDD Tabelle 2: Batch-Parameter (initial leer, update bei Montage)
        "bsdd:BatchID":            eintrag["Batch"],
        "bsdd:Verbindungsdatum":   None,
        "bsdd:VerlinkungBauteile": [],
        "bsdd:BatchStatus":        None,
        "bsdd:Einbaudatum":        None,

    }


# ─── HTML Generator ──────────────────────────────────────────────────────────

def erstelle_html(eintrag: dict, jsonld: dict, qr_b64: str) -> str:
    """Erzeugt eine human-readable DPP-Seite mit eingebettetem QR-Code."""
    uri = eintrag["uri"]
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DPP – {eintrag['Serial']}</title>
<script type="application/ld+json">
{json.dumps(jsonld, ensure_ascii=False, indent=2)}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  :root{{
    --bg:#F4F1EC;--card:#FDFCFA;--ink:#1A1916;--muted:#7A7870;
    --accent:#2D5A3D;--accent-light:#EAF2ED;--border:#DDD9D1;
    --mono:'DM Mono',monospace;--sans:'DM Sans',sans-serif
  }}
  body{{background:var(--bg);font-family:var(--sans);color:var(--ink);min-height:100vh;padding:2rem 1rem}}
  .wrap{{max-width:520px;margin:0 auto}}
  .badge{{background:var(--accent);color:#fff;font-family:var(--mono);font-size:10px;
    font-weight:500;letter-spacing:.12em;padding:4px 10px;border-radius:4px;text-transform:uppercase;display:inline-block}}
  h1{{font-size:24px;font-weight:300;letter-spacing:-.02em;line-height:1.2;margin:.5rem 0 .25rem}}
  .sub{{font-size:12px;color:var(--muted);font-family:var(--mono);margin-bottom:1.5rem}}
  .card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.25rem;margin-bottom:1rem}}
  .card-label{{font-size:10px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;
    color:var(--muted);margin-bottom:1rem;font-family:var(--mono)}}
  .metrics{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}
  .metric label{{font-size:11px;color:var(--muted);display:block;margin-bottom:4px}}
  .metric .val{{font-size:30px;font-weight:300;letter-spacing:-.03em;line-height:1}}
  .metric .unit{{font-size:13px;color:var(--muted);margin-left:2px}}
  .metric.full{{grid-column:1/-1}}
  .row{{display:flex;align-items:center;gap:8px;padding:9px 0;
    border-bottom:1px solid var(--border);font-size:13px}}
  .row:last-child{{border-bottom:none}}
  .dot{{width:7px;height:7px;border-radius:50%;background:var(--accent);flex-shrink:0}}
  .key{{color:var(--muted);flex:1}}
  .val-mono{{font-family:var(--mono);font-size:12px}}
  .qr-wrap{{text-align:center;padding:.5rem 0}}
  .qr-wrap img{{width:148px;height:148px;border-radius:8px;
    border:1px solid var(--border);padding:6px;background:#fff}}
  .uri{{font-size:10px;color:var(--muted);font-family:var(--mono);
    margin-top:8px;word-break:break-all;line-height:1.5}}
  .footer{{text-align:center;font-size:11px;color:var(--muted);
    margin-top:2rem;font-family:var(--mono)}}

</style>
</head>
<body>
<div class="wrap">
  <span class="badge">Digital Product Passport</span>
  <h1>{PRODUKT}</h1>
  <p class="sub">{eintrag['Datum']} &nbsp;·&nbsp; {eintrag['Serial']}</p>

  <div class="card">
    <p class="card-label">Produktionsdaten</p>
    <div class="metrics">
      <div class="metric">
        <label>Temperatur (&#x2300;)</label>
        <span class="val">{eintrag['Temperatur']}<span class="unit">°C</span></span>
      </div>
      <div class="metric">
        <label>Feuchtigkeit (&#x2300;)</label>
        <span class="val">{eintrag['Feuchtigkeit']}<span class="unit">%</span></span>
      </div>
      <div class="metric full">
        <label>Aushärte-Dauer</label>
        <span class="val">{eintrag['Dauer']}<span class="unit">s</span></span>
      </div>
    </div>
  </div>

  <div class="card">
    <p class="card-label">Identifikation</p>
    <div class="row"><span class="dot"></span><span class="key">GTIN</span>
      <span class="val-mono">{eintrag['GTIN']}</span></div>
    <div class="row"><span class="dot"></span><span class="key">Batch</span>
      <span class="val-mono">{eintrag['Batch']}</span></div>
    <div class="row"><span class="dot"></span><span class="key">Serial</span>
      <span class="val-mono">{eintrag['Serial']}</span></div>
    <div class="row"><span class="dot"></span><span class="key">Hersteller</span>
      <span class="val-mono">{HERSTELLER}</span></div>
    <div class="row"><span class="dot"></span><span class="key">Status</span>
      <span class="val-mono" style="color:var(--accent)">ARCHIVIERT</span></div>
  </div>

  <div class="card">
    <p class="card-label">QR-Code – dieser Passport</p>
    <div class="qr-wrap">
      <img src="data:image/png;base64,{qr_b64}" alt="GS1 Digital Link QR Code">
      <p class="uri">{uri}</p>
    </div>
  </div>

  <p class="footer">
    Erzeugt von Hyperloop Steuerung &nbsp;·&nbsp; {eintrag['Datum']}<br>
    JSON-LD: <a href="{eintrag['Serial']}.jsonld" style="color:var(--accent)">{eintrag['Serial']}.jsonld</a>
  </p>
</div>
</body>
</html>"""


# ─── QR Code ─────────────────────────────────────────────────────────────────

def erstelle_qr_b64(uri: str) -> str:
    """Erzeugt QR Code als Base64-String (für HTML-Einbettung)."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2
        )
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        print("  [!] qrcode nicht installiert: pip install qrcode[pil]")
        return ""


# ─── GitHub Push ─────────────────────────────────────────────────────────────

def github_push(serial_nr: str, dateien: list[str]):
    """
    Kopiert Dateien ins GitHub-Repo und pusht.
    Voraussetzung: GITHUB_REPO ist ein initialisiertes Git-Repo
    mit konfiguriertem remote 'origin'.
    """
    if not os.path.isdir(GITHUB_REPO):
        print(f"  [!] Git-Repo nicht gefunden: {GITHUB_REPO} – kein Push")
        return

    try:
        for pfad in dateien:
            # Unterordner-Struktur beibehalten (z.B. passports/SN-xxx.html)
            ziel = os.path.join(GITHUB_REPO, pfad)
            os.makedirs(os.path.dirname(ziel) or GITHUB_REPO, exist_ok=True)
            with open(pfad, "rb") as f:
                inhalt = f.read()
            with open(ziel, "wb") as f:
                f.write(inhalt)

        subprocess.run(["git", "-C", GITHUB_REPO, "add"] + [os.path.abspath(os.path.join(GITHUB_REPO, p)) for p in dateien], check=True)
        subprocess.run(["git", "-C", GITHUB_REPO, "commit", "-m",
                         f"DPP {serial_nr} hinzugefügt"],              check=True)
        subprocess.run(["git", "-C", GITHUB_REPO, "push"],             check=True)
        print(f"  [OK] GitHub Push erfolgreich: {serial_nr}")

    except subprocess.CalledProcessError as e:
        print(f"  [!] Git-Fehler: {e}")
    except Exception as e:
        print(f"  [!] Push-Fehler: {e}")


# ─── Speichern & Publizieren ─────────────────────────────────────────────────

def speichere_und_publiziere(t_med: float, h_med: float, dauer: float):
    """Erstellt alle DPP-Artefakte und pusht sie auf GitHub."""
    ts       = int(time.time())
    sn       = serial_nummer(ts)
    batch    = batch_nummer()
    datum    = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    uri      = gs1_uri(GTIN, batch, sn)

    eintrag = {
        "ID":           ts,
        "Datum":        datum,
        "Temperatur":   t_med,
        "Feuchtigkeit": h_med,
        "Dauer":        dauer,
        "GTIN":         GTIN,
        "Batch":        batch,
        "Serial":       sn,
        "uri":          uri
    }

    # 1) Passport-Ordner anlegen
    os.makedirs(PASSPORT_DIR, exist_ok=True)

    # 3) JSON-LD schreiben (in passports/)
    jsonld       = erstelle_jsonld(eintrag)
    jsonld_datei = os.path.join(PASSPORT_DIR, f"{sn}.jsonld")
    with open(jsonld_datei, "w", encoding="utf-8") as f:
        json.dump(jsonld, f, indent=2, ensure_ascii=False)

    # 4) QR Code zeigt auf GS1/W3ID-URI
    qr_url = f"{GITHUB_PAGES}/{PASSPORT_DIR}/{sn}.html"
    qr_b64 = erstelle_qr_b64(qr_url)

    # 5) HTML schreiben (in passports/)
    html_datei = os.path.join(PASSPORT_DIR, f"{sn}.html")
    with open(html_datei, "w", encoding="utf-8") as f:
        f.write(erstelle_html(eintrag, jsonld, qr_b64))

    print(f"  [OK] {sn} | {dauer}s | {t_med}°C | {h_med}%")
    print(f"  [OK] URI: {uri}")
    print(f"  [OK] Dateien: {PASSPORT_DIR}/{sn}.html + {sn}.jsonld")

    # 6) GitHub Push
    github_push(sn, [jsonld_datei, html_datei])

    return sn, uri


# ─── Serieller Logger ────────────────────────────────────────────────────────

try:
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[OK] Logger aktiv an {PORT}")
except Exception as e:
    print(f"[!] Serielle Verbindung fehlgeschlagen: {e}")
    exit(1)

zyklus: dict = {"start": None, "t": [], "h": []}


def sende_start():
    ser.write(b"C")
    ser.flush()
    print("[>>] Befehl: CLOSE + START")


def sende_stopp():
    ser.write(b"O")
    ser.flush()
    print("[>>] Befehl: OPEN + STOPP")


def lese_seriell():
    global zyklus

    while ser.in_waiting > 0:
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not (line.startswith("{") and line.endswith("}")):
                continue

            data     = json.loads(line)
            msg_type = data.get("type")
            event    = data.get("event")

            if event in ["system_start", "cmd_start"]:
                zyklus.update({"start": time.time(), "t": [], "h": []})
                status_label.config(text="Status: AUFZEICHNUNG LÄUFT", fg="#2D5A3D")
                servo_label.config(text="Schalung: GESCHLOSSEN",       fg="#c0392b")
                print("[●] Produktion gestartet")

            elif msg_type == "sensor" and zyklus["start"]:
                if "temp" in data: zyklus["t"].append(data["temp"])
                if "hum"  in data: zyklus["h"].append(data["hum"])

            elif event in ["system_stopp", "cmd_stopp"] and zyklus["start"]:
                t_med = round(sum(zyklus["t"]) / len(zyklus["t"]), 1) if zyklus["t"] else 0.0
                h_med = round(sum(zyklus["h"]) / len(zyklus["h"]), 1) if zyklus["h"] else 0.0
                dauer = round(time.time() - zyklus["start"], 1)
                zyklus["start"] = None

                status_label.config(text="Status: PUBLIZIERE…", fg="#e67e22")
                root.update()

                sn, uri = speichere_und_publiziere(t_med, h_med, dauer)

                status_label.config(
                    text=f"Status: FERTIG – {sn}", fg="gray")
                servo_label.config(text="Schalung: OFFEN", fg="#2980b9")
                uri_label.config(text=uri, fg="#2D5A3D")
                lade_liste()

        except Exception:
            pass

    root.after(100, lese_seriell)


# ─── GUI ─────────────────────────────────────────────────────────────────────

root = tk.Tk()
root.title("Hyperloop DPP Steuerung")
root.geometry("640x520")
root.configure(bg="#F4F1EC")

def lbl(text, font_size=10, bold=False, fg="gray", bg="#F4F1EC"):
    weight = "bold" if bold else "normal"
    return tk.Label(root, text=text, font=("Arial", font_size, weight),
                    fg=fg, bg=bg)

lbl("DIGITAL PRODUCT PASSPORT", 9, fg="#7A7870").pack(pady=(18, 0))

servo_label = lbl("Schalung: OFFEN", 15, bold=True, fg="#2980b9")
servo_label.pack(pady=6)

status_label = lbl("Status: BEREIT", 10, fg="gray")
status_label.pack(pady=2)

uri_label = lbl("", 8, fg="#2D5A3D")
uri_label.pack(pady=2)
uri_label.bind("<Button-1>", lambda e: oeffne_dpp(uri_label.cget("text")) if uri_label.cget("text") else None)
uri_label.bind("<Enter>", lambda e: uri_label.config(cursor="hand2", font=("Arial", 8, "underline")))
uri_label.bind("<Leave>", lambda e: uri_label.config(cursor="", font=("Arial", 8)))

frame = tk.Frame(root, bg="#F4F1EC")
frame.pack(pady=10)

tk.Button(frame, text="Schliessen & Start", command=sende_start,
          font=("Arial", 12), bg="#d5e8d4", fg="#1A1916",
          relief="flat", padx=16, pady=8).grid(row=0, column=0, padx=8)

tk.Button(frame, text="Öffnen & Stopp", command=sende_stopp,
          font=("Arial", 12), bg="#f8cecc", fg="#1A1916",
          relief="flat", padx=16, pady=8).grid(row=0, column=1, padx=8)

lbl(f"GTIN: {GTIN}  ·  {W3ID_BASE}", 8, fg="#7A7870").pack(pady=(4, 0))

# ─── DPP Liste ───────────────────────────────────────────────────────────────

lbl("ERSTELLTE PASSPORTS", 8, bold=True, fg="#7A7870").pack(pady=(12, 2))

list_frame = tk.Frame(root, bg="#F4F1EC")
list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

scrollbar = tk.Scrollbar(list_frame)
scrollbar.pack(side="right", fill="y")

listbox = tk.Listbox(
    list_frame,
    yscrollcommand=scrollbar.set,
    font=("Courier", 9),
    bg="#FDFCFA", fg="#1A1916",
    selectbackground="#2D5A3D", selectforeground="#fff",
    relief="flat", borderwidth=1,
    activestyle="none",
    height=8
)
listbox.pack(side="left", fill="both", expand=True)
scrollbar.config(command=listbox.yview)

def lade_liste():
    """Lädt alle Passports aus passports/*.jsonld in die Listbox."""
    listbox.delete(0, "end")
    passport_path = os.path.join(GITHUB_REPO, PASSPORT_DIR)
    if not os.path.isdir(passport_path):
        return
    dateien = sorted(glob.glob(os.path.join(passport_path, "*.jsonld")), reverse=True)
    for datei in dateien:
        try:
            with open(datei, encoding="utf-8") as f:
                jld = json.load(f)
            sn    = jld.get("gs1:serialNumber", os.path.basename(datei).replace(".jsonld", ""))
            datum = (jld.get("bsdd:Herstellungsdatum") or {}).get("@value", jld.get("productionDate", ""))
            temp  = (jld.get("bsdd:AussentemperaturSchalung") or {}).get("@value", "")
            dauer = (jld.get("bsdd:DauerInSchalung") or {}).get("@value", "")
            status = jld.get("bsdd:SegmentStatus", "")
            listbox.insert("end", f"  {sn}  |  {datum}  |  {temp}°C  |  {dauer}min  |  {status}")
        except Exception:
            pass

def zeige_link(event):
    """Zeigt den Link des ausgewählten Eintrags im Link-Label an."""
    sel = listbox.curselection()
    if not sel:
        return
    sn = listbox.get(sel[0]).strip().split("|")[0].strip()
    liste_link_label.config(text=f"{W3ID_BASE}/{sn}", fg="#2D5A3D")

def oeffne_ausgewaehlt(event):
    sel = listbox.curselection()
    if not sel:
        return
    sn = listbox.get(sel[0]).strip().split("|")[0].strip()
    oeffne_dpp(f"{W3ID_BASE}/{sn}")

listbox.bind("<<ListboxSelect>>", zeige_link)
listbox.bind("<Double-Button-1>", oeffne_ausgewaehlt)
listbox.bind("<Return>", oeffne_ausgewaehlt)

liste_link_label = tk.Label(root, text="", font=("Arial", 8), fg="#2D5A3D", bg="#F4F1EC", cursor="hand2")
liste_link_label.pack(pady=(0, 4))
liste_link_label.bind("<Button-1>", lambda e: oeffne_dpp(liste_link_label.cget("text")) if liste_link_label.cget("text") else None)
liste_link_label.bind("<Enter>", lambda e: liste_link_label.config(font=("Arial", 8, "underline")))
liste_link_label.bind("<Leave>", lambda e: liste_link_label.config(font=("Arial", 8)))

lade_liste()

root.after(100, lese_seriell)
root.mainloop()