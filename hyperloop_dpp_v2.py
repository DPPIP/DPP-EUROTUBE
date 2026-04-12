"""
hyperloop_dpp_v2.py – DPP mit QR-Code Verknüpfung
==================================================
Variante 2: Nach dem Öffnen der Schalung wird der vorgedruckte
QR-Code des physischen Elements gescannt → DPP erhält diese ID.

Unterschied zu v1:
  - Stop-Event speichert Sensordaten zwischen
  - Scan-Dialog erscheint: QR-Scanner / RFID füllt Feld automatisch
  - DPP wird mit gescannter ID erstellt (statt Timestamp)

QR-Labels vorbereiten:
    python hyperloop_qr_prep.py

Abhängigkeiten:
    pip install pyserial qrcode[pil]
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
from tkinter import messagebox
import webbrowser
from io import BytesIO

# ─── CONFIG ──────────────────────────────────────────────────────────────────

PORT        = "COM7"
BAUD        = 9600

W3ID_BASE      = "https://w3id.org/hyperloop-dpp"
GITHUB_PAGES   = "https://DPPIP.github.io/DPP-EUROTUBE"
GITHUB_REPO    = "C:/Users/david/Documents/DPP-EUROTUBE"
PASSPORT_DIR   = "passports"

HERSTELLER  = "Eurotube – FHNW"
PRODUKT     = "Beton-Fertigelement Typ A"
MATERIAL    = "Beton C40/50, Bewehrungsstahl B500B"
BSDD_BASE   = "https://identifier.buildingsmart.org/uri/demo2026/HYPER-DPP/0.1"

# ─────────────────────────────────────────────────────────────────────────────


def extrahiere_id(scanned: str) -> str:
    """
    Extrahiert die Segment-ID aus dem gescannten QR-Code Text.
    Beispiele:
      "https://w3id.org/hyperloop-dpp/SEG-001"  → "SEG-001"
      "https://w3id.org/hyperloop-dpp/SEG-042"  → "SEG-042"
      "SEG-007"                                  → "SEG-007"
    """
    scanned = scanned.strip()
    # URL-Format: letzter Pfad-Teil
    if "/" in scanned:
        return scanned.rstrip("/").split("/")[-1]
    return scanned


def batch_nummer() -> str:
    now = datetime.datetime.now()
    return f"LOT-{now.year}-{now.isocalendar()[1]:02d}"


def oeffne_dpp(uri: str):
    sn = uri.split("/")[-1]
    github_url = f"{GITHUB_PAGES}/{PASSPORT_DIR}/{sn}.html"
    def _open():
        try:
            urllib.request.urlopen(
                urllib.request.Request(uri, method="HEAD"), timeout=3)
            webbrowser.open(uri)
        except Exception:
            webbrowser.open(github_url)
    threading.Thread(target=_open, daemon=True).start()


# ─── JSON-LD Generator ───────────────────────────────────────────────────────

def erstelle_jsonld(eintrag: dict) -> dict:
    uri = eintrag["uri"]
    return {
        "@context": {
            "xsd":     "http://www.w3.org/2001/XMLSchema#",
            "bsdd":    f"{BSDD_BASE}/prop/",
            "dpp":     "https://w3id.org/dpp#",
            "dcterms": "http://purl.org/dc/terms/"
        },
        "@type": [
            "dpp:DigitalProductPassport",
            f"{BSDD_BASE}/class/HyperloopSegment"
        ],
        "@id":   uri,
        "dpp:status":       "active",
        "dcterms:created":  eintrag["Datum"],
        "dcterms:modified": eintrag["Datum"],
        "dcterms:creator":  HERSTELLER,
        "dpp:wasDerivedFrom": {
            "dpp:attributedTo": "Arduino Sensor – Digital Twin SMF",
            "dpp:method":       "Automatisiert via Serial-Kommunikation (USB, 9600 Baud)"
        },
        "bsdd:SegmentID":   eintrag["Serial"],
        "bsdd:Herstellungsdatum":        {"@value": eintrag["Datum"],          "@type": "xsd:dateTime"},
        "bsdd:DauerInSchalung":          {"@value": str(eintrag["Dauer"]),     "@type": "xsd:decimal"},
        "bsdd:AussentemperaturSchalung": {"@value": str(eintrag["Temperatur"]),"@type": "xsd:decimal"},
        "bsdd:Materialzusammensetzung":  MATERIAL,
        "bsdd:SegmentStatus":   "Produced",
        "bsdd:BatchID":            eintrag["Batch"],
        "bsdd:Verbindungsdatum":   None,
        "bsdd:VerlinkungBauteile": [],
        "bsdd:BatchStatus":        None,
        "bsdd:Einbaudatum":        None,
    }


# ─── HTML Generator ──────────────────────────────────────────────────────────

def erstelle_html(eintrag: dict, jsonld: dict, qr_b64: str) -> str:
    uri   = eintrag["uri"]
    sn    = eintrag["Serial"]
    batch = eintrag.get("Batch", "")
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DPP \u2013 {sn}</title>
<script>
(function() {{
  if (new URLSearchParams(window.location.search).get('single')) return;
  var sn = "{sn}";
  fetch('https://DPPIP.github.io/DPP-EUROTUBE/passports/' + sn + '.jsonld', {{cache:'no-store'}})
    .then(function(r){{ return r.json(); }})
    .then(function(jld){{
      var b = jld['bsdd:BatchID'];
      if (!b) return;
      return fetch('https://DPPIP.github.io/DPP-EUROTUBE/batch/' + b + '.jsonld', {{method:'HEAD'}})
        .then(function(r) {{
          if (r.ok) {{
            window.location.replace('../batch/index.html?batch=' + encodeURIComponent(b) + '&from=' + sn + '.html');
          }}
        }});
    }}).catch(function(){{}});
}})();
</script>
<script type="application/ld+json">
{json.dumps(jsonld, ensure_ascii=False, indent=2)}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#F4F1EC;--card:#FDFCFA;--ink:#1A1916;--muted:#7A7870;--accent:#2D5A3D;--border:#DDD9D1;--mono:'DM Mono',monospace;--sans:'DM Sans',sans-serif}}
body{{background:var(--bg);font-family:var(--sans);color:var(--ink);padding:2rem 1rem}}
.wrap{{max-width:520px;margin:0 auto}}
.badge{{background:var(--accent);color:#fff;font-family:var(--mono);font-size:10px;font-weight:500;letter-spacing:.12em;padding:4px 10px;border-radius:4px;text-transform:uppercase;display:inline-block}}
.badge-v2{{background:#2980b9;color:#fff;font-family:var(--mono);font-size:10px;font-weight:500;letter-spacing:.12em;padding:4px 10px;border-radius:4px;text-transform:uppercase;display:inline-block;margin-left:6px}}
h1{{font-size:24px;font-weight:300;margin:.5rem 0 .25rem}}
.sub{{font-size:12px;color:var(--muted);font-family:var(--mono);margin-bottom:1.5rem}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.25rem;margin-bottom:1rem}}
.card-label{{font-size:10px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:1rem;font-family:var(--mono)}}
.metrics{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}
.metric label{{font-size:11px;color:var(--muted);display:block;margin-bottom:4px}}
.metric .val{{font-size:30px;font-weight:300;line-height:1}}
.metric .unit{{font-size:13px;color:var(--muted);margin-left:2px}}
.metric.full{{grid-column:1/-1}}
.row{{display:flex;align-items:center;gap:8px;padding:9px 0;border-bottom:1px solid var(--border);font-size:13px}}
.row:last-child{{border-bottom:none}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--accent);flex-shrink:0}}
.key{{color:var(--muted);flex:1}}
.vm{{font-family:var(--mono);font-size:12px}}
.qr-wrap{{text-align:center;padding:.5rem 0}}
.qr-wrap img{{width:148px;height:148px;border-radius:8px;border:1px solid var(--border);padding:6px;background:#fff}}
.uri{{font-size:10px;color:var(--muted);font-family:var(--mono);margin-top:8px;word-break:break-all}}
.single-link{{display:block;text-align:center;margin-top:.75rem;font-size:12px;color:var(--accent);font-family:var(--mono)}}
.footer{{text-align:center;font-size:11px;color:var(--muted);margin-top:2rem;font-family:var(--mono)}}
</style>
</head>
<body>
<div class="wrap">
  <span class="badge">Digital Product Passport</span>
  <span class="badge-v2">QR-Verknüpft</span>
  <h1>{PRODUKT}</h1>
  <p class="sub">{eintrag['Datum']} &nbsp;&middot;&nbsp; {sn}</p>
  <div class="card">
    <p class="card-label">Produktionsdaten</p>
    <div class="metrics">
      <div class="metric"><label>Temperatur (&oslash;)</label><span class="val">{eintrag['Temperatur']}<span class="unit">&deg;C</span></span></div>
      <div class="metric"><label>Feuchtigkeit (&oslash;)</label><span class="val">{eintrag['Feuchtigkeit']}<span class="unit">%</span></span></div>
      <div class="metric full"><label>Aush&auml;rte-Dauer</label><span class="val">{eintrag['Dauer']}<span class="unit"> min</span></span></div>
    </div>
  </div>
  <div class="card">
    <p class="card-label">Identifikation</p>
    <div class="row"><span class="dot"></span><span class="key">Segment ID</span><span class="vm">{sn}</span></div>
    <div class="row"><span class="dot"></span><span class="key">Batch</span><span class="vm">{batch}</span></div>
    <div class="row"><span class="dot"></span><span class="key">Hersteller</span><span class="vm">{HERSTELLER}</span></div>
    <div class="row"><span class="dot"></span><span class="key">Material</span><span class="vm">{MATERIAL}</span></div>
    <div class="row"><span class="dot"></span><span class="key">Status</span><span class="vm" style="color:var(--accent)">Produced</span></div>
  </div>
  <div class="card">
    <p class="card-label">QR-Code &ndash; dieser Passport</p>
    <div class="qr-wrap">
      <img src="data:image/png;base64,{qr_b64}" alt="QR Code">
      <p class="uri">{uri}</p>
    </div>
    <a class="single-link" href="?single=1">&rarr; Nur dieser Passport anzeigen</a>
  </div>
  <p class="footer">Hyperloop Digital Twin (V2) &middot; {eintrag['Datum']}<br>
  JSON-LD: <a href="{sn}.jsonld" style="color:var(--accent)">{sn}.jsonld</a></p>
</div>
</body>
</html>"""


