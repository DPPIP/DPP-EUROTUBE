"""
hyperloop_qr_prep.py – QR-Code Vorbereitung
============================================
Erstellt vorgedruckte QR-Code Labels mit W3ID URIs.

Output:
  qr_labels/labels.pdf   – druckbares A4-PDF, 3 Spalten × 8 Zeilen, QR 90° gedreht
  qr_labels/prepared.json – Manifest der generierten SNs

Verwendung:
    python hyperloop_qr_prep.py

Abhängigkeiten:
    pip install qrcode[pil] reportlab
"""

import os
import io
import json
import random
import base64
from io import BytesIO

# ─── CONFIG ──────────────────────────────────────────────────────────────────

W3ID_BASE  = "https://w3id.org/hyperloop-dpp"
GTIN       = "09999000000001"   # GS1 GTIN-14
COUNT      = 11                 # 11 unterschiedliche SNs
OUTPUT_DIR = "qr_labels"

COLS = 3
ROWS = 8

# ─────────────────────────────────────────────────────────────────────────────


def generate_serial() -> str:
    return str(random.randint(1000000000, 9999999999))


def make_qr_image(uri: str):
    """Gibt ein PIL-Image des QR-Codes zurück."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2
        )
        qr.add_data(uri)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white").convert("RGB")
    except ImportError:
        print("[!] qrcode nicht installiert: pip install qrcode[pil]")
        return None


def make_pdf(labels: list, path: str):
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from PIL import Image
    except ImportError:
        print("[!] reportlab nicht installiert: pip install reportlab")
        return

    W, H = A4  # 595.27 × 841.89 pt

    # Randlos: Etiketten füllen die gesamte A4-Seite
    cell_w = W / COLS
    cell_h = H / ROWS

    c = canvas.Canvas(path, pagesize=A4)

    for i, label in enumerate(labels[:COLS * ROWS]):
        col = i % COLS
        row = i // COLS

        x0 = col * cell_w
        y0 = H - (row + 1) * cell_h

        pad = 1.5 * mm

        # QR-Code: 90° gedreht, etwas kleiner als Zellhöhe
        qr_size = cell_h * 0.78

        if label.get("img"):
            img_rotated = label["img"].rotate(90, expand=True)
            buf = BytesIO()
            img_rotated.save(buf, format="PNG")
            buf.seek(0)
            ir = ImageReader(buf)
            # QR vertikal zentriert, kleiner Abstand vom linken Rand
            qr_y = y0 + (cell_h - qr_size) / 2
            c.drawImage(ir, x0 + 2 * mm, qr_y, qr_size, qr_size, mask="auto")

        # Text rechts vom QR
        text_x = x0 + 2 * mm + qr_size + 2.5 * mm
        center_y = y0 + cell_h / 2

        # SN
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(text_x, center_y + 6, label["id"])

        # "Digital Product Passport"
        c.setFont("Helvetica", 5.5)
        c.setFillColorRGB(0.45, 0.45, 0.45)
        c.drawString(text_x, center_y - 1, "Digital Product Passport")

        # URI: sinnvoll aufgeteilt in 3 Zeilen
        # Zeile 1: https://w3id.org/hyperloop-dpp/
        # Zeile 2: 01/09999000000001/21/
        # Zeile 3: {serial}
        c.setFont("Helvetica", 4.5)
        c.setFillColorRGB(0.65, 0.65, 0.65)
        uri = label["uri"]
        if "/01/" in uri and "/21/" in uri:
            base   = uri.split("/01/")[0] + "/"          # https://w3id.org/hyperloop-dpp/
            middle = "01/" + uri.split("/01/")[1].split("/21/")[0] + "/21/"  # 01/GTIN/21/
            serial = uri.split("/21/")[1]                # serial
        else:
            base, middle, serial = uri, "", ""
        c.drawString(text_x, center_y - 9,  base)
        c.drawString(text_x, center_y - 14, middle)
        c.drawString(text_x, center_y - 19, serial)

    c.save()
    print(f"  PDF gespeichert: {path}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 11 unterschiedliche SNs generieren
    unique = []
    for _ in range(COUNT):
        serial = generate_serial()
        uri = f"{W3ID_BASE}/01/{GTIN}/21/{serial}"
        print(f"  Generiere {serial} -> {uri}")
        img = make_qr_image(uri)
        unique.append({"id": serial, "uri": uri, "img": img})

    # 2 davon doppelt -> total 13 Etiketten
    labels = unique + [unique[0], unique[1]]
    print(f"\n  Duplikate: {unique[0]['id']} (2x), {unique[1]['id']} (2x)")

    # PDF
    pdf_path = os.path.join(OUTPUT_DIR, "labels.pdf")
    make_pdf(labels, pdf_path)

    # Manifest (nur die 11 eindeutigen SNs)
    manifest_path = os.path.join(OUTPUT_DIR, "prepared.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump([{"id": l["id"], "uri": l["uri"], "used": False}
                   for l in unique], f, indent=2)

    print(f"  13 Labels (11 einmalig + 2x2) -> {pdf_path}")
    print(f"  Manifest  -> {manifest_path}")


if __name__ == "__main__":
    main()
