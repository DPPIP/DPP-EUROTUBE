# Arduino Komponenten – Hyperloop DPP Prototyp

| Kategorie | Komponente |
|---|---|
| Mikrocontroller | Arduino Uno |
| Module und Sensoren | RFID-Modul RC522 |
| | DHT22 / DHT11 |
| Eingabe und Ausgabe | 2 Servomotoren |
| | Drucktaster |
| Verkabelung und Prototyping | Steckbrett |
| | Kleines Steckbrett |
| | Widerstand |
| | Jumperkabel |
| Stromversorgung | Batteriepack (4 × 1.5 V) |

## Simulation

Das Schaltschema wurde mit [Wokwi](https://wokwi.com/projects/461746891808954369) erstellt und simuliert.  
Die Dateien `sketch.ino` und `diagram.json` in diesem Ordner können direkt in Wokwi importiert werden.

## Pin-Belegung

| Komponente | Pin |
|---|---|
| DHT11/22 | 2 |
| Drucktaster | 3 (INPUT_PULLUP) |
| Servo | 6 |
| RFID RST | 9 |
| RFID SS (SDA) | 10 |
| RFID MOSI | 11 |
| RFID MISO | 12 |
| RFID SCK | 13 |
