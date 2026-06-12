/**
 * Node Aktuator Terpadu — AC Clicker (servo continuous-rotation) + Relay Lampu + DHT22
 *
 * Board yang didukung:
 *   - Wemos D1 Mini (ESP8266)
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
 *   MG996R menarik arus jauh lebih besar dari SG90 (stall current ~2.5A/servo @ 6V).
 *   JANGAN pakai pin VCC/3.3V/5V onboard untuk supply servo.
 *   Pakai power supply 5V/6V eksternal min. 5A dengan GND bersama (common GND dengan board).
 *
 * ── Model Servo: Continuous Rotation (MG996R 360°) ─────────────────────────────
 * Servo ini TIDAK punya posisi — pulsa PWM menentukan ARAH + KECEPATAN putar:
 *   neutral_us (~1500, bisa di-trim per servo)        → diam (stop)
 *   neutral_us + offset                                → putar arah "CW"
 *   neutral_us - offset                                → putar arah "CCW"
 *   offset makin besar (0-180us)                       → makin cepat
 *
 * Kalibrasi per servo (tersimpan di LittleFS):
 *   - click_dir          : arah (CW/CCW) yang menekan tombol AC
 *   - click_speed        : kecepatan (0-100%) saat klik & kembali
 *   - click_duration_ms  : lama putar ke click_dir untuk menekan tombol
 *   - return_duration_ms : lama putar balik (arah berlawanan) untuk kembali ke posisi awal
 *   - neutral_us (trim)  : titik "stop" sebenarnya (kompensasi drift)
 *
 * ── HTTP REST API ───────────────────────────────────────────────────────────────
 *   GET  /health                                          → status node
 *   GET  /sensor                                          → pembacaan DHT22
 *   GET  /servo/config                                    → kalibrasi tersimpan semua servo
 *   POST /servo/jog?id=<0-2>&dir=<CW|CCW>&speed=<0-100>   → putar selama heartbeat masuk (kalibrasi manual)
 *   POST /servo/stop?id=<0-2>                             → berhenti segera
 *   POST /servo/stop_all                                  → berhenti semua servo (emergency stop)
 *   POST /servo/click?id=<0-2>                            → jalankan urutan klik (pakai kalibrasi tersimpan)
 *   POST /servo/calibrate?id=<0-2>&dir=&speed=&click_ms=&return_ms=&trim=  → simpan kalibrasi
 *   POST /relay?state=<ON|OFF>                            → kontrol relay lampu
 *
 * ── Safety: Jog Watchdog ────────────────────────────────────────────────────────
 *   /servo/jog HARUS dipanggil berulang (heartbeat, ~150ms) selama tombol jog ditahan
 *   di dashboard. Jika tidak ada heartbeat dalam JOG_WATCHDOG_MS, servo dihentikan
 *   otomatis. Ada juga batas absolut JOG_ABSOLUTE_MAX_MS agar servo tidak bisa
 *   berputar tanpa henti walau heartbeat terus masuk (proteksi bug frontend).
 *   Jika WiFi putus, SEMUA servo langsung dihentikan (tidak menunggu watchdog).
 *
 * Library yang dibutuhkan (install via Arduino Library Manager):
 *   - ESP8266Servo  (jika pakai D1 Mini)  ATAU  ESP32Servo  (jika pakai ESP32)
 *   - DHTesp        by beegee_tokyo
 *   - ArduinoJson   by Benoit Blanchon    (versi 6.x atau 7.x)
 *   - LittleFS      (built-in untuk ESP8266 core >= 2.7, dan ESP32 core >= 1.0.6)
 *
 * Untuk ESP8266: di Arduino IDE, pilih board "LOLIN(WEMOS) D1 R2 & mini"
 * Untuk ESP32:   di Arduino IDE, pilih board "ESP32 Dev Module"
 *                (pastikan Partition Scheme punya alokasi SPIFFS/LittleFS)
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

// ── Konstanta Servo (continuous rotation) ────────────────────────────────────
#define NUM_SERVOS 3

#define SERVO_NEUTRAL_US_DEFAULT  1500   // pulsa "stop" default
#define SERVO_TRIM_MIN           -100    // batas trim neutral (us)
#define SERVO_TRIM_MAX            100

#define JOG_MIN_OFFSET_US   30    // lewati deadband — di bawah ini servo tidak bergerak
#define JOG_MAX_OFFSET_US   180   // cap aman — speed 100% pun masih pelan-moderate
#define PULSE_MIN_US       1000   // batas pulsa absolut (constrain)
#define PULSE_MAX_US       2000

#define CLICK_DEFAULT_SPEED        30
#define CLICK_DEFAULT_DURATION_MS  300
#define CLICK_MAX_DURATION_MS     3000   // cap per fase (klik/kembali) saat simpan kalibrasi

#define STOP_SETTLE_MS  80    // delay setelah tulis pulsa stop, sebelum detach

// ── Safety: Jog Watchdog ──────────────────────────────────────────────────────
#define JOG_WATCHDOG_MS      400   // tanpa heartbeat selama ini → auto-stop
#define JOG_ABSOLUTE_MAX_MS 4000   // batas absolut durasi jog walau heartbeat terus masuk

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

// ── State kalibrasi (persisten) ────────────────────────────────────────────────
struct ServoConfig {
  int neutral_us;          // pulsa "stop" sebenarnya (default + trim)
  int click_dir;           // +1 = CW, -1 = CCW — arah yang menekan tombol
  int click_speed;         // 0-100
  int click_duration_ms;   // lama jog ke click_dir
  int return_duration_ms;  // lama jog balik (arah berlawanan)
};
ServoConfig servoConfig[NUM_SERVOS];

// ── State jog (runtime, tidak disimpan) ────────────────────────────────────────
struct JogState {
  bool active;
  int  dirSign;          // +1 / -1
  int  speed;             // 0-100
  unsigned long lastCmdMs;
  unsigned long startMs;
};
JogState jogState[NUM_SERVOS];

// ── Helpers arah ──────────────────────────────────────────────────────────────

int parseDirSign(const String &dirStrIn, bool &valid) {
  String d = dirStrIn;
  d.toUpperCase();
  if (d == "CW")  { valid = true;  return 1; }
  if (d == "CCW") { valid = true;  return -1; }
  valid = false;
  return 0;
}

const char* dirSignToStr(int dirSign) {
  return dirSign >= 0 ? "CW" : "CCW";
}

// ── LittleFS: load/save kalibrasi ─────────────────────────────────────────────

void loadCalibration() {
  for (int i = 0; i < NUM_SERVOS; i++) {
    servoConfig[i].neutral_us         = SERVO_NEUTRAL_US_DEFAULT;
    servoConfig[i].click_dir          = 1;   // CW
    servoConfig[i].click_speed        = CLICK_DEFAULT_SPEED;
    servoConfig[i].click_duration_ms  = CLICK_DEFAULT_DURATION_MS;
    servoConfig[i].return_duration_ms = CLICK_DEFAULT_DURATION_MS;
  }

  if (!LittleFS.exists(CALIBRATION_FILE)) {
    Serial.println("[Cal] File kalibrasi tidak ditemukan, pakai default.");
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
      servoConfig[i].neutral_us         = doc[key]["neutral"]   | SERVO_NEUTRAL_US_DEFAULT;
      servoConfig[i].click_dir          = doc[key]["dir"]       | 1;
      servoConfig[i].click_speed        = doc[key]["speed"]     | CLICK_DEFAULT_SPEED;
      servoConfig[i].click_duration_ms  = doc[key]["click_ms"]  | CLICK_DEFAULT_DURATION_MS;
      servoConfig[i].return_duration_ms = doc[key]["return_ms"] | CLICK_DEFAULT_DURATION_MS;
    }
  }

  Serial.println("[Cal] Kalibrasi dimuat:");
  for (int i = 0; i < NUM_SERVOS; i++) {
    Serial.printf("  Servo %d (%s): neutral=%dus dir=%s speed=%d click=%dms return=%dms\n",
                  i, SERVO_NAMES[i],
                  servoConfig[i].neutral_us,
                  dirSignToStr(servoConfig[i].click_dir),
                  servoConfig[i].click_speed,
                  servoConfig[i].click_duration_ms,
                  servoConfig[i].return_duration_ms);
  }
}

bool saveCalibration() {
  StaticJsonDocument<512> doc;

  for (int i = 0; i < NUM_SERVOS; i++) {
    String key = "servo" + String(i);
    doc[key]["neutral"]   = servoConfig[i].neutral_us;
    doc[key]["dir"]       = servoConfig[i].click_dir;
    doc[key]["speed"]     = servoConfig[i].click_speed;
    doc[key]["click_ms"]  = servoConfig[i].click_duration_ms;
    doc[key]["return_ms"] = servoConfig[i].return_duration_ms;
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

// ── Kontrol servo continuous-rotation ──────────────────────────────────────────

// Mapping speed (0-100%) → offset pulsa (us) dari neutral
int speedToOffset(int speed) {
  speed = constrain(speed, 0, 100);
  if (speed == 0) return 0;
  return JOG_MIN_OFFSET_US +
         (int)((long)(JOG_MAX_OFFSET_US - JOG_MIN_OFFSET_US) * speed / 100);
}

int computePulse(int servoId, int dirSign, int speed) {
  int offset = speedToOffset(speed);
  int pulse  = servoConfig[servoId].neutral_us + dirSign * offset;
  return constrain(pulse, PULSE_MIN_US, PULSE_MAX_US);
}

// Mulai/lanjutkan jog. Dipanggil berulang (heartbeat) selama tombol ditahan di UI.
void applyJog(int id, int dirSign, int speed) {
  speed = constrain(speed, 0, 100);
  if (speed <= 0) {
    stopServo(id);
    return;
  }

  servos[id].attach(SERVO_PINS[id]);
  servos[id].writeMicroseconds(computePulse(id, dirSign, speed));

  unsigned long now = millis();
  if (!jogState[id].active) {
    jogState[id].startMs = now;
  }
  jogState[id].active    = true;
  jogState[id].dirSign   = dirSign;
  jogState[id].speed     = speed;
  jogState[id].lastCmdMs = now;
}

// Hentikan servo segera: tulis pulsa netral, tunggu settle, lalu detach.
void stopServo(int id) {
  servos[id].attach(SERVO_PINS[id]);
  servos[id].writeMicroseconds(servoConfig[id].neutral_us);
  delay(STOP_SETTLE_MS);
  servos[id].detach();
  jogState[id].active = false;
}

void stopAllServos() {
  for (int i = 0; i < NUM_SERVOS; i++) stopServo(i);
}

// Dipanggil di setiap iterasi loop() — prioritas tertinggi.
// Menghentikan servo yang jog-nya tidak menerima heartbeat (koneksi putus)
// atau sudah melebihi batas durasi absolut.
void checkJogWatchdog() {
  unsigned long now = millis();
  for (int i = 0; i < NUM_SERVOS; i++) {
    if (!jogState[i].active) continue;

    if (now - jogState[i].lastCmdMs > JOG_WATCHDOG_MS) {
      Serial.printf("[Servo %d] Watchdog: heartbeat hilang → STOP.\n", i);
      stopServo(i);
      continue;
    }

    if (now - jogState[i].startMs > JOG_ABSOLUTE_MAX_MS) {
      Serial.printf("[Servo %d] Watchdog: batas durasi absolut tercapai → STOP.\n", i);
      stopServo(i);
    }
  }
}

// Urutan klik: putar ke arah click_dir (tekan tombol), lalu putar balik
// (arah berlawanan) untuk kembali ke posisi awal, lalu berhenti.
void doClickSequence(int id) {
  ServoConfig &c = servoConfig[id];
  Serial.printf("[Servo %d] Klik: dir=%s speed=%d click=%dms return=%dms\n",
                id, dirSignToStr(c.click_dir), c.click_speed,
                c.click_duration_ms, c.return_duration_ms);

  servos[id].attach(SERVO_PINS[id]);

  // Fase tekan
  servos[id].writeMicroseconds(computePulse(id, c.click_dir, c.click_speed));
  delay(c.click_duration_ms);

  // Fase kembali (arah berlawanan)
  servos[id].writeMicroseconds(computePulse(id, -c.click_dir, c.click_speed));
  delay(c.return_duration_ms);

  // Berhenti
  servos[id].writeMicroseconds(c.neutral_us);
  delay(STOP_SETTLE_MS);
  servos[id].detach();

  jogState[id].active = false;
  Serial.printf("[Servo %d] Klik selesai.\n", id);
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
  StaticJsonDocument<768> doc;

  for (int i = 0; i < NUM_SERVOS; i++) {
    String key = "servo" + String(i);
    doc[key]["id"]          = i;
    doc[key]["name"]        = SERVO_NAMES[i];
    doc[key]["neutral_us"]  = servoConfig[i].neutral_us;
    doc[key]["trim"]        = servoConfig[i].neutral_us - SERVO_NEUTRAL_US_DEFAULT;
    doc[key]["click_dir"]   = dirSignToStr(servoConfig[i].click_dir);
    doc[key]["click_speed"] = servoConfig[i].click_speed;
    doc[key]["click_ms"]    = servoConfig[i].click_duration_ms;
    doc[key]["return_ms"]   = servoConfig[i].return_duration_ms;
  }

  String out;
  serializeJson(doc, out);
  sendJson(200, out);
}

// POST /servo/jog?id=0&dir=CW&speed=20
// Dipanggil berulang (heartbeat) oleh dashboard selama tombol jog ditahan.
// speed<=0 → berhenti (sama seperti /servo/stop).
void handleServoJog() {
  int id = getServoId();
  if (id < 0) {
    sendJson(400, "{\"error\":\"id servo tidak valid (0-2)\"}");
    return;
  }
  if (!server.hasArg("dir") || !server.hasArg("speed")) {
    sendJson(400, "{\"error\":\"parameter dir dan speed diperlukan\"}");
    return;
  }

  bool validDir;
  int dirSign = parseDirSign(server.arg("dir"), validDir);
  if (!validDir) {
    sendJson(400, "{\"error\":\"dir harus CW atau CCW\"}");
    return;
  }

  int speed = constrain(server.arg("speed").toInt(), 0, 100);

  StaticJsonDocument<128> doc;
  doc["ok"]    = true;
  doc["servo"] = id;

  if (speed <= 0) {
    stopServo(id);
    doc["stopped"] = true;
    doc["speed"]   = 0;
  } else {
    applyJog(id, dirSign, speed);
    doc["dir"]      = dirSignToStr(dirSign);
    doc["speed"]    = speed;
    doc["pulse_us"] = computePulse(id, dirSign, speed);
  }

  String out;
  serializeJson(doc, out);
  sendJson(200, out);
}

void handleServoStop() {
  int id = getServoId();
  if (id < 0) {
    sendJson(400, "{\"error\":\"id servo tidak valid (0-2)\"}");
    return;
  }

  stopServo(id);

  StaticJsonDocument<64> doc;
  doc["ok"]    = true;
  doc["servo"] = id;
  String out;
  serializeJson(doc, out);
  sendJson(200, out);
}

void handleServoStopAll() {
  stopAllServos();
  sendJson(200, "{\"ok\":true,\"message\":\"Semua servo dihentikan\"}");
}

void handleServoClick() {
  int id = getServoId();
  if (id < 0) {
    sendJson(400, "{\"error\":\"id servo tidak valid (0-2)\"}");
    return;
  }

  doClickSequence(id);

  StaticJsonDocument<128> doc;
  doc["ok"]    = true;
  doc["servo"] = id;
  doc["name"]  = SERVO_NAMES[id];

  String out;
  serializeJson(doc, out);
  sendJson(200, out);
}

// POST /servo/calibrate?id=0&dir=CW&speed=30&click_ms=300&return_ms=300&trim=0
// Field yang tidak dikirim akan dipertahankan dari nilai tersimpan sebelumnya.
void handleServoCalibrate() {
  int id = getServoId();
  if (id < 0) {
    sendJson(400, "{\"error\":\"id servo tidak valid (0-2)\"}");
    return;
  }

  int dirSign = servoConfig[id].click_dir;
  if (server.hasArg("dir")) {
    bool validDir;
    dirSign = parseDirSign(server.arg("dir"), validDir);
    if (!validDir) {
      sendJson(400, "{\"error\":\"dir harus CW atau CCW\"}");
      return;
    }
  }

  int speed    = server.hasArg("speed")     ? server.arg("speed").toInt()     : servoConfig[id].click_speed;
  int clickMs  = server.hasArg("click_ms")  ? server.arg("click_ms").toInt()  : servoConfig[id].click_duration_ms;
  int returnMs = server.hasArg("return_ms") ? server.arg("return_ms").toInt() : servoConfig[id].return_duration_ms;
  int trim     = server.hasArg("trim")      ? server.arg("trim").toInt()
                                             : (servoConfig[id].neutral_us - SERVO_NEUTRAL_US_DEFAULT);

  speed    = constrain(speed, 0, 100);
  clickMs  = constrain(clickMs,  0, CLICK_MAX_DURATION_MS);
  returnMs = constrain(returnMs, 0, CLICK_MAX_DURATION_MS);
  trim     = constrain(trim, SERVO_TRIM_MIN, SERVO_TRIM_MAX);

  servoConfig[id].click_dir          = dirSign;
  servoConfig[id].click_speed        = speed;
  servoConfig[id].click_duration_ms  = clickMs;
  servoConfig[id].return_duration_ms = returnMs;
  servoConfig[id].neutral_us         = SERVO_NEUTRAL_US_DEFAULT + trim;

  bool saved = saveCalibration();

  StaticJsonDocument<160> doc;
  doc["ok"]          = saved;
  doc["servo"]       = id;
  doc["click_dir"]   = dirSignToStr(dirSign);
  doc["click_speed"] = speed;
  doc["click_ms"]    = clickMs;
  doc["return_ms"]   = returnMs;
  doc["trim"]        = trim;

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

  // Pastikan semua servo diam total saat boot (tulis pulsa netral, lalu detach)
  for (int i = 0; i < NUM_SERVOS; i++) {
    jogState[i].active    = false;
    jogState[i].dirSign   = 1;
    jogState[i].speed     = 0;
    jogState[i].lastCmdMs = 0;
    jogState[i].startMs   = 0;

    servos[i].attach(SERVO_PINS[i]);
    servos[i].writeMicroseconds(servoConfig[i].neutral_us);
    delay(50);
    servos[i].detach();
    Serial.printf("[Boot] Servo %d (%s) → neutral=%dus (diam)\n",
                  i, SERVO_NAMES[i], servoConfig[i].neutral_us);
  }

  // WiFi
  connectWiFi();

  // HTTP Server
  server.on("/health",          HTTP_GET,  handleHealth);
  server.on("/sensor",          HTTP_GET,  handleSensor);
  server.on("/servo/config",    HTTP_GET,  handleServoConfig);
  server.on("/servo/jog",       HTTP_POST, handleServoJog);
  server.on("/servo/stop",      HTTP_POST, handleServoStop);
  server.on("/servo/stop_all",  HTTP_POST, handleServoStopAll);
  server.on("/servo/click",     HTTP_POST, handleServoClick);
  server.on("/servo/calibrate", HTTP_POST, handleServoCalibrate);
  server.on("/relay",           HTTP_POST, handleRelay);
  server.onNotFound(handleNotFound);
  server.begin();

  Serial.println("[Boot] HTTP server berjalan di port 80.");
  Serial.println("[Boot] Siap menerima perintah.\n");
  Serial.printf("  Health     : curl http://%s/health\n", WiFi.localIP().toString().c_str());
  Serial.printf("  Jog        : curl -X POST \"http://%s/servo/jog?id=0&dir=CW&speed=20\"\n", WiFi.localIP().toString().c_str());
  Serial.printf("  Stop       : curl -X POST \"http://%s/servo/stop?id=0\"\n", WiFi.localIP().toString().c_str());
  Serial.printf("  Stop semua : curl -X POST \"http://%s/servo/stop_all\"\n", WiFi.localIP().toString().c_str());
  Serial.printf("  Kalibrasi  : curl -X POST \"http://%s/servo/calibrate?id=0&dir=CW&speed=30&click_ms=300&return_ms=300\"\n\n",
                WiFi.localIP().toString().c_str());
}

// ── loop() ────────────────────────────────────────────────────────────────────

void loop() {
  // 1. Safety watchdog — prioritas tertinggi, jalan di setiap iterasi
  checkJogWatchdog();

  // 2. WiFi: kalau putus, stop SEMUA servo SEKARANG (jangan tunggu watchdog),
  //    lalu coba reconnect tanpa memblok loop() (agar watchdog tetap jalan)
  if (WiFi.status() != WL_CONNECTED) {
    stopAllServos();

    static unsigned long lastReconnectAttempt = 0;
    unsigned long now = millis();
    if (now - lastReconnectAttempt > 3000) {
      Serial.println("[WiFi] Terputus! Mencoba reconnect...");
      WiFi.reconnect();
      lastReconnectAttempt = now;
    }
    return;
  }

  server.handleClient();
}
