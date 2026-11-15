#include <Arduino.h>
#include "ap_secrets.h"
#include <WiFi.h>
#include <WebServer.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <esp_camera.h>
#include <ESP32_OV5640_AF.h>

// Local diagnostic network; change this test password before wider use.
constexpr char DEVICE_NAME[] = "XIAO-S3-1984";
constexpr char SERVICE_UUID[] = "4fafc201-1fb5-459e-8fcc-c5c9c331914b";
constexpr char CHARACTERISTIC_UUID[] = "beb5483e-36e1-4688-b7f5-ea07361b26a8";

WebServer http(80);
bool wifiReady = false;
bool bleReady = false;
volatile bool bleConnected = false;
volatile bool restartAdvertising = false;
unsigned long lastStatus = 0;
bool cameraInitialized = false;
esp_err_t cameraError = ESP_ERR_INVALID_STATE;
uint16_t cameraPid = 0;
const char *cameraModel = "unknown";
unsigned long cameraFrames = 0;
size_t lastFrameBytes = 0;
String serialCommand;
OV5640 autofocus;
bool cameraAutofocusReady = false;
esp_err_t cameraAutofocusError = ESP_ERR_INVALID_STATE;

void initializeCamera() {
  if (!psramFound()) {
    cameraError = ESP_ERR_NO_MEM;
    Serial.println("ERROR: CAMERA_REQUIRES_PSRAM");
    return;
  }
  // Official CAMERA_MODEL_XIAO_ESP32S3 pin mapping.
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = 15;
  config.pin_d1 = 17;
  config.pin_d2 = 18;
  config.pin_d3 = 16;
  config.pin_d4 = 14;
  config.pin_d5 = 12;
  config.pin_d6 = 11;
  config.pin_d7 = 48;
  config.pin_xclk = 10;
  config.pin_pclk = 13;
  config.pin_vsync = 38;
  config.pin_href = 47;
  config.pin_sccb_sda = 40;
  config.pin_sccb_scl = 39;
  config.pin_pwdn = -1;
  config.pin_reset = -1;
  config.xclk_freq_hz = 20000000;
  // Allocate for the resolution needed by OV5640's initial focus evaluation.
  config.frame_size = FRAMESIZE_SXGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count = 2;
  cameraError = esp_camera_init(&config);
  if (cameraError != ESP_OK) {
    Serial.printf("ERROR: CAMERA_INIT_FAILED 0x%x\n", cameraError);
    return;
  }
  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor == nullptr) {
    cameraError = ESP_ERR_INVALID_STATE;
    return;
  }
  cameraPid = sensor->id.PID;
  switch (cameraPid) {
    case OV2640_PID: cameraModel = "OV2640"; break;
    case OV3660_PID: cameraModel = "OV3660"; break;
    case OV5640_PID: cameraModel = "OV5640"; break;
    default: break;
  }
  cameraInitialized = true;
  if (cameraPid == OV5640_PID) {
    if (autofocus.start(sensor) && autofocus.focusInit() == 0 &&
        autofocus.autoFocusMode() == 0) {
      cameraAutofocusReady = true;
      cameraAutofocusError = ESP_OK;
      const unsigned long focusStart = millis();
      while (millis() - focusStart < 8000) {
        if (autofocus.getFWStatus() == FW_STATUS_S_FOCUSED) {
          break;
        }
        delay(100);
      }
    } else {
      cameraAutofocusError = ESP_FAIL;
      Serial.println("ERROR: CAMERA_AUTOFOCUS_INIT_FAILED");
    }
  } else {
    cameraAutofocusError = ESP_ERR_NOT_SUPPORTED;
  }
  if (sensor->set_framesize(sensor, FRAMESIZE_VGA) != 0) {
    cameraError = ESP_FAIL;
    Serial.println("ERROR: CAMERA_VGA_CONFIG_FAILED");
  }
  // Discard queued frames from the initial, higher-resolution focus stage.
  for (int index = 0; index < 3; index++) {
    camera_fb_t *frame = esp_camera_fb_get();
    if (frame != nullptr) {
      esp_camera_fb_return(frame);
    }
  }
  Serial.printf("CAMERA_READY model=%s pid=0x%x\n", cameraModel, cameraPid);
}

camera_fb_t *captureFrame() {
  if (!cameraInitialized) {
    return nullptr;
  }
  camera_fb_t *frame = esp_camera_fb_get();
  if (frame == nullptr) {
    cameraError = ESP_FAIL;
    return nullptr;
  }
  if (frame->format != PIXFORMAT_JPEG) {
    esp_camera_fb_return(frame);
    cameraError = ESP_ERR_NOT_SUPPORTED;
    return nullptr;
  }
  cameraError = ESP_OK;
  cameraFrames++;
  lastFrameBytes = frame->len;
  return frame;
}

void captureToSerial() {
  camera_fb_t *frame = captureFrame();
  if (frame == nullptr) {
    Serial.printf("ERROR: CAMERA_CAPTURE_FAILED 0x%x\n", cameraError);
    return;
  }
  Serial.printf("JPEG %u\n", unsigned(frame->len));
  const size_t written = Serial.write(frame->buf, frame->len);
  Serial.print("\nJPEG_END\n");
  if (written != frame->len) {
    cameraError = ESP_ERR_TIMEOUT;
  }
  esp_camera_fb_return(frame);
}