# ─── QR Code ─────────────────────────────────────────────────────────────────

def erstelle_qr_b64(uri: str) -> str:
    try:
        import qrcode
        qr = qrcode.QRCode(version=None,
                           error_correction=qrcode.constants.ERROR_CORRECT_M,
                           box_size=6, border=2)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        return ""



# ─── GitHub Push ─────────────────────────────────────────────────────────────

def github_push(serial_nr: str, dateien: list):
    if not os.path.isdir(GITHUB_REPO):
        print(f"  [!] Git-Repo nicht gefunden: {GITHUB_REPO}")
        return
    try:
        for pfad in dateien:
            ziel = os.path.join(GITHUB_REPO, pfad)
            os.makedirs(os.path.dirname(ziel) or GITHUB_REPO, exist_ok=True)
            with open(pfad, "rb") as f: inhalt = f.read()
            with open(ziel, "wb") as f: f.write(inhalt)
        subprocess.run(["git", "-C", GITHUB_REPO, "add"] +
                       [os.path.abspath(os.path.join(GITHUB_REPO, p)) for p in dateien], check=True)
        subprocess.run(["git", "-C", GITHUB_REPO, "commit", "-m",
                        f"DPP {serial_nr} hinzugefügt (V2)"], check=True)
        subprocess.run(["git", "-C", GITHUB_REPO, "push"], check=True)
        print(f"  [OK] GitHub Push: {serial_nr}")
    except subprocess.CalledProcessError as e:
        print(f"  [!] Git-Fehler: {e}")


