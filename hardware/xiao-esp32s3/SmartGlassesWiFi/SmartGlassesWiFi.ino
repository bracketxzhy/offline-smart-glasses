#include <Arduino.h>
#include "ap_secrets.h"
#include <WiFi.h>
#include <WebServer.h>
#include <ESP_I2S.h>
#include <esp_mac.h>
#include "camera_capture.h"

// Existing project-local development AP. Never requires a USB serial monitor.
constexpr char AP_NAME[] = "XIAO-S3-1984";
WiFiServer streamServer(3333);
WebServer http(80);
WiFiClient client;
I2SClass microphone;
SemaphoreHandle_t networkMutex;
volatile bool sessionEnabled=false, cameraEnabled=false, microphoneEnabled=false;
bool microphoneReady=false, wifiReady=false;
uint32_t sequenceNumber=0, sentFrames=0, sentAudioBytes=0, droppedPackets=0;
uint32_t lastStatus=0;
String command;
char deviceMac[18];

struct __attribute__((packed)) PacketHeader {
  char magic[4]; uint8_t version; uint8_t kind; uint16_t headerBytes;
  uint32_t sequence; uint32_t timestampMs; uint32_t payloadBytes; uint32_t crc;
};
static_assert(sizeof(PacketHeader)==24,"SGA1 header changed");

uint32_t crc32(const uint8_t *data,size_t count) {
  uint32_t crc=0xffffffffU;
  for (size_t i=0;i<count;i++) {
    crc^=data[i];
    for (int bit=0;bit<8;bit++) crc=(crc>>1)^(0xedb88320U & (0U-(crc&1U)));
  }
  return ~crc;
}

void stopSession() { sessionEnabled=false; cameraEnabled=false; microphoneEnabled=false; }

bool writeAll(const uint8_t *data,size_t count) {
  size_t offset=0; uint32_t started=millis();
  while (offset<count && millis()-started<2000 && client.connected()) {
    size_t n=client.write(data+offset,count-offset);
    offset+=n;
    if (!n) delay(1);
  }
  return offset==count;
}

bool sendPacket(uint8_t kind,const uint8_t *data,size_t count,bool force=false) {
  if ((!sessionEnabled && !force) || count>524288) return false;
  if (xSemaphoreTake(networkMutex,pdMS_TO_TICKS(500))!=pdTRUE) { droppedPackets++; return false; }
  bool ok=false;
  if (client.connected()) {
    PacketHeader header={{'S','G','A','1'},1,kind,24,sequenceNumber++,millis(),uint32_t(count),crc32(data,count)};
    ok=writeAll(reinterpret_cast<const uint8_t *>(&header),sizeof(header)) && writeAll(data,count);
    if (!ok) { client.stop(); stopSession(); }
  }
  xSemaphoreGive(networkMutex);
  if (!ok) droppedPackets++;
  return ok;
}

String statusJson() {
  String text="{\"protocol\":\"SGA1\",\"version\":1,\"transport\":\"wifi_tcp\",\"mac\":\""+String(deviceMac)+"\"";
  text+=",\"chip\":\"ESP32-S3\",\"ssid\":\""+String(AP_NAME)+"\",\"ip\":\""+WiFi.softAPIP().toString()+"\",\"port\":3333";
  text+=",\"wifi_ready\":"+String(wifiReady?"true":"false")+",\"wifi_clients\":"+String(WiFi.softAPgetStationNum());
  text+=",\"camera_ready\":"+String(CameraModule::ready?"true":"false")+",\"camera_pid\":"+String(CameraModule::pid);
  text+=",\"camera_error\":"+String(CameraModule::error)+",\"autofocus_ready\":"+String(CameraModule::autofocusReady?"true":"false");
  text+=",\"microphone_ready\":"+String(microphoneReady?"true":"false");
  text+=",\"camera_enabled\":"+String(cameraEnabled?"true":"false")+",\"microphone_enabled\":"+String(microphoneEnabled?"true":"false");
  text+=",\"sample_rate\":16000,\"channels\":1,\"format\":\"s16le\",\"camera_fps\":3";
  text+=",\"frames_sent\":"+String(sentFrames)+",\"audio_bytes_sent\":"+String(sentAudioBytes)+",\"dropped_packets\":"+String(droppedPackets);
  text+=",\"free_heap\":"+String(ESP.getFreeHeap())+",\"psram_bytes\":"+String(ESP.getPsramSize())+",\"uptime_ms\":"+String(millis())+"}";
  return text;
}

