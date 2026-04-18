/**
 * ESP32-CAM HTTP MJPEG Streaming Server
 * Board  : AI-Thinker ESP32-CAM
 * Kamera : OV2640
 *
 * Setelah upload:
 * 1. Buka Serial Monitor @ 115200 baud
 * 2. Catat IP yang ditampilkan
 * 3. Masukkan IP tersebut ke config.py (ESP32_STREAM_URL)
 * 4. Akses http://<IP>/stream di browser untuk preview
 */

#include "esp_camera.h"
#include "esp_http_server.h"
#include <WiFi.h>

// ── Konfigurasi WiFi ─────────────────────────────────────────────────────────
// Ganti dengan SSID dan password jaringan kampus / hotspot kamu.
#define WIFI_SSID     "NAMA_WIFI_KAMU"
#define WIFI_PASSWORD "PASSWORD_WIFI"

// ── Pin Kamera AI-Thinker ESP32-CAM ─────────────────────────────────────────
#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM    0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27
#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM      5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22

// ── HTTP Server handle ────────────────────────────────────────────────────────
httpd_handle_t stream_httpd = NULL;
httpd_handle_t camera_httpd = NULL;

// ── Inisialisasi Kamera ───────────────────────────────────────────────────────
bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Resolusi & kualitas
  // Untuk YOLOv8 yang berjalan di PC, SVGA (800x600) sudah cukup.
  // Turunkan ke VGA (640x480) jika koneksi WiFi lambat.
  if (psramFound()) {
    config.frame_size   = FRAMESIZE_SVGA;   // 800x600
    config.jpeg_quality = 12;               // 0=terbaik, 63=terburuk
    config.fb_count     = 2;
  } else {
    config.frame_size   = FRAMESIZE_VGA;    // 640x480
    config.jpeg_quality = 20;
    config.fb_count     = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[Camera] Init gagal: 0x%x\n", err);
    return false;
  }

  // Pengaturan sensor tambahan (opsional)
  sensor_t *s = esp_camera_sensor_get();
  s->set_brightness(s, 0);
  s->set_contrast(s, 0);
  s->set_saturation(s, 0);
  s->set_whitebal(s, 1);
  s->set_awb_gain(s, 1);
  s->set_exposure_ctrl(s, 1);
  s->set_aec2(s, 0);
  s->set_gain_ctrl(s, 1);

  Serial.println("[Camera] Kamera berhasil diinisialisasi.");
  return true;
}

// ── Handler: MJPEG Stream (/stream) ──────────────────────────────────────────
#define PART_BOUNDARY "frame"
static const char *STREAM_CONTENT_TYPE =
  "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char *STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char *STREAM_PART =
  "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

esp_err_t streamHandler(httpd_req_t *req) {
  camera_fb_t *fb = NULL;
  esp_err_t res = ESP_OK;

  res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;

  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(req, "Cache-Control", "no-cache");

  char part_buf[64];

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[Stream] Gagal mengambil frame.");
      res = ESP_FAIL;
      break;
    }

    // Kirim boundary
    res = httpd_resp_send_chunk(
      req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY)
    );

    // Kirim header part
    size_t hlen = snprintf(part_buf, sizeof(part_buf),
                           STREAM_PART, fb->len);
    res = httpd_resp_send_chunk(req, part_buf, hlen);

    // Kirim data JPEG
    res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);

    esp_camera_fb_return(fb);
    fb = NULL;

    if (res != ESP_OK) break;
  }

  return res;
}

// ── Handler: Halaman Utama (/) ────────────────────────────────────────────────
esp_err_t indexHandler(httpd_req_t *req) {
  httpd_resp_set_type(req, "text/html");
  String html = R"rawhtml(
<!DOCTYPE html><html>
<head><meta charset="UTF-8">
<title>ESP32-CAM Stream</title>
<style>body{background:#111;color:#eee;font-family:sans-serif;text-align:center;padding:20px}
img{max-width:100%;border:2px solid #444;border-radius:8px}</style>
</head>
<body>
<h2>ESP32-CAM Live Stream</h2>
<img src="/stream" alt="Stream" />
<p style="color:#888">Gunakan <code>http://IP_INI/stream</code> di Python script.</p>
</body></html>
)rawhtml";
  return httpd_resp_sendstr(req, html.c_str());
}

// ── Jalankan HTTP Server ──────────────────────────────────────────────────────
void startCameraServer() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 80;

  // Server utama (halaman index)
  httpd_uri_t index_uri = {
    .uri      = "/",
    .method   = HTTP_GET,
    .handler  = indexHandler,
    .user_ctx = NULL
  };

  // Stream server (port terpisah agar tidak blocking)
  httpd_config_t stream_cfg = HTTPD_DEFAULT_CONFIG();
  stream_cfg.server_port = 81;
  stream_cfg.ctrl_port   = 32769;

  httpd_uri_t stream_uri = {
    .uri      = "/stream",
    .method   = HTTP_GET,
    .handler  = streamHandler,
    .user_ctx = NULL
  };

  if (httpd_start(&camera_httpd, &cfg) == ESP_OK) {
    httpd_register_uri_handler(camera_httpd, &index_uri);
    Serial.println("[Server] HTTP server aktif di port 80.");
  }

  if (httpd_start(&stream_httpd, &stream_cfg) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    Serial.println("[Server] Stream server aktif di port 81.");
  }
}

// ── setup() ──────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  Serial.println("\n[Boot] ESP32-CAM starting...");

  // Inisialisasi kamera
  if (!initCamera()) {
    Serial.println("[Boot] FATAL: Kamera gagal. Restart...");
    ESP.restart();
  }

  // Koneksi WiFi
  Serial.printf("[WiFi] Menghubungkan ke: %s\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  WiFi.setSleep(false);

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
  Serial.print("[WiFi] IP Address: ");
  Serial.println(WiFi.localIP());
  Serial.println();
  Serial.println("==============================================");
  Serial.print("  Stream URL: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":81/stream");
  Serial.println("  Masukkan URL ini ke config.py (ESP32_STREAM_URL)");
  Serial.println("==============================================\n");

  startCameraServer();
}

// ── loop() ────────────────────────────────────────────────────────────────────
void loop() {
  // ESP32 HTTP server berjalan di background via FreeRTOS tasks.
  // loop() hanya mencetak status WiFi setiap 30 detik.
  delay(30000);
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Koneksi terputus! Reconnecting...");
    WiFi.reconnect();
  }
}