# ─── Speichern & Publizieren ─────────────────────────────────────────────────

def speichere_und_publiziere(t_med: float, h_med: float, dauer: float,
                              segment_id: str):
    """Erstellt DPP mit gescannter Segment-ID."""
    sn    = segment_id
    uri   = f"{W3ID_BASE}/{sn}"
    batch = ""   # wird erst beim Batch-Scan in batch/index.html gesetzt
    datum = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    eintrag = {
        "Datum":        datum,
        "Temperatur":   t_med,
        "Feuchtigkeit": h_med,
        "Dauer":        dauer,
        "Batch":        batch,
        "Serial":       sn,
        "uri":          uri
    }

    os.makedirs(PASSPORT_DIR, exist_ok=True)

    jsonld       = erstelle_jsonld(eintrag)
    jsonld_datei = os.path.join(PASSPORT_DIR, f"{sn}.jsonld")
    with open(jsonld_datei, "w", encoding="utf-8") as f:
        json.dump(jsonld, f, indent=2, ensure_ascii=False)

    qr_b64       = erstelle_qr_b64(uri)
    html_datei   = os.path.join(PASSPORT_DIR, f"{sn}.html")
    with open(html_datei, "w", encoding="utf-8") as f:
        f.write(erstelle_html(eintrag, jsonld, qr_b64))

    github_push(sn, [jsonld_datei, html_datei])

    print(f"  [OK] {sn} | {dauer}min | {t_med}°C | URI: {uri}")
    return sn, uri


