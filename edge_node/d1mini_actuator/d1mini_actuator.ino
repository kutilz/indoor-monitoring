/**
 * Node Aktuator Terpadu — AC Clicker + Relay Lampu + Sensor DHT22
 *
 * Board yang didukung:
 *   - Wemos D1 Mini (ESP8266) — cukup untuk pin, tapi servo mungkin jitter saat Wi-Fi aktif
 *   - ESP32 Dev Module (REKOMENDASI) — hardware PWM stabil, dual core, lebih banyak pin
 *
 * Wiring:
 *   Servo 0 (Power AC)  → D1 (GPIO5)
 *   Servo 1 (Temp Up)   → D2 (GPIO4)
 *   Servo 2 (Temp Down) → D5 (GPIO14)
 *   Relay Lampu         → D6 (GPIO12)  [aktif HIGH: HIGH=ON, LOW=OFF]
 *   DHT22 Data          → D7 (GPIO13)  [+ resistor pull-up 10kΩ ke 3.3V]
 *
 * Catatan power servo:
 *   JANGAN pakai pin VCC/3.3V onboard untuk supply servo.
 *   Pakai power supply 5V eksternal dengan GND bersama (common GND dengan board).
 *
 * HTTP REST API Endpoints:
 *   GET  /health                               → status node
 *   GET  /sensor                               → pembacaan DHT22
 *   GET  /servo/config                         → kalibrasi tersimpan semua servo
 *   POST /servo/move?id=<0-2>&angle=<0-180>   → gerakin servo ke sudut (kalibrasi)
 *   POST /servo/click?id=<0-2>                → jalankan urutan klik dengan easing
 *   POST /servo/calibrate?id=<0-2>&stay=<angle>&click=<angle> → simpan kalibrasi
 *   POST /relay?state=<ON|OFF>                → kontrol relay lampu
 *
 * Library yang dibutuhkan (install via Arduino Library Manager):
 *   - ESP8266Servo  (jika pakai D1 Mini)  ATAU  ESP32Servo  (jika pakai ESP32)
 *   - DHTesp        by beegee_tokyo
 *   - ArduinoJson   by Benoit Blanchon    (versi 6.x atau 7.x)
 *   - LittleFS      (built-in untuk ESP8266 core >= 2.7, dan ESP32 core >= 1.0.6)
 *
 * Untuk ESP8266: di Arduino IDE, pilih board "LOLIN(WEMOS) D1 R2 & mini"
 * Untuk ESP32:   di Arduino IDE, pilih board "ESP32 Dev Module"
 */

// ── Deteksi board ─────────────────────────────────────────────────────────────
#ifdef ESP32
  #include <WiFi.h>
  #include <WebServer.h>
  #include <ESP32Servo.h>
  #include <LittleFS.h>
  #define PLATFORM "ESP32"
#else
  #include <ESP8266WiFi.h>
  #include <ESP8266WebServer.h>
  #include <ESP8266Servo.h>
  #include <LittleFS.h>
  #define PLATFORM "ESP8266"
#endif

#include <ArduinoJson.h>
#include <DHTesp.h>

// ── Konfigurasi WiFi ──────────────────────────────────────────────────────────
#define WIFI_SSID     "NAMA_WIFI_KAMU"
#define WIFI_PASSWORD "PASSWORD_WIFI"

// ── Pin ───────────────────────────────────────────────────────────────────────
#define PIN_SERVO_0   5    // D1 — Power AC
#define PIN_SERVO_1   4    // D2 — Temp Up
#define PIN_SERVO_2   14   // D5 — Temp Down
#define PIN_RELAY     12   // D6 — Relay Lampu (aktif HIGH)
#define PIN_DHT22     13   // D7 — DHT22 Data

// ── Konstanta Servo ───────────────────────────────────────────────────────────
#define NUM_SERVOS           3
#define SERVO_DEFAULT_STAY   90    // Sudut aman default (tengah range 0-180)
#define SERVO_DEFAULT_CLICK  90    // Default sama — tidak bergerak sampai dikalibrasi
#define SERVO_MAX_TRAVEL     120   // Batas maksimum perjalanan dari stay ke click (derajat)

// Easing: 70% pertama cepat, 30% terakhir lambat
#define CLICK_DELAY_FAST_MS  15    // ms per derajat fase cepat
#define CLICK_DELAY_SLOW_MS  35    // ms per derajat fase lambat (mendekat titik klik)
#define CLICK_HOLD_MS        200   // ms tahan di posisi klik
#define CLICK_SETTLE_MS      300   // ms setelah kembali ke stay

