/**
 * hyperloop_dpp_combined.ino
 * ──────────────────────────
 * Kombiniert: DHT11-Sensor + Servo (Schalung) + RFID-Leser (MFRC522)
 *
 * Pins:
 *   DHT11   → Pin 2
 *   Taster  → Pin 3
 *   Servo   → Pin 6
 *   RFID RST→ Pin 9
 *   RFID SS → Pin 10
 *   RFID SPI→ 11 (MOSI), 12 (MISO), 13 (SCK) [Standard Arduino SPI]
 *
 * Bibliotheken:
 *   DHT sensor library (Adafruit)
 *   Servo (built-in)
 *   MFRC522 (Miguel Balboa)
 *
 * Protokoll (seriell, 9600 Baud):
 *   Befehle von Python: 'C' = schliessen/start, 'O' = öffnen/stopp
 *   Ausgaben JSON:
 *     {"type":"boot","msg":"System bereit"}
 *     {"type":"event","event":"cmd_start"}
 *     {"type":"sensor","grund":"periodic","temp":22.5,"hum":58.0,"servo":5}
 *     {"type":"event","event":"cmd_stopp"}
 *     {"type":"rfid","url":"https://w3id.org/hyperloop-dpp/SN-..."}
 *     {"type":"rfid_error","msg":"Karte nicht lesbar"}
 */

#include "DHT.h"
#include <Servo.h>
#include <SPI.h>
#include <MFRC522.h>

// ─── Pins ────────────────────────────────────────────────────────────────────
#define DHTPIN       2
#define DHTTYPE      DHT11
#define TASTER_PIN   3
#define SERVO_PIN    6
#define RST_PIN      9
#define SS_PIN       10

// ─── Intervalle ──────────────────────────────────────────────────────────────
#define SENSOR_INTERVALL 2000

// ─── Objekte ─────────────────────────────────────────────────────────────────
DHT      dht(DHTPIN, DHTTYPE);
Servo    schalung;
MFRC522  mfrc522(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key rfidKey;

// ─── Zustandsvariablen ───────────────────────────────────────────────────────
bool sensorAktiv          = false;
bool rfidAktiv            = false;   // true = Scan wird erwartet (Schalung offen)
bool letzterTasterZustand = HIGH;
unsigned long letzterSensorSend = 0;
int aktuellerWinkel       = 85;


// ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

void sendeStatus(const char* grund) {
  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();

  Serial.print("{\"type\":\"sensor\",\"grund\":\"");
  Serial.print(grund);
  Serial.print("\",\"temp\":");
  if (!isnan(temp)) Serial.print(temp, 1); else Serial.print("\"null\"");
  Serial.print(",\"hum\":");
  if (!isnan(hum))  Serial.print(hum, 1);  else Serial.print("\"null\"");
  Serial.print(",\"servo\":");
  Serial.print(aktuellerWinkel);
  Serial.println("}");
}

void oeffneSchalung() {
  schalung.attach(SERVO_PIN);
  aktuellerWinkel = 85;
  schalung.write(aktuellerWinkel);
  delay(400);
  schalung.detach();
}

void schliesseSchalung() {
  schalung.attach(SERVO_PIN);
  aktuellerWinkel = 5;
  schalung.write(aktuellerWinkel);
  delay(400);
  schalung.detach();
}

// ─── RFID lesen ──────────────────────────────────────────────────────────────

void leseRFID() {
  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) return;

  MFRC522::StatusCode status;
  byte buffer[18];
  byte size = sizeof(buffer);
  String fullData = "";

  // Authentifizierung Sektor 1 (Block 4)
  status = mfrc522.PCD_Authenticate(
    MFRC522::PICC_CMD_MF_AUTH_KEY_A, 4, &rfidKey, &(mfrc522.uid)
  );
  if (status != MFRC522::STATUS_OK) {
    Serial.println("{\"type\":\"rfid_error\",\"msg\":\"Auth fehlgeschlagen\"}");
    mfrc522.PICC_HaltA();
    return;
  }

  // Blöcke 4–6 lesen
  for (byte block = 4; block <= 6; block++) {
    status = mfrc522.MIFARE_Read(block, buffer, &size);
    if (status == MFRC522::STATUS_OK) {
      for (byte i = 0; i < 16; i++) {
        fullData += (char)buffer[i];
      }
    }
  }

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();

  // URL aus NDEF-Daten extrahieren
  String url = "";
  int headerIndex = -1;

  for (int i = 0; i < (int)fullData.length(); i++) {
    if (fullData[i] == 0x55) { headerIndex = i; break; }
  }

  if (headerIndex != -1 && headerIndex + 1 < (int)fullData.length()) {
    byte prefix = fullData[headerIndex + 1];
    if      (prefix == 0x01) url = "http://www.";
    else if (prefix == 0x02) url = "https://www.";
    else if (prefix == 0x03) url = "http://";
    else if (prefix == 0x04) url = "https://";

    for (int i = headerIndex + 2; i < (int)fullData.length(); i++) {
      byte c = fullData[i];
      if (c == 0xFE) break;
      if (c >= 32 && c <= 126) url += (char)c;
    }
  }

  if (url.length() > 0) {
    Serial.print("{\"type\":\"rfid\",\"url\":\"");
    Serial.print(url);
    Serial.println("\"}");
    rfidAktiv = false;  // Einmalig – nach erfolgtem Scan zurücksetzen
  } else {
    Serial.println("{\"type\":\"rfid_error\",\"msg\":\"Keine URL auf Karte\"}");
  }
}