# ─── Scan-Dialog ─────────────────────────────────────────────────────────────

def zeige_scan_dialog(t_med: float, h_med: float, dauer: float):
    """
    Scan-Dialog mit Kamera-Preview (OpenCV + pyzbar).
    Erkennt QR-Code automatisch → bestätigt sofort.
    Fallback: manuelles Eingabefeld für USB-Scanner.
    """
    import tkinter as tk
    from PIL import Image, ImageTk

    dialog = tk.Toplevel(root)
    dialog.title("QR-Code scannen")
    dialog.geometry("420x520")
    dialog.configure(bg="#F4F1EC")
    dialog.grab_set()
    dialog.focus_set()

    tk.Label(dialog, text="QR-Code vor die Kamera halten",
             font=("Arial", 13, "bold"), bg="#F4F1EC", fg="#1A1916"
             ).pack(pady=(16, 2))
    tk.Label(dialog, text=f"Messung: {t_med}°C  {h_med}%  {dauer} min",
             font=("Arial", 10), bg="#F4F1EC", fg="#7A7870"
             ).pack(pady=(0, 8))

    # Kamera-Canvas
    canvas = tk.Canvas(dialog, width=360, height=270, bg="#000",
                       highlightthickness=0)
    canvas.pack()

    status_lbl = tk.Label(dialog, text="Suche QR-Code oder RFID-Karte…",
                          font=("Courier", 10), bg="#F4F1EC", fg="#7A7870")
    status_lbl.pack(pady=6)

    # Manuelles Eingabefeld (Fallback / USB-Scanner)
    tk.Label(dialog, text="oder manuell / USB-Scanner:",
             font=("Arial", 9), bg="#F4F1EC", fg="#aaa").pack()
    entry_var = tk.StringVar()
    entry = tk.Entry(dialog, textvariable=entry_var,
                     font=("Courier", 11), width=30,
                     relief="flat", highlightthickness=1,
                     highlightbackground="#DDD9D1", highlightcolor="#2D5A3D")
    entry.pack(ipady=6, padx=24, pady=(2, 8))

    scanning = [True]
    cap = [None]

    # RFID-Callback registrieren → lese_seriell() kann publiziere() aufrufen
    global _scan_callback

    def publiziere(seg_id: str):
        # Prüfen ob QR-Code bereits einem Bauteil zugewiesen ist (HEAD-Check)
        try:
            check_url = f"{GITHUB_PAGES}/{PASSPORT_DIR}/{seg_id}.jsonld"
            req = urllib.request.Request(check_url, method="HEAD")
            urllib.request.urlopen(req, timeout=5)
            # 200 → Datei existiert → bereits vergeben
            status_lbl.config(text=f"⛔ {seg_id} bereits vergeben!", fg="#A03030")
            messagebox.showerror(
                "Doppelter QR-Code",
                f"{seg_id} ist bereits einem Bauteil zugewiesen.\n"
                "Bitte einen anderen QR-Code verwenden."
            )
            scanning[0] = True
            return
        except urllib.error.HTTPError as e:
            if e.code != 404:
                pass  # anderer Fehler → trotzdem erlauben
        except Exception:
            pass  # Netzwerkfehler → erlauben

        global _scan_callback
        _scan_callback = None   # Dialog schliesst → kein RFID-Callback mehr
        scanning[0] = False
        if cap[0]:
            cap[0].release()
        dialog.destroy()
        status_label.config(text=f"Status: PUBLIZIERE {seg_id}…", fg="#e67e22")
        root.update()

        def _publish():
            sn, uri = speichere_und_publiziere(t_med, h_med, dauer, seg_id)
            root.after(0, lambda: _fertig(sn, uri))

        def _fertig(sn, uri):
            status_label.config(text=f"Status: FERTIG – {sn}", fg="gray")
            servo_label.config(text="Schalung: OFFEN", fg="#2980b9")
            uri_label.config(text=uri, fg="#2D5A3D")
            lade_liste()

        threading.Thread(target=_publish, daemon=True).start()

    # Callback registrieren: RFID-Treffer in lese_seriell() → publiziere()
    _scan_callback = publiziere

    def bestaetigen(event=None):
        raw = entry_var.get().strip()
        if raw:
            publiziere(extrahiere_id(raw))

    entry.bind("<Return>", bestaetigen)
    tk.Button(dialog, text="Bestätigen", command=bestaetigen,
              font=("Arial", 11), bg="#2D5A3D", fg="white",
              relief="flat", padx=16, pady=6).pack(pady=(0, 4))
    tk.Button(dialog, text="Überspringen",
              command=lambda: [globals().__setitem__('_scan_callback', None),
                               scanning.__setitem__(0, False),
                               cap[0].release() if cap[0] else None,
                               dialog.destroy()],
              font=("Arial", 9), bg="#F4F1EC", fg="#7A7870",
              relief="flat").pack()

    def kamera_loop():
        try:
            import cv2
            from pyzbar import pyzbar as pz
        except ImportError:
            status_lbl.config(text="opencv/pyzbar nicht installiert")
            return

        cap[0] = cv2.VideoCapture(0)
        if not cap[0].isOpened():
            status_lbl.config(text="Keine Kamera gefunden – bitte manuell eingeben")
            return

        def update():
            if not scanning[0] or not cap[0]:
                return
            ret, frame = cap[0].read()
            if not ret:
                dialog.after(50, update)
                return

            # QR erkennen
            codes = pz.decode(frame)
            for code in codes:
                data = code.data.decode("utf-8", errors="ignore").strip()
                if data:
                    seg_id = extrahiere_id(data)
                    status_lbl.config(text=f"Erkannt: {seg_id}", fg="#2D5A3D")
                    dialog.after(400, lambda sid=seg_id: publiziere(sid))
                    return

            # Kamerabild anzeigen
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb).resize((360, 270))
            photo = ImageTk.PhotoImage(img)
            canvas.photo = photo
            canvas.create_image(0, 0, anchor="nw", image=photo)

            dialog.after(30, update)

        dialog.after(100, update)

    dialog.protocol("WM_DELETE_WINDOW", lambda: [
        globals().__setitem__('_scan_callback', None),
        scanning.__setitem__(0, False),
        cap[0].release() if cap[0] else None,
        dialog.destroy()
    ])

    threading.Thread(target=kamera_loop, daemon=True).start()