// ── Nama file kalibrasi di LittleFS ──────────────────────────────────────────
#define CALIBRATION_FILE "/calibration.json"

// ── Nama servo (untuk log & response JSON) ────────────────────────────────────
const char* SERVO_NAMES[NUM_SERVOS] = {"Power AC", "Temp Up", "Temp Down"};
const int   SERVO_PINS[NUM_SERVOS]  = {PIN_SERVO_0, PIN_SERVO_1, PIN_SERVO_2};

// ── Objects ───────────────────────────────────────────────────────────────────
Servo servos[NUM_SERVOS];
DHTesp dht;

#ifdef ESP32
  WebServer server(80);
#else
  ESP8266WebServer server(80);
#endif

// ── State kalibrasi ───────────────────────────────────────────────────────────
struct ServoConfig {
  int stay_angle;
  int click_angle;
};
ServoConfig servoConfig[NUM_SERVOS];

// ── LittleFS: load/save kalibrasi ─────────────────────────────────────────────

void loadCalibration() {
  for (int i = 0; i < NUM_SERVOS; i++) {
    servoConfig[i].stay_angle  = SERVO_DEFAULT_STAY;
    servoConfig[i].click_angle = SERVO_DEFAULT_CLICK;
  }

  if (!LittleFS.exists(CALIBRATION_FILE)) {
    Serial.println("[Cal] File kalibrasi tidak ditemukan, pakai default (stay=90, click=90).");
    return;
  }

  File f = LittleFS.open(CALIBRATION_FILE, "r");
  if (!f) {
    Serial.println("[Cal] Gagal buka file kalibrasi.");
    return;
  }

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, f);
  f.close();

  if (err) {
    Serial.printf("[Cal] JSON parse error: %s\n", err.c_str());
    return;
  }

  for (int i = 0; i < NUM_SERVOS; i++) {
    String key = "servo" + String(i);
    if (doc.containsKey(key)) {
      servoConfig[i].stay_angle  = doc[key]["stay"]  | SERVO_DEFAULT_STAY;
      servoConfig[i].click_angle = doc[key]["click"] | SERVO_DEFAULT_CLICK;
    }
  }

  Serial.println("[Cal] Kalibrasi dimuat:");
  for (int i = 0; i < NUM_SERVOS; i++) {
    Serial.printf("  Servo %d (%s): stay=%d, click=%d\n",
                  i, SERVO_NAMES[i],
                  servoConfig[i].stay_angle,
                  servoConfig[i].click_angle);
  }
}

bool saveCalibration() {
  StaticJsonDocument<512> doc;

  for (int i = 0; i < NUM_SERVOS; i++) {
    String key = "servo" + String(i);
    doc[key]["stay"]  = servoConfig[i].stay_angle;
    doc[key]["click"] = servoConfig[i].click_angle;
  }

  File f = LittleFS.open(CALIBRATION_FILE, "w");
  if (!f) {
    Serial.println("[Cal] Gagal tulis file kalibrasi.");
    return false;
  }
  serializeJson(doc, f);
  f.close();
  Serial.println("[Cal] Kalibrasi disimpan ke LittleFS.");
  return true;
}

// ── Logika servo click dengan easing ─────────────────────────────────────────

void doClick(int servoId) {
  int stay_a  = servoConfig[servoId].stay_angle;
  int click_a = servoConfig[servoId].click_angle;
  int diff    = click_a - stay_a;

  if (diff == 0) {
    Serial.printf("[Servo %d] stay==click, tidak bergerak (belum dikalibrasi).\n", servoId);
    return;
  }

  int dir      = (diff > 0) ? 1 : -1;
  int absDiff  = abs(diff);
  int slowStep = (int)(absDiff * 0.70f);  // 70% pertama: cepat

  Serial.printf("[Servo %d] Klik: %d → %d (easing)\n", servoId, stay_a, click_a);

  servos[servoId].attach(SERVO_PINS[servoId]);
  servos[servoId].write(stay_a);
  delay(100);

  int current = stay_a;
  for (int step = 0; step < absDiff; step++) {
    current += dir;
    servos[servoId].write(current);
    if (step < slowStep) {
      delay(CLICK_DELAY_FAST_MS);   // Fase cepat
    } else {
      delay(CLICK_DELAY_SLOW_MS);   // Fase lambat — mendekat titik klik
    }
  }

  delay(CLICK_HOLD_MS);             // Tahan di posisi klik
  servos[servoId].write(stay_a);    // Kembali ke posisi stay (cepat)
  delay(CLICK_SETTLE_MS);           // Tunggu servo settle

  servos[servoId].detach();         // Detach agar servo tidak bergetar/mendengung
  Serial.printf("[Servo %d] Klik selesai, kembali ke %d.\n", servoId, stay_a);
}

