"""
hyperloop_qr_prep.py – QR-Code Vorbereitung
============================================
Erstellt vorgedruckte QR-Code Labels mit W3ID URIs.
Output: druckbares HTML-Sheet + einzelne PNGs

Verwendung:
    python hyperloop_qr_prep.py
    → qr_labels/sheet.html  (drucken, ausschneiden, in Kessel legen)
    → qr_labels/SEG-001.png ... SEG-0xx.png
"""

import os
import base64
import json
from io import BytesIO

# ─── CONFIG ──────────────────────────────────────────────────────────────────

W3ID_BASE   = "https://w3id.org/hyperloop-dpp"
PREFIX      = "SEG"          # Prefix für Labels (SEG-001, SEG-002, ...)
START       = 1              # Erste Nummer
COUNT       = 20             # Anzahl QR-Codes generieren
OUTPUT_DIR  = "qr_labels"   # Ausgabeordner

# ─────────────────────────────────────────────────────────────────────────────


def make_qr_b64(uri: str) -> str:
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
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        print("[!] qrcode nicht installiert: pip install qrcode[pil]")
        return ""


def label_id(nr: int) -> str:
    return f"{PREFIX}-{nr:03d}"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    labels = []
    for nr in range(START, START + COUNT):
        lid = label_id(nr)
        uri = f"{W3ID_BASE}/{lid}"
        print(f"  Generiere {lid} → {uri}")

        qrb64 = make_qr_b64(uri)

        # PNG speichern
        if qrb64:
            png_data = base64.b64decode(qrb64)
            with open(os.path.join(OUTPUT_DIR, f"{lid}.png"), "wb") as f:
                f.write(png_data)

        labels.append({"id": lid, "uri": uri, "qrb64": qrb64})

    # Manifest der vorbereiteten Labels
    manifest_path = os.path.join(OUTPUT_DIR, "prepared.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump([{"id": l["id"], "uri": l["uri"], "used": False}
                   for l in labels], f, indent=2)

    # Druckbares HTML-Sheet
    sheet_path = os.path.join(OUTPUT_DIR, "sheet.html")
    with open(sheet_path, "w", encoding="utf-8") as f:
        f.write(make_sheet_html(labels))

    print(f"\n  {COUNT} Labels erstellt → {OUTPUT_DIR}/sheet.html")
    print(f"  Manifest → {manifest_path}")


def make_sheet_html(labels: list) -> str:
    cards = ""
    for l in labels:
        cards += f"""
        <div class="label">
          <img src="data:image/png;base64,{l['qrb64']}" alt="{l['id']}">
          <div class="lid">{l['id']}</div>
          <div class="uri">{l['uri']}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Hyperloop QR Labels</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: monospace; background: #fff; }}
  h1 {{ font-size: 14px; font-weight: normal; padding: 12px 16px;
        border-bottom: 1px solid #ccc; color: #555; }}
  .grid {{ display: flex; flex-wrap: wrap; padding: 8px; gap: 8px; }}
  .label {{
    width: 120px; border: 1px dashed #aaa; border-radius: 4px;
    padding: 8px; text-align: center; page-break-inside: avoid;
  }}
  .label img {{ width: 100px; height: 100px; display: block; margin: 0 auto 6px; }}
  .lid {{ font-size: 13px; font-weight: bold; letter-spacing: .05em; }}
  .uri {{ font-size: 7px; color: #888; word-break: break-all; margin-top: 3px; line-height: 1.3; }}
  @media print {{
    h1 {{ display: none; }}
    .grid {{ padding: 0; gap: 6px; }}
    .label {{ border: 1px solid #999; }}
  }}
</style>
</head>
<body>
  <h1>Hyperloop DPP – QR Labels ({W3ID_BASE})</h1>
  <div class="grid">{cards}
  </div>
</body>
</html>"""


if __name__ == "__main__":
    main()