void sendStatus() {
  String text=statusJson();
  sendPacket(3,reinterpret_cast<const uint8_t *>(text.c_str()),text.length(),true);
}

void captureCamera(void *) {
  TickType_t previous=xTaskGetTickCount();
  while (true) {
    if (sessionEnabled && cameraEnabled && CameraModule::ready) {
      camera_fb_t *frame=esp_camera_fb_get();
      if (frame) {
        if (frame->format==PIXFORMAT_JPEG && sendPacket(1,frame->buf,frame->len)) sentFrames++;
        esp_camera_fb_return(frame);
      }
    }
    vTaskDelayUntil(&previous,pdMS_TO_TICKS(333));
  }
}

void captureMicrophone(void *) {
  int16_t samples[1600];
  while (true) {
    if (!microphoneReady) { delay(100); continue; }
    size_t bytes=microphone.readBytes(reinterpret_cast<char *>(samples),sizeof(samples));
    if (bytes && sessionEnabled && microphoneEnabled && sendPacket(2,reinterpret_cast<uint8_t *>(samples),bytes)) sentAudioBytes+=bytes;
    if (!bytes) delay(2);
  }
}

void setup() {
  Serial.begin(115200); delay(300);
  uint8_t mac[6]; esp_read_mac(mac,ESP_MAC_WIFI_STA);
  snprintf(deviceMac,sizeof(deviceMac),"%02x:%02x:%02x:%02x:%02x:%02x",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
  networkMutex=xSemaphoreCreateMutex();
  CameraModule::initialize();
  microphone.setPinsPdmRx(42,41);
  microphoneReady=microphone.begin(I2S_MODE_PDM_RX,16000,I2S_DATA_BIT_WIDTH_16BIT,I2S_SLOT_MODE_MONO);
  microphone.setTimeout(500);
  WiFi.mode(WIFI_AP);
  wifiReady=WiFi.softAP(AP_NAME,AP_PASSWORD,6,false,1);
  WiFi.setSleep(false);
  if (!wifiReady) { Serial.println("ERROR: WIFI_AP_START_FAILED"); return; }
  streamServer.begin();
  http.on("/api/status",HTTP_GET,[](){ http.sendHeader("Cache-Control","no-store"); http.send(200,"application/json",statusJson()); });
  http.on("/",HTTP_GET,[](){ http.send(200,"text/html","<h1>XIAO wireless image/audio</h1><p>SGA1 TCP port 3333</p><a href='/api/status'>Status</a>"); });
  http.begin();
  xTaskCreatePinnedToCore(captureMicrophone,"microphone",8192,nullptr,3,nullptr,0);
  xTaskCreatePinnedToCore(captureCamera,"camera",6144,nullptr,1,nullptr,1);
  Serial.println(statusJson());
}

void loop() {
  if (!wifiReady) { delay(100); return; }
  http.handleClient();
  WiFiClient incoming=streamServer.accept();
  if (incoming) {
    if (xSemaphoreTake(networkMutex,pdMS_TO_TICKS(500))==pdTRUE) {
      if (client.connected()) incoming.stop();
      else {
        stopSession(); client=incoming; client.setNoDelay(true);
        client.setConnectionTimeout(1500); command="";
      }
      xSemaphoreGive(networkMutex);
    } else incoming.stop();
  }
  bool connected=false;
  String complete;
  if (xSemaphoreTake(networkMutex,pdMS_TO_TICKS(50))==pdTRUE) {
    connected=client.connected() && WiFi.softAPgetStationNum()>0;
    if (!connected) { stopSession(); client.stop(); }
    else {
      while (client.available()) {
        char value=client.read();
        if (value=='\n') { complete=command; command=""; break; }
        if (command.length()<32) command+=value;
        else { client.stop(); stopSession(); break; }
      }
    }
    xSemaphoreGive(networkMutex);
  }
  if (complete.length()) {
    complete.trim();
    if (complete=="START") sessionEnabled=true;
    else if (complete=="STOP") stopSession();
    else if (complete=="CAM_ON") cameraEnabled=true;
    else if (complete=="CAM_OFF") cameraEnabled=false;
    else if (complete=="MIC_ON") microphoneEnabled=true;
    else if (complete=="MIC_OFF") microphoneEnabled=false;
    sendStatus(); lastStatus=millis();
  }
  if (connected && millis()-lastStatus>=2000) { lastStatus=millis(); sendStatus(); }
  delay(2);
}