# ─── Serieller Logger ────────────────────────────────────────────────────────

try:
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[OK] Logger aktiv an {PORT}")
except Exception as e:
    print(f"[!] Serielle Verbindung fehlgeschlagen: {e}")
    exit(1)

zyklus: dict = {"start": None, "t": [], "h": []}

# Callback-Slot: wird gesetzt wenn Scan-Dialog offen ist
# → lese_seriell() ruft ihn bei RFID-Treffer auf
_scan_callback = None


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
                servo_label.config(text="Schalung: GESCHLOSSEN", fg="#c0392b")
                print("[●] Produktion gestartet")

            elif msg_type == "sensor" and zyklus["start"]:
                if "temp" in data: zyklus["t"].append(data["temp"])
                if "hum"  in data: zyklus["h"].append(data["hum"])

            elif msg_type == "rfid":
                url = data.get("url", "").strip()
                if url and _scan_callback:
                    seg_id = extrahiere_id(url)
                    print(f"  [RFID] Erkannt: {seg_id}")
                    root.after(0, lambda sid=seg_id: _scan_callback(sid))

            elif msg_type == "rfid_error":
                print(f"  [RFID] Fehler: {data.get('msg')}")

            elif event in ["system_stopp", "cmd_stopp"] and zyklus["start"]:
                t_med = round(sum(zyklus["t"]) / len(zyklus["t"]), 1) if zyklus["t"] else 0.0
                h_med = round(sum(zyklus["h"]) / len(zyklus["h"]), 1) if zyklus["h"] else 0.0
                dauer = round(time.time() - zyklus["start"], 1)
                zyklus["start"] = None

                servo_label.config(text="Schalung: OFFEN", fg="#2980b9")
                status_label.config(text="Status: WARTE AUF SCAN…", fg="#e67e22")
                root.update()

                # ← Scan-Dialog statt sofort publizieren
                root.after(100, lambda t=t_med, h=h_med, d=dauer:
                           zeige_scan_dialog(t, h, d))

        except Exception:
            pass

    root.after(100, lese_seriell)