void moveServo(int servoId, int angle) {
  angle = constrain(angle, 0, 180);
  servos[servoId].attach(SERVO_PINS[servoId]);
  servos[servoId].write(angle);
  delay(400);  // Cukup waktu servo mencapai posisi
  // Tidak detach — biarkan tetap di posisi untuk kalibrasi interaktif
  Serial.printf("[Servo %d] Pindah ke sudut %d\n", servoId, angle);
}

// ── Helpers HTTP ───────────────────────────────────────────────────────────────

void sendJson(int code, const String &body) {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(code, "application/json", body);
}

int getServoId() {
  if (!server.hasArg("id")) return -1;
  int id = server.arg("id").toInt();
  if (id < 0 || id >= NUM_SERVOS) return -1;
  return id;
}

// ── HTTP Handlers ─────────────────────────────────────────────────────────────

void handleHealth() {
  StaticJsonDocument<128> doc;
  doc["status"]   = "ok";
  doc["platform"] = PLATFORM;
  doc["uptime_s"] = millis() / 1000;
  doc["ip"]       = WiFi.localIP().toString();

  String out;
  serializeJson(doc, out);
  sendJson(200, out);
}

void handleSensor() {
  TempAndHumidity data = dht.getTempAndHumidity();
  bool ok = !isnan(data.temperature) && !isnan(data.humidity);

  StaticJsonDocument<128> doc;
  doc["ok"]       = ok;
  doc["temp"]     = ok ? round(data.temperature * 10.0f) / 10.0f : 0.0f;
  doc["humidity"] = ok ? round(data.humidity    * 10.0f) / 10.0f : 0.0f;

  if (!ok) {
    Serial.println("[DHT22] Gagal baca sensor.");
  }

  String out;
  serializeJson(doc, out);
  sendJson(200, out);
}

void handleServoConfig() {
  StaticJsonDocument<512> doc;

  for (int i = 0; i < NUM_SERVOS; i++) {
    String key = "servo" + String(i);
    doc[key]["id"]    = i;
    doc[key]["name"]  = SERVO_NAMES[i];
    doc[key]["stay"]  = servoConfig[i].stay_angle;
    doc[key]["click"] = servoConfig[i].click_angle;
    doc[key]["travel"] = abs(servoConfig[i].click_angle - servoConfig[i].stay_angle);
  }

  String out;
  serializeJson(doc, out);
  sendJson(200, out);
}

void handleServoMove() {
  int id = getServoId();
  if (id < 0) {
    sendJson(400, "{\"error\":\"id servo tidak valid (0-2)\"}");
    return;
  }
  if (!server.hasArg("angle")) {
    sendJson(400, "{\"error\":\"parameter angle diperlukan\"}");
    return;
  }

  int angle = constrain(server.arg("angle").toInt(), 0, 180);
  moveServo(id, angle);

  StaticJsonDocument<128> doc;
  doc["ok"]    = true;
  doc["servo"] = id;
  doc["angle"] = angle;

  String out;
  serializeJson(doc, out);
  sendJson(200, out);
}

void handleServoClick() {
  int id = getServoId();
  if (id < 0) {
    sendJson(400, "{\"error\":\"id servo tidak valid (0-2)\"}");
    return;
  }

  doClick(id);

  StaticJsonDocument<128> doc;
  doc["ok"]    = true;
  doc["servo"] = id;
  doc["name"]  = SERVO_NAMES[id];

  String out;
  serializeJson(doc, out);
  sendJson(200, out);
}

void handleServoCalibrate() {
  int id = getServoId();
  if (id < 0) {
    sendJson(400, "{\"error\":\"id servo tidak valid (0-2)\"}");
    return;
  }
  if (!server.hasArg("stay") || !server.hasArg("click")) {
    sendJson(400, "{\"error\":\"parameter stay dan click diperlukan\"}");
    return;
  }

  int stay_a  = constrain(server.arg("stay").toInt(), 0, 180);
  int click_a = constrain(server.arg("click").toInt(), 0, 180);
  int travel  = abs(click_a - stay_a);

  if (travel > SERVO_MAX_TRAVEL) {
    StaticJsonDocument<128> doc;
    doc["ok"]      = false;
    doc["error"]   = "Perjalanan servo melebihi batas aman 120 derajat";
    doc["travel"]  = travel;
    doc["max"]     = SERVO_MAX_TRAVEL;
    String out;
    serializeJson(doc, out);
    sendJson(400, out);
    return;
  }

  servoConfig[id].stay_angle  = stay_a;
  servoConfig[id].click_angle = click_a;
  bool saved = saveCalibration();

  StaticJsonDocument<128> doc;
  doc["ok"]     = saved;
  doc["servo"]  = id;
  doc["stay"]   = stay_a;
  doc["click"]  = click_a;
  doc["travel"] = travel;

  String out;
  serializeJson(doc, out);
  sendJson(saved ? 200 : 500, out);
}

