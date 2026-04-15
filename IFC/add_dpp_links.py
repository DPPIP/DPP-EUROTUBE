"""
add_dpp_links.py  –  Variante 1: Nur DPP-URLs ins IFC schreiben
================================================================
Ziel-Batch: Batch (2511795) - Betonsegment_2m10-14
  -> IfcElementAssembly: ePset_DigitalProductPassport.URL = Batch-Link
  -> 5x IfcBuildingElementProxy: ePset_DigitalProductPassport.URL = Segment-Link

Output: IFC/IP3_DPP_v1.ifc
"""

import ifcopenshell
import ifcopenshell.api

INPUT  = "C:/Users/david/Documents/DPP-EUROTUBE/IFC/IP3.ifc"
OUTPUT = "C:/Users/david/Documents/DPP-EUROTUBE/IFC/IP3_DPP_v1.ifc"

PSET_NAME = "ePset_DigitalProductPassport"

BATCH_URL = "https://DPPIP.github.io/DPP-EUROTUBE/batch/index.html?batch=4873316459"

SEGMENT_URLS = [
    "https://w3id.org/hyperloop-dpp/01/09999000000001/21/8038081531",
    "https://w3id.org/hyperloop-dpp/01/09999000000001/21/1966110844",
    "https://w3id.org/hyperloop-dpp/01/09999000000001/21/4860687236",
    "https://w3id.org/hyperloop-dpp/01/09999000000001/21/6075117551",
    "https://w3id.org/hyperloop-dpp/01/09999000000001/21/5554867685",
]

TARGET_BATCH_NAME = "Allgemeines Modell Baugruppe:Batch:2511795"


def add_url_pset(f, element, url):
    pset = ifcopenshell.api.run("pset.add_pset", f, product=element, name=PSET_NAME)
    ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties={"URL": url})
    print(f"  [OK] {element.Name}  ->  {url}")


def main():
    f = ifcopenshell.open(INPUT)

    batch_el = next((e for e in f.by_type("IfcElementAssembly") if e.Name == TARGET_BATCH_NAME), None)
    if not batch_el:
        print(f"[!] Batch nicht gefunden: {TARGET_BATCH_NAME}")
        return

    print(f"\nBatch: {batch_el.Name}")
    add_url_pset(f, batch_el, BATCH_URL)

    segments = []
    for rel in f.by_type("IfcRelAggregates"):
        if rel.RelatingObject == batch_el:
            for obj in rel.RelatedObjects:
                if obj.is_a("IfcBuildingElementProxy") and "Betonsegment" in (obj.Name or ""):
                    segments.append(obj)
    segments.sort(key=lambda e: e.Name)

    if len(segments) != 5:
        print(f"[!] Erwartet 5 Segmente, gefunden: {len(segments)}")
        return

    print(f"\nSegmente ({len(segments)}):")
    for seg, url in zip(segments, SEGMENT_URLS):
        add_url_pset(f, seg, url)

    f.write(OUTPUT)
    print(f"\n[OK] Gespeichert: {OUTPUT}")


if __name__ == "__main__":
    main()