String statusJson() {
  String result = "{\"device\":\"";
  result += DEVICE_NAME;
  result += "\",\"chip\":\"ESP32-S3\",\"wifi_mode\":\"AP\",\"wifi_ready\":";
  result += wifiReady ? "true" : "false";
  result += ",\"ip\":\"" + WiFi.softAPIP().toString();
  result += "\",\"ap_mac\":\"" + WiFi.softAPmacAddress();
  result += "\",\"wifi_clients\":" + String(WiFi.softAPgetStationNum());
  result += ",\"ble_ready\":";
  result += bleReady ? "true" : "false";
  result += ",\"ble_connected\":";
  result += bleConnected ? "true" : "false";
  result += ",\"uptime_ms\":" + String(millis());
  result += ",\"free_heap\":" + String(ESP.getFreeHeap());
  result += ",\"psram_bytes\":" + String(ESP.getPsramSize());
  result += ",\"camera_initialized\":";
  result += cameraInitialized ? "true" : "false";
  result += ",\"camera_model\":\"" + String(cameraModel);
  result += "\",\"camera_pid\":" + String(cameraPid);
  result += ",\"camera_error\":" + String(cameraError);
  result += ",\"camera_autofocus_ready\":";
  result += cameraAutofocusReady ? "true" : "false";
  result += ",\"camera_autofocus_error\":" + String(cameraAutofocusError);
  const uint8_t focusStatus = cameraAutofocusReady ? autofocus.getFWStatus() : 255;
  result += ",\"camera_focus_status\":" + String(focusStatus);
  result += ",\"camera_focused\":";
  result += focusStatus == FW_STATUS_S_FOCUSED ? "true" : "false";
  result += ",\"camera_frames\":" + String(cameraFrames);
  result += ",\"last_frame_bytes\":" + String(lastFrameBytes) + "}";
  return result;
}

class ConnectionCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *) override {
    bleConnected = true;
  }

  void onDisconnect(BLEServer *) override {
    bleConnected = false;
    restartAdvertising = true;
  }
};

void setup() {
  Serial.begin(115200);
  delay(500);  // Do not wait for a host serial monitor.
  Serial.println("XIAO_WIRELESS_CHECK_START");
  initializeCamera();

  WiFi.mode(WIFI_AP);
  wifiReady = WiFi.softAP(DEVICE_NAME, AP_PASSWORD, 6, false, 2);
  if (!wifiReady) {
    Serial.println("ERROR: WIFI_AP_START_FAILED");
    return;
  }

  BLEDevice::init(DEVICE_NAME);
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ConnectionCallbacks());
  BLEService *service = server->createService(SERVICE_UUID);
  BLECharacteristic *characteristic = service->createCharacteristic(
      CHARACTERISTIC_UUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE);
  characteristic->setValue("XIAO BLE ready");
  service->start();
  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->setScanResponse(true);
  BLEDevice::startAdvertising();
  bleReady = true;

  http.on("/", HTTP_GET, []() {
    http.send(200, "text/html; charset=utf-8",
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>XIAO Camera Check</title><body>"
        "<h1>XIAO ESP32-S3</h1><p>Wi-Fi hotspot and BLE are running.</p>"
        "<p><a href='/api/status'>Device status</a></p>"
        "<p>BLE name: XIAO-S3-1984. Use a BLE GATT client to read or write "
        "characteristic beb5483e-36e1-4688-b7f5-ea07361b26a8.</p>"
        "<p><a href='/capture.jpg'>Take a photo (640 x 480 JPEG)</a></p></body></html>");
  });
  http.on("/capture.jpg", HTTP_GET, []() {
    camera_fb_t *frame = captureFrame();
    if (frame == nullptr) {
      http.send(503, "application/json", "{\"error\":\"camera_capture_failed\"}");
      return;
    }
    http.sendHeader("Cache-Control", "no-store");
    http.sendHeader("Content-Disposition", "inline; filename=capture.jpg");
    http.setContentLength(frame->len);
    http.send(200, "image/jpeg", "");
    http.sendContent(reinterpret_cast<const char *>(frame->buf), frame->len);
    esp_camera_fb_return(frame);
  });
  http.on("/api/status", HTTP_GET, []() {
    http.sendHeader("Cache-Control", "no-store");
    http.send(200, "application/json", statusJson());
  });
  http.onNotFound([]() { http.send(404, "text/plain", "Not found"); });
  http.begin();
  Serial.println(statusJson());
}

void loop() {
  if (wifiReady && bleReady) {
    http.handleClient();
  }
  if (restartAdvertising) {
    restartAdvertising = false;
    BLEDevice::startAdvertising();
  }
  while (Serial.available()) {
    char value = Serial.read();
    if (value == '\n') {
      serialCommand.trim();
      if (serialCommand == "capture") {
        captureToSerial();
      } else if (serialCommand == "status") {
        Serial.println(statusJson());
      } else {
        Serial.println("ERROR: UNKNOWN_COMMAND");
      }
      serialCommand = "";
    } else if (serialCommand.length() < 32) {
      serialCommand += value;
    } else {
      serialCommand = "";
      Serial.println("ERROR: COMMAND_TOO_LONG");
    }
  }
  if (millis() - lastStatus >= 10000) {
    lastStatus = millis();
    Serial.println(statusJson());
  }
  delay(2);
}