// ─── Setup ───────────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(9600);
  dht.begin();
  pinMode(TASTER_PIN, INPUT_PULLUP);

  // Servo Startposition
  schalung.attach(SERVO_PIN);
  schalung.write(aktuellerWinkel);
  delay(400);
  schalung.detach();

  // SPI + RFID initialisieren
  SPI.begin();
  mfrc522.PCD_Init();

  // NFC-Forum Key (D3 F7 D3 F7 D3 F7)
  for (byte i = 0; i < 6; i++) {
    rfidKey.keyByte[i] = (i % 2 == 0) ? 0xD3 : 0xF7;
  }

  Serial.println("{\"type\":\"boot\",\"msg\":\"System bereit (DHT+Servo+RFID)\"}");
}


// ─── Loop ────────────────────────────────────────────────────────────────────

void loop() {

  // ── 1. Befehle von Python lesen ──────────────────────────────────────────
  if (Serial.available() > 0) {
    char cmd = Serial.read();

    if (cmd == 'C') {
      sensorAktiv = true;
      rfidAktiv   = false;   // kein Scan während Messung
      schliesseSchalung();
      Serial.println("{\"type\":\"event\",\"event\":\"cmd_start\"}");
      sendeStatus("start");
      letzterSensorSend = millis();
    }
    else if (cmd == 'O') {
      sensorAktiv = false;
      rfidAktiv   = true;    // Scan wird jetzt erwartet
      oeffneSchalung();
      Serial.println("{\"type\":\"event\",\"event\":\"cmd_stopp\"}");
    }
  }

  // ── 2. Taster abfragen ───────────────────────────────────────────────────
  bool aktuellerTasterZustand = digitalRead(TASTER_PIN);

  if (aktuellerTasterZustand == LOW && letzterTasterZustand == HIGH) {
    sensorAktiv = !sensorAktiv;
    schalung.attach(SERVO_PIN);

    if (sensorAktiv) {
      rfidAktiv = false;
      schliesseSchalung();
      Serial.println("{\"type\":\"event\",\"event\":\"system_start\"}");
      sendeStatus("start");
      letzterSensorSend = millis();
    } else {
      rfidAktiv = true;      // Scan erwartet nach manuellem Öffnen
      oeffneSchalung();
      Serial.println("{\"type\":\"event\",\"event\":\"system_stopp\"}");
    }
    delay(50);
  }

  letzterTasterZustand = aktuellerTasterZustand;

  // ── 3. Sensordaten senden ────────────────────────────────────────────────
  if (sensorAktiv) {
    unsigned long jetzt = millis();
    if (jetzt - letzterSensorSend >= SENSOR_INTERVALL) {
      letzterSensorSend = jetzt;
      sendeStatus("periodic");
    }
  }

  // ── 4. RFID prüfen (nur wenn Scan erwartet wird) ─────────────────────────
  if (rfidAktiv) {
    leseRFID();
  }
}
