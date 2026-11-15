#include <Arduino.h>
#include <ESP_I2S.h>
#include <WiFi.h>
#include <esp_mac.h>
#include "camera_capture.h"

// SGA1 v1: little-endian 24-byte header + payload. CRC32 is the zlib polynomial.
struct __attribute__((packed)) PacketHeader {
  char magic[4]; uint8_t version; uint8_t kind; uint16_t headerBytes;
  uint32_t sequence; uint32_t timestampMs; uint32_t payloadBytes; uint32_t crc;
};
static_assert(sizeof(PacketHeader)==24,"Protocol header size changed");
I2SClass microphone;
SemaphoreHandle_t serialMutex;
volatile bool sessionEnabled=false, cameraEnabled=false, microphoneEnabled=false;
bool microphoneReady=false;
uint32_t sequenceNumber=0, sentFrames=0, sentAudioBytes=0, droppedPackets=0;
uint32_t lastStatus=0;
String command;

uint32_t crc32(const uint8_t *data,size_t count) {
  uint32_t crc=0xffffffffU;
  for (size_t i=0;i<count;i++) {
    crc^=data[i];
    for (int bit=0;bit<8;bit++) crc=(crc>>1)^(0xedb88320U & (0U-(crc&1U)));
  }
  return ~crc;
}

bool writeAll(const uint8_t *data,size_t count) {
  size_t offset=0; uint32_t started=millis();
  while (offset<count && millis()-started<1500) {
    size_t n=Serial.write(data+offset,count-offset);
    offset+=n;
    if (!n) delay(1);
  }
  return offset==count;
}

bool sendPacket(uint8_t kind,const uint8_t *data,size_t count,bool force=false) {
  if ((!sessionEnabled && !force) || count>524288) return false;
  if (xSemaphoreTake(serialMutex,pdMS_TO_TICKS(500))!=pdTRUE) { droppedPackets++; return false; }
  PacketHeader header={{'S','G','A','1'},1,kind,24,sequenceNumber++,millis(),uint32_t(count),crc32(data,count)};
  bool ok=writeAll(reinterpret_cast<const uint8_t *>(&header),sizeof(header)) && writeAll(data,count);
  xSemaphoreGive(serialMutex);
  if (!ok) droppedPackets++;
  return ok;
}

void sendStatus() {
  uint8_t mac[6]; esp_read_mac(mac,ESP_MAC_WIFI_STA);
  char macText[18]; snprintf(macText,sizeof(macText),"%02x:%02x:%02x:%02x:%02x:%02x",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
  String text="{\"protocol\":\"SGA1\",\"version\":1,\"mac\":\""+String(macText)+"\"";
  text+=",\"camera_ready\":"+String(CameraModule::ready?"true":"false");
  text+=",\"camera_pid\":"+String(CameraModule::pid);
  text+=",\"camera_error\":"+String(CameraModule::error);
  text+=",\"autofocus_ready\":"+String(CameraModule::autofocusReady?"true":"false");
  text+=",\"microphone_ready\":"+String(microphoneReady?"true":"false");
  text+=",\"camera_enabled\":"+String(cameraEnabled?"true":"false");
  text+=",\"microphone_enabled\":"+String(microphoneEnabled?"true":"false");
  text+=",\"sample_rate\":16000,\"channels\":1,\"format\":\"s16le\",\"camera_fps\":3";
  text+=",\"frames_sent\":"+String(sentFrames)+",\"audio_bytes_sent\":"+String(sentAudioBytes);
  text+=",\"dropped_packets\":"+String(droppedPackets)+",\"free_heap\":"+String(ESP.getFreeHeap());
  text+=",\"psram_bytes\":"+String(ESP.getPsramSize())+",\"uptime_ms\":"+String(millis())+"}";
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
  Serial.begin(921600);
  delay(300);
  serialMutex=xSemaphoreCreateMutex();
  // Wi-Fi is not needed for the wired capture path.
  WiFi.mode(WIFI_OFF);
  CameraModule::initialize();
  microphone.setPinsPdmRx(42,41);
  microphoneReady=microphone.begin(I2S_MODE_PDM_RX,16000,I2S_DATA_BIT_WIDTH_16BIT,I2S_SLOT_MODE_MONO);
  microphone.setTimeout(500);
  xTaskCreatePinnedToCore(captureMicrophone,"microphone",8192,nullptr,3,nullptr,0);
  xTaskCreatePinnedToCore(captureCamera,"camera",6144,nullptr,1,nullptr,1);
}

void loop() {
  while (Serial.available()) {
    char value=Serial.read();
    if (value=='\n') {
      command.trim();
      if (command=="START") sessionEnabled=true;
      else if (command=="STOP") { sessionEnabled=false; cameraEnabled=false; microphoneEnabled=false; }
      else if (command=="CAM_ON") cameraEnabled=true;
      else if (command=="CAM_OFF") cameraEnabled=false;
      else if (command=="MIC_ON") microphoneEnabled=true;
      else if (command=="MIC_OFF") microphoneEnabled=false;
      sendStatus(); command="";
    } else if (command.length()<32) command+=value;
    else command="";
  }
  if (sessionEnabled && millis()-lastStatus>=2000) { lastStatus=millis(); sendStatus(); }
  delay(2);
}
