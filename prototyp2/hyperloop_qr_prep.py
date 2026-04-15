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
COUNT      = 24                 # 3 × 8 = eine A4-Seite
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

    # Ränder
    margin_x = 5 * mm
    margin_y = 5 * mm
    usable_w = W - 2 * margin_x
    usable_h = H - 2 * margin_y

    cell_w = usable_w / COLS
    cell_h = usable_h / ROWS

    c = canvas.Canvas(path, pagesize=A4)

    for i, label in enumerate(labels[:COLS * ROWS]):
        col = i % COLS
        row = i // COLS

        # Ursprung oben-links -> reportlab Koordinaten (0,0 = unten-links)
        x0 = margin_x + col * cell_w
        y0 = H - margin_y - (row + 1) * cell_h

        # Rahmen (gestrichelt)
        c.setStrokeColorRGB(0.75, 0.75, 0.75)
        c.setLineWidth(0.4)
        c.setDash(3, 3)
        c.rect(x0, y0, cell_w, cell_h)
        c.setDash()  # reset

        pad = 2 * mm

        # QR-Code: 90° gedreht, quadratisch, Höhe = Zellhöhe - 2×pad
        qr_size = cell_h - 2 * pad

        if label.get("img"):
            img_rotated = label["img"].rotate(90, expand=True)
            buf = BytesIO()
            img_rotated.save(buf, format="PNG")
            buf.seek(0)
            ir = ImageReader(buf)
            c.drawImage(ir, x0 + pad, y0 + pad, qr_size, qr_size, mask="auto")

        # Seriennummer + URI rechts vom QR
        text_x = x0 + pad + qr_size + 2 * mm
        text_max_w = cell_w - qr_size - 3 * pad - 2 * mm

        # SN (gross)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(text_x, y0 + cell_h - pad - 7, label["id"])

        # "DPP" Label
        c.setFont("Helvetica", 5.5)
        c.setFillColorRGB(0.45, 0.45, 0.45)
        c.drawString(text_x, y0 + cell_h - pad - 16, "Digital Product Passport")

        # URI (klein, umgebrochen)
        c.setFont("Helvetica", 4.5)
        c.setFillColorRGB(0.6, 0.6, 0.6)
        uri = label["uri"]
        # Teile URI in zwei Zeilen auf /21/ Grenze
        if "/21/" in uri:
            parts = uri.split("/21/")
            line1 = parts[0] + "/21/"
            line2 = parts[1]
        else:
            line1 = uri[:len(uri)//2]
            line2 = uri[len(uri)//2:]
        c.drawString(text_x, y0 + pad + 9, line1)
        c.drawString(text_x, y0 + pad + 3, line2)

    c.save()
    print(f"  PDF gespeichert: {path}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    labels = []
    for _ in range(COUNT):
        serial = generate_serial()
        uri = f"{W3ID_BASE}/01/{GTIN}/21/{serial}"
        print(f"  Generiere {serial} -> {uri}")
        img = make_qr_image(uri)
        labels.append({"id": serial, "uri": uri, "img": img})

    # PDF
    pdf_path = os.path.join(OUTPUT_DIR, "labels.pdf")
    make_pdf(labels, pdf_path)

    # Manifest
    manifest_path = os.path.join(OUTPUT_DIR, "prepared.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump([{"id": l["id"], "uri": l["uri"], "used": False}
                   for l in labels], f, indent=2)

    print(f"\n  {COUNT} Labels -> {pdf_path}")
    print(f"  Manifest  -> {manifest_path}")


if __name__ == "__main__":
    main()