# ─── GUI ─────────────────────────────────────────────────────────────────────

root = tk.Tk()
root.title("Hyperloop DPP V2 – QR/RFID Verknüpfung")
root.geometry("640x520")
root.configure(bg="#F4F1EC")

def lbl(text, font_size=10, bold=False, fg="gray", bg="#F4F1EC"):
    weight = "bold" if bold else "normal"
    return tk.Label(root, text=text, font=("Arial", font_size, weight),
                    fg=fg, bg=bg)

lbl("DIGITAL PRODUCT PASSPORT  ·  V2 QR/RFID", 9, fg="#2980b9").pack(pady=(18, 0))

servo_label = lbl("Schalung: OFFEN", 15, bold=True, fg="#2980b9")
servo_label.pack(pady=6)

status_label = lbl("Status: BEREIT", 10, fg="gray")
status_label.pack(pady=2)

uri_label = lbl("", 8, fg="#2D5A3D")
uri_label.pack(pady=2)
uri_label.bind("<Button-1>",
               lambda e: oeffne_dpp(uri_label.cget("text")) if uri_label.cget("text") else None)
uri_label.bind("<Enter>",
               lambda e: uri_label.config(cursor="hand2", font=("Arial", 8, "underline")))
uri_label.bind("<Leave>",
               lambda e: uri_label.config(cursor="", font=("Arial", 8)))

frame = tk.Frame(root, bg="#F4F1EC")
frame.pack(pady=10)

tk.Button(frame, text="Schliessen & Start", command=sende_start,
          font=("Arial", 12), bg="#d5e8d4", fg="#1A1916",
          relief="flat", padx=16, pady=8).grid(row=0, column=0, padx=8)

