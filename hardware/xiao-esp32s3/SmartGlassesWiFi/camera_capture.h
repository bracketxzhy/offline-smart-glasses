#pragma once
#include <esp_camera.h>
#include <ESP32_OV5640_AF.h>

namespace CameraModule {
bool ready = false;
bool autofocusReady = false;
esp_err_t error = ESP_ERR_INVALID_STATE;
uint16_t pid = 0;
OV5640 autofocus;

void initialize() {
  if (!psramFound()) { error = ESP_ERR_NO_MEM; return; }
  camera_config_t c = {};
  c.ledc_channel=LEDC_CHANNEL_0; c.ledc_timer=LEDC_TIMER_0;
  c.pin_d0=15; c.pin_d1=17; c.pin_d2=18; c.pin_d3=16;
  c.pin_d4=14; c.pin_d5=12; c.pin_d6=11; c.pin_d7=48;
  c.pin_xclk=10; c.pin_pclk=13; c.pin_vsync=38; c.pin_href=47;
  c.pin_sccb_sda=40; c.pin_sccb_scl=39;
  c.pin_pwdn=-1; c.pin_reset=-1; c.xclk_freq_hz=20000000;
  c.frame_size=FRAMESIZE_SXGA; c.pixel_format=PIXFORMAT_JPEG;
  c.grab_mode=CAMERA_GRAB_LATEST; c.fb_location=CAMERA_FB_IN_PSRAM;
  c.jpeg_quality=12; c.fb_count=2;
  error=esp_camera_init(&c);
  if (error!=ESP_OK) return;
  sensor_t *sensor=esp_camera_sensor_get();
  if (!sensor) { error=ESP_ERR_INVALID_STATE; return; }
  pid=sensor->id.PID;
  if (pid==OV5640_PID && autofocus.start(sensor) &&
      autofocus.focusInit()==0 && autofocus.autoFocusMode()==0) {
    autofocusReady=true;
    const uint32_t start=millis();
    while (millis()-start<8000 && autofocus.getFWStatus()!=FW_STATUS_S_FOCUSED) delay(100);
  }
  if (sensor->set_framesize(sensor,FRAMESIZE_VGA)!=0) { error=ESP_FAIL; return; }
  for (int i=0;i<3;i++) {
    camera_fb_t *frame=esp_camera_fb_get();
    if (frame) esp_camera_fb_return(frame);
  }
  ready=true;
}
}
