"""
add_dpp_data.py  –  Variante 2: DPP-Inhalte direkt ins IFC schreiben
=====================================================================
Gem. IFC-Mapping-Tabelle:

IfcElementAssembly (Batch Röhrensegment 10m):
  ePset_DigitalProductPassport:
    URL              -> Batch-DPP-Link
    Verbindungsdatum -> 2026-04-15T10:35:24
    Batch_ID         -> 4873316459
    Status           -> Verbunden
    Einbaudatum      -> (offen)

IfcBuildingElementProxy (Betonsegment 2m):
  ePset_DigitalProductPassport:
    URL              -> Segment-DPP-Link
  Pset_ConcreteElementGeneral:
    StrengthClass    -> C70/85
  Pset_ManufacturerTypeInformation:
    AssemblyPlace    -> Muttenz
  Pset_ManufacturerOccurrence:
    ManufactoringDate -> 2026-04-15T...
  Pset_EnvironmentalCondition:
    ReferenceEnvironmentTemperature -> 25.5
    ReferenceAtRelativeHumidity     -> 34.0
  Pset_Herstellung:
    Schalungsdauer -> 0.xx
    Status         -> Aktiv

Output: IFC/IP3_DPP_v2.ifc
"""

import ifcopenshell
import ifcopenshell.api

INPUT  = "C:/Users/david/Documents/DPP-EUROTUBE/IFC/IP3.ifc"
OUTPUT = "C:/Users/david/Documents/DPP-EUROTUBE/IFC/IP3_DPP_v2.ifc"

TARGET_BATCH_NAME = "Allgemeines Modell Baugruppe:Batch:2511795"

BATCH_DATA = {
    "URL":              "https://DPPIP.github.io/DPP-EUROTUBE/batch/index.html?batch=4873316459",
    "Batch_ID":         "4873316459",
    "Verbindungsdatum": "2026-04-15T10:35:24",
    "Status":           "Verbunden",
    "Einbaudatum":      "offen",
}

SEGMENT_DATA = [
    {
        "url":               "https://w3id.org/hyperloop-dpp/01/09999000000001/21/8038081531",
        "StrengthClass":     "C70/85",
        "AssemblyPlace":     "Muttenz",
        "ManufactoringDate": "2026-04-15T12:27:19",
        "Temperature":       "25.5",
        "Humidity":          "34.0",
        "Schalungsdauer":    "0.39",
        "Status":            "Aktiv",
    },
    {
        "url":               "https://w3id.org/hyperloop-dpp/01/09999000000001/21/1966110844",
        "StrengthClass":     "C70/85",
        "AssemblyPlace":     "Muttenz",
        "ManufactoringDate": "2026-04-15T12:30:05",
        "Temperature":       "25.5",
        "Humidity":          "34.0",
        "Schalungsdauer":    "0.39",
        "Status":            "Aktiv",
    },
    {
        "url":               "https://w3id.org/hyperloop-dpp/01/09999000000001/21/4860687236",
        "StrengthClass":     "C70/85",
        "AssemblyPlace":     "Muttenz",
        "ManufactoringDate": "2026-04-15T12:30:49",
        "Temperature":       "25.5",
        "Humidity":          "34.0",
        "Schalungsdauer":    "0.30",
        "Status":            "Aktiv",
    },
    {
        "url":               "https://w3id.org/hyperloop-dpp/01/09999000000001/21/6075117551",
        "StrengthClass":     "C70/85",
        "AssemblyPlace":     "Muttenz",
        "ManufactoringDate": "2026-04-15T12:31:18",
        "Temperature":       "25.5",
        "Humidity":          "34.0",
        "Schalungsdauer":    "0.18",
        "Status":            "Aktiv",
    },
    {
        "url":               "https://w3id.org/hyperloop-dpp/01/09999000000001/21/5554867685",
        "StrengthClass":     "C70/85",
        "AssemblyPlace":     "Muttenz",
        "ManufactoringDate": "2026-04-15T12:32:30",
        "Temperature":       "25.5",
        "Humidity":          "34.0",
        "Schalungsdauer":    "0.15",
        "Status":            "Aktiv",
    },
]


def add_pset(f, element, pset_name, props):
    pset = ifcopenshell.api.run("pset.add_pset", f, product=element, name=pset_name)
    ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=props)


def main():
    f = ifcopenshell.open(INPUT)

    batch_el = next((e for e in f.by_type("IfcElementAssembly") if e.Name == TARGET_BATCH_NAME), None)
    if not batch_el:
        print(f"[!] Batch nicht gefunden: {TARGET_BATCH_NAME}")
        return

    # --- Batch ---
    print(f"\nBatch: {batch_el.Name}")
    add_pset(f, batch_el, "ePset_DigitalProductPassport", BATCH_DATA)
    print(f"  [OK] ePset_DigitalProductPassport geschrieben")

    # --- Segmente ---
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
    for seg, d in zip(segments, SEGMENT_DATA):
        add_pset(f, seg, "ePset_DigitalProductPassport", {"URL": d["url"]})
        add_pset(f, seg, "Pset_ConcreteElementGeneral",  {"StrengthClass": d["StrengthClass"]})
        add_pset(f, seg, "Pset_ManufacturerTypeInformation", {"AssemblyPlace": d["AssemblyPlace"]})
        add_pset(f, seg, "Pset_ManufacturerOccurrence",  {"ManufactoringDate": d["ManufactoringDate"]})
        add_pset(f, seg, "Pset_EnvironmentalCondition",  {
            "ReferenceEnvironmentTemperature": d["Temperature"],
            "ReferenceAtRelativeHumidity":     d["Humidity"],
        })
        add_pset(f, seg, "Pset_Herstellung", {
            "Schalungsdauer": d["Schalungsdauer"],
            "Status":         d["Status"],
        })
        print(f"  [OK] {seg.Name}")

    f.write(OUTPUT)
    print(f"\n[OK] Gespeichert: {OUTPUT}")


if __name__ == "__main__":
    main()