tk.Button(frame, text="Öffnen & Stopp", command=sende_stopp,
          font=("Arial", 12), bg="#f8cecc", fg="#1A1916",
          relief="flat", padx=16, pady=8).grid(row=0, column=1, padx=8)

lbl(f"W3ID: {W3ID_BASE}", 8, fg="#7A7870").pack(pady=(4, 0))

# ─── DPP Liste ───────────────────────────────────────────────────────────────

lbl("ERSTELLTE PASSPORTS", 8, bold=True, fg="#7A7870").pack(pady=(12, 2))

list_frame = tk.Frame(root, bg="#F4F1EC")
list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

scrollbar = tk.Scrollbar(list_frame)
scrollbar.pack(side="right", fill="y")

listbox = tk.Listbox(
    list_frame, yscrollcommand=scrollbar.set,
    font=("Courier", 9), bg="#FDFCFA", fg="#1A1916",
    selectbackground="#2980b9", selectforeground="#fff",
    relief="flat", borderwidth=1, activestyle="none", height=8
)
listbox.pack(side="left", fill="both", expand=True)
scrollbar.config(command=listbox.yview)


def lade_liste():
    listbox.delete(0, "end")
    passport_path = os.path.join(GITHUB_REPO, PASSPORT_DIR)
    if not os.path.isdir(passport_path):
        return
    dateien = sorted(glob.glob(os.path.join(passport_path, "*.jsonld")), reverse=True)
    for datei in dateien:
        try:
            with open(datei, encoding="utf-8") as f:
                jld = json.load(f)
            sn    = jld.get("bsdd:SegmentID", os.path.basename(datei).replace(".jsonld", ""))
            datum = (jld.get("bsdd:Herstellungsdatum") or {}).get("@value", "")
            temp  = (jld.get("bsdd:AussentemperaturSchalung") or {}).get("@value", "")
            dauer = (jld.get("bsdd:DauerInSchalung") or {}).get("@value", "")
            listbox.insert("end", f"  {sn}  |  {datum}  |  {temp}°C  |  {dauer}min")
        except Exception:
            pass


def zeige_link(event):
    sel = listbox.curselection()
    if not sel: return
    sn = listbox.get(sel[0]).strip().split("|")[0].strip()
    pfad = os.path.join(GITHUB_REPO, PASSPORT_DIR, f"{sn}.jsonld")
    try:
        with open(pfad, encoding="utf-8") as f:
            uri = json.load(f).get("@id", f"{W3ID_BASE}/{sn}")
    except Exception:
        uri = f"{W3ID_BASE}/{sn}"
    liste_link_label.config(text=uri, fg="#2D5A3D")


def oeffne_ausgewaehlt(event):
    sel = listbox.curselection()
    if not sel: return
    sn = listbox.get(sel[0]).strip().split("|")[0].strip()
    pfad = os.path.join(GITHUB_REPO, PASSPORT_DIR, f"{sn}.jsonld")
    try:
        with open(pfad, encoding="utf-8") as f:
            uri = json.load(f).get("@id", f"{W3ID_BASE}/{sn}")
    except Exception:
        uri = f"{W3ID_BASE}/{sn}"
    oeffne_dpp(uri)


listbox.bind("<<ListboxSelect>>", zeige_link)
listbox.bind("<Double-Button-1>", oeffne_ausgewaehlt)
listbox.bind("<Return>", oeffne_ausgewaehlt)

liste_link_label = tk.Label(root, text="", font=("Arial", 8),
                            fg="#2D5A3D", bg="#F4F1EC", cursor="hand2")
liste_link_label.pack(pady=(0, 4))
liste_link_label.bind("<Button-1>",
                      lambda e: oeffne_dpp(liste_link_label.cget("text"))
                      if liste_link_label.cget("text") else None)
liste_link_label.bind("<Enter>",
                      lambda e: liste_link_label.config(font=("Arial", 8, "underline")))
liste_link_label.bind("<Leave>",
                      lambda e: liste_link_label.config(font=("Arial", 8)))

lade_liste()

root.after(100, lese_seriell)
root.mainloop()
