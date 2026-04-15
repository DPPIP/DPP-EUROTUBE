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
GTIN           = "09999000000001"   # GS1 GTIN-14
GITHUB_PAGES   = "https://DPPIP.github.io/DPP-EUROTUBE"
GITHUB_REPO    = "C:/Users/david/Documents/DPP-EUROTUBE"
PASSPORT_DIR   = "passports"

HERSTELLER  = "Eurotube – FHNW"
PRODUKT     = "Beton-Fertigelement Typ A"
MATERIAL    = "Beton C40/50, Bewehrungsstahl B500B"
BSDD_BASE   = "https://identifier.buildingsmart.org/uri/demo2026/HYPER-DPP/0.6"
BETONSORTE  = "C25/30"
HERSTELLUNGSORT = "Koblenz"

# ─────────────────────────────────────────────────────────────────────────────


def extrahiere_id(scanned: str) -> str:
    """
    Extrahiert die Segment-ID aus dem gescannten QR-Code Text.
    Unterstützt GS1 Digital Link URI Format:
      "https://w3id.org/hyperloop-dpp/01/09999000000001/21/9867341762"  → "9867341762"
      "https://w3id.org/hyperloop-dpp/01/09999000000001/10/4521"        → "4521"
      "9867341762"                                                        → "9867341762"
    """
    scanned = scanned.strip().split('?')[0].rstrip('/')
    if '/21/' in scanned:
        return scanned.split('/21/')[-1]
    if '/10/' in scanned:
        return scanned.split('/10/')[-1]
    if '/' in scanned:
        return scanned.split('/')[-1]
    return scanned



def oeffne_dpp(uri: str):
    sn = uri.split("/")[-1]
    viewer_url = f"{GITHUB_PAGES}/passports/viewer.html?sn={sn}"
    threading.Thread(target=lambda: webbrowser.open(viewer_url), daemon=True).start()


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
            f"{BSDD_BASE}/class/HyperloopSegment",
            "IfcBuildingElementProxy"
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
        "bsdd:SegmentID":                  eintrag["Serial"],
        "bsdd:StrengthClass":              BETONSORTE,
        "bsdd:AssemblyPlace":              HERSTELLUNGSORT,
        "bsdd:ManufactoringDate":          {"@value": eintrag["Datum"],                       "@type": "xsd:dateTime"},
        "bsdd:ReferenceEnvironmentTemperature": {"@value": str(eintrag["Temperatur"]),        "@type": "xsd:decimal"},
        "bsdd:ReferenceAirRelativeHumidity":    {"@value": str(eintrag["Feuchtigkeit"]),      "@type": "xsd:decimal"},
        "bsdd:Schalungsdauer":             {"@value": str(round(eintrag["Dauer"] / 60, 2)),   "@type": "xsd:decimal"},
        "bsdd:Status":          "Hergestellt",
        "bsdd:BatchID":         eintrag["Batch"],
        "bsdd:Verbindungsdatum":   None,
        "bsdd:VerlinkungBauteile": [],
        "bsdd:BatchStatus":        None,
        "bsdd:Einbaudatum":        None,
    }


# ─── HTML Generator ──────────────────────────────────────────────────────────

def erstelle_html(eintrag: dict, jsonld: dict, qr_b64: str = "") -> str:
    # Nicht mehr verwendet – HTML wird durch passports/viewer.html on-the-fly gerendert
    return ""



# ─── GitHub Push ─────────────────────────────────────────────────────────────

def github_push(serial_nr: str, dateien: list):
    if not os.path.isdir(GITHUB_REPO):
        print(f"  [!] Git-Repo nicht gefunden: {GITHUB_REPO}")
        return
    try:
        # Zuerst pullen, damit keine Konflikte beim Push entstehen
        subprocess.run(["git", "-C", GITHUB_REPO, "pull", "--rebase", "--autostash"], check=True)
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
    uri   = f"{W3ID_BASE}/01/{GTIN}/21/{sn}"
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

    github_push(sn, [jsonld_datei])

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
