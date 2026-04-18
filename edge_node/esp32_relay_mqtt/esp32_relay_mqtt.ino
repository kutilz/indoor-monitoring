/**
 * ESP32 MQTT Relay Controller
 * Board  : ESP32 Dev Module (bukan ESP32-CAM)
 * Fungsi : Menerima perintah dari server Python via MQTT
 *          dan men-trigger pin GPIO yang terhubung ke Relay 4-Channel.
 *
 * Topik MQTT yang di-subscribe: classroom/relay
 * Format payload (JSON): {"relay": 1, "state": "ON"}
 *
 * Wiring Relay:
 *   IN1 → GPIO 12 → AC / Pendingin
 *   IN2 → GPIO 13 → Lampu Zona Depan
 *   IN3 → GPIO 14 → Lampu Zona Belakang
 *   IN4 → GPIO 15 → Cadangan
 *   VCC → 5V
 *   GND → GND
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ── Konfigurasi WiFi ─────────────────────────────────────────────────────────
#define WIFI_SSID     "NAMA_WIFI_KAMU"
#define WIFI_PASSWORD "PASSWORD_WIFI"

// ── Konfigurasi MQTT ─────────────────────────────────────────────────────────
// Isi dengan IP komputer yang menjalankan Mosquitto broker.
// Jika broker di komputer yang sama dengan server Python, IP ini adalah
// IP komputer kamu di jaringan WiFi.
#define MQTT_SERVER   "192.168.1.50"
#define MQTT_PORT     1883
#define MQTT_CLIENT_ID "esp32_relay_controller"
#define MQTT_TOPIC    "classroom/relay"

// ── Pin Relay ─────────────────────────────────────────────────────────────────
// Modul relay aktif-LOW: LOW = relay ON, HIGH = relay OFF
#define RELAY_1_PIN   12   // AC / Pendingin
#define RELAY_2_PIN   13   // Lampu Zona Depan
#define RELAY_3_PIN   14   // Lampu Zona Belakang
#define RELAY_4_PIN   15   // Cadangan

const int RELAY_PINS[4] = {RELAY_1_PIN, RELAY_2_PIN, RELAY_3_PIN, RELAY_4_PIN};
const char* RELAY_NAMES[4] = {"AC", "Lampu Depan", "Lampu Belakang", "Cadangan"};

// ── Objects ───────────────────────────────────────────────────────────────────
WiFiClient   espClient;
PubSubClient mqttClient(espClient);

// ── Inisialisasi Pin Relay ────────────────────────────────────────────────────
void initRelays() {
  for (int i = 0; i < 4; i++) {
    pinMode(RELAY_PINS[i], OUTPUT);
    digitalWrite(RELAY_PINS[i], HIGH);  // Relay OFF saat boot (aktif LOW)
  }
  Serial.println("[Relay] Semua relay diinisialisasi (OFF).");
}

// ── Koneksi WiFi ──────────────────────────────────────────────────────────────
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
  Serial.println("\n[WiFi] Terhubung!");
  Serial.print("[WiFi] IP: ");
  Serial.println(WiFi.localIP());
}

// ── Callback MQTT ─────────────────────────────────────────────────────────────
void onMqttMessage(char *topic, byte *payload, unsigned int length) {
  // Parse JSON
  StaticJsonDocument<128> doc;
  DeserializationError err = deserializeJson(
    doc, (char *)payload, length
  );

  if (err) {
    Serial.printf("[MQTT] JSON parse error: %s\n", err.c_str());
    return;
  }

  int    relayNum = doc["relay"] | 0;
  String stateStr = doc["state"] | "OFF";

  // Validasi nomor relay
  if (relayNum < 1 || relayNum > 4) {
    Serial.printf("[MQTT] Nomor relay tidak valid: %d\n", relayNum);
    return;
  }

  int pin  = RELAY_PINS[relayNum - 1];
  bool on  = (stateStr == "ON");

  // Aktif LOW: ON = LOW, OFF = HIGH
  digitalWrite(pin, on ? LOW : HIGH);

  Serial.printf("[Relay] %s → %s (GPIO %d)\n",
                RELAY_NAMES[relayNum - 1],
                stateStr.c_str(),
                pin);
}

// ── Koneksi MQTT ──────────────────────────────────────────────────────────────
void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.printf("[MQTT] Menghubungkan ke broker %s:%d...\n",
                  MQTT_SERVER, MQTT_PORT);

    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      Serial.println("[MQTT] Terhubung!");
      mqttClient.subscribe(MQTT_TOPIC);
      Serial.printf("[MQTT] Subscribe ke topik: %s\n", MQTT_TOPIC);

      // Kirim pesan status online
      mqttClient.publish("classroom/status",
                         "{\"device\":\"relay\",\"status\":\"online\"}");
    } else {
      Serial.printf("[MQTT] Gagal (rc=%d). Coba lagi dalam 5s...\n",
                    mqttClient.state());
      delay(5000);
    }
  }
}

// ── setup() ──────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial.println("\n[Boot] ESP32 Relay Controller starting...");

  initRelays();
  connectWiFi();

  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setCallback(onMqttMessage);
  mqttClient.setBufferSize(256);

  connectMQTT();

  Serial.println("\n[Boot] Siap menerima perintah relay via MQTT.");
}

// ── loop() ────────────────────────────────────────────────────────────────────
void loop() {
  // Cek koneksi WiFi
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Terputus! Reconnecting...");
    WiFi.reconnect();
    delay(3000);
    return;
  }

  // Cek koneksi MQTT
  if (!mqttClient.connected()) {
    connectMQTT();
  }

  // Proses pesan MQTT yang masuk
  mqttClient.loop();
}