void handleRelay() {
  if (!server.hasArg("state")) {
    sendJson(400, "{\"error\":\"parameter state diperlukan (ON atau OFF)\"}");
    return;
  }

  String stateStr = server.arg("state");
  stateStr.toUpperCase();

  if (stateStr != "ON" && stateStr != "OFF") {
    sendJson(400, "{\"error\":\"state harus ON atau OFF\"}");
    return;
  }

  bool on = (stateStr == "ON");
  digitalWrite(PIN_RELAY, on ? HIGH : LOW);

  Serial.printf("[Relay] Lampu → %s\n", stateStr.c_str());

  StaticJsonDocument<64> doc;
  doc["ok"]    = true;
  doc["relay"] = "lamp";
  doc["state"] = stateStr;
  String out;
  serializeJson(doc, out);
  sendJson(200, out);
}

void handleNotFound() {
  sendJson(404, "{\"error\":\"endpoint tidak ditemukan\"}");
}

// ── WiFi Setup ────────────────────────────────────────────────────────────────

void connectWiFi() {
  Serial.printf("[WiFi] Menghubungkan ke: %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempt = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (++attempt > 40) {
      Serial.println("\n[WiFi] Timeout! Restart...");
      ESP.restart();
    }
  }

  Serial.println();
  Serial.printf("[WiFi] Terhubung! IP: %s\n", WiFi.localIP().toString().c_str());
}

// ── setup() ───────────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);
  Serial.printf("\n[Boot] Node Aktuator (%s) starting...\n", PLATFORM);

  // Relay
  pinMode(PIN_RELAY, OUTPUT);
  digitalWrite(PIN_RELAY, LOW);  // Lampu OFF saat boot
  Serial.println("[Boot] Relay diinisialisasi (OFF).");

  // DHT22
  dht.setup(PIN_DHT22, DHTesp::DHT22);
  Serial.println("[Boot] DHT22 diinisialisasi.");

  // LittleFS — format otomatis jika partisi belum pernah diformat (umum terjadi
  // pada ESP32 baru / pertama kali pakai LittleFS)
  if (!LittleFS.begin(true)) {
    Serial.println("[Boot] LittleFS gagal mount walau sudah dicoba format! Cek Partition Scheme di Tools (harus ada alokasi SPIFFS/LittleFS).");
    // Jangan stop — lanjutkan dengan nilai default
  } else {
    Serial.println("[Boot] LittleFS OK.");
  }

  // Kalibrasi
  loadCalibration();

  // Posisikan semua servo ke stay_angle saat boot
  for (int i = 0; i < NUM_SERVOS; i++) {
    servos[i].attach(SERVO_PINS[i]);
    servos[i].write(servoConfig[i].stay_angle);
    delay(300);
    servos[i].detach();  // Detach setelah posisi tercapai (mencegah dengung)
    Serial.printf("[Boot] Servo %d (%s) → stay=%d°\n",
                  i, SERVO_NAMES[i], servoConfig[i].stay_angle);
  }

  // WiFi
  connectWiFi();

  // HTTP Server
  server.on("/health",           HTTP_GET,  handleHealth);
  server.on("/sensor",           HTTP_GET,  handleSensor);
  server.on("/servo/config",     HTTP_GET,  handleServoConfig);
  server.on("/servo/move",       HTTP_POST, handleServoMove);
  server.on("/servo/click",      HTTP_POST, handleServoClick);
  server.on("/servo/calibrate",  HTTP_POST, handleServoCalibrate);
  server.on("/relay",            HTTP_POST, handleRelay);
  server.onNotFound(handleNotFound);
  server.begin();

  Serial.println("[Boot] HTTP server berjalan di port 80.");
  Serial.println("[Boot] Siap menerima perintah.\n");
  Serial.printf("  Contoh: curl http://%s/health\n", WiFi.localIP().toString().c_str());
  Serial.printf("  Kalibrasi: curl -X POST \"http://%s/servo/calibrate?id=0&stay=90&click=150\"\n\n",
                WiFi.localIP().toString().c_str());
}

// ── loop() ────────────────────────────────────────────────────────────────────

void loop() {
  // Cek WiFi reconnect
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Terputus! Reconnecting...");
    WiFi.reconnect();
    delay(3000);
    return;
  }

  server.handleClient();
}
