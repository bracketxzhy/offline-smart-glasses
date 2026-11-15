"""XIAO native USB camera/audio transport. No network and no sensor fallback."""
import json
import struct
import threading
import time
import zlib

from .core import require_fresh


class PacketParser:
    HEADER = struct.Struct("<4sBBHIIII")

    def __init__(self):
        self.buffer = bytearray()
        self.bad_packets = 0

    def feed(self, data):
        self.buffer.extend(data)
        packets = []
        while len(self.buffer) >= self.HEADER.size:
            offset = self.buffer.find(b"SGA1")
            if offset < 0:
                del self.buffer[:-3]
                break
            if offset:
                del self.buffer[:offset]
            if len(self.buffer) < 24:
                break
            magic, version, kind, header_size, sequence, device_ms, size, crc = self.HEADER.unpack_from(self.buffer)
            if version != 1 or kind not in {1,2,3} or header_size != 24 or size > 524288:
                self.bad_packets += 1
                del self.buffer[:4]
                continue
            if len(self.buffer) < 24 + size:
                break
            payload = bytes(self.buffer[24:24+size])
            if zlib.crc32(payload) != crc:
                self.bad_packets += 1
                del self.buffer[:1]
                continue
            del self.buffer[:24+size]
            packets.append({"kind":kind,"sequence":sequence,"device_ms":device_ms,"payload":payload})
        return packets


class USBTransport:
    def __init__(self, config):
        self.config = config
        self.lifecycle_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.serial = None
        self.camera_enabled = False
        self.audio_enabled = False
        self.audio_callback = None
        self.frame, self.frame_time = None, 0.
        self.device = None
        self.error = None
        self.port_name = None
        self.parser = PacketParser()
        self.frames_received = 0
        self.audio_samples_received = 0

    def _choose_port(self):
        from serial.tools import list_ports
        ports = list(list_ports.comports())
        requested = self.config["port"]
        candidates = [p for p in ports if (requested == "auto" or p.device == requested) and p.vid == self.config["vid"] and p.pid == self.config["pid"] and (p.serial_number or "").lower() == self.config["expected_mac"].lower()]
        if len(candidates) != 1:
            raise ValueError("未找到唯一匹配的 XIAO USB 设备，请检查连接、串口编号和设备标识")
        return candidates[0].device

    def _command(self, text):
        with self.write_lock:
            self.serial.write((text+"\n").encode("ascii"))

    def _ensure_started(self):
        import serial
        if self.thread and self.thread.is_alive():
            return
        if self.serial is not None:
            self.serial.close()
        self.port_name = self._choose_port()
        connection = serial.Serial()
        connection.port, connection.baudrate = self.port_name, 921600
        connection.timeout, connection.write_timeout = .1, 2
        connection.dtr, connection.rts = False, False
        connection.open()
        connection.reset_input_buffer()
        self.serial, self.error, self.device = connection, None, None
        self.parser = PacketParser()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._read, args=(connection,), daemon=True, name="xiao-usb")
        self.thread.start()
        self._command("START")

    def _read(self, connection):
        import cv2
        import numpy as np
        handshake_started = time.monotonic()
        try:
            while not self.stop_event.is_set():
                data = connection.read(min(65536, max(1, connection.in_waiting)))
                if not data:
                    if self.device is None and time.monotonic()-handshake_started > 20:
                        raise ValueError("未收到 SGA1 固件握手，请检查板卡固件与串口")
                    continue
                for packet in self.parser.feed(data):
                    now = time.monotonic()
                    if packet["kind"] == 3:
                        device = json.loads(packet["payload"])
                        if device.get("mac", "").lower() != self.config["expected_mac"].lower() or device.get("protocol") != "SGA1":
                            raise ValueError("XIAO 固件或板卡标识与配置不符")
                        if device.get("sample_rate") != 16000 or device.get("channels") != 1 or device.get("format") != "s16le":
                            raise ValueError("XIAO 音频格式不符合 16kHz 单声道 s16le 协议")
                        self.device = device
                    elif self.device is not None and packet["kind"] == 1 and self.camera_enabled:
                        frame = cv2.imdecode(np.frombuffer(packet["payload"], dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is None:
                            raise ValueError("XIAO JPEG 数据无法解码")
                        with self.state_lock:
                            self.frame, self.frame_time = frame, now
                            self.frames_received += 1
                    elif self.device is not None and packet["kind"] == 2 and self.audio_enabled:
                        payload = packet["payload"]
                        if len(payload) % 2:
                            raise ValueError("XIAO PCM 样本长度错误")
                        samples = np.frombuffer(payload, dtype="<i2").astype(np.float32)/32768.
                        samples = np.clip(samples*self.config["audio_gain"], -1., 1.)
                        self.audio_samples_received += len(samples)
                        callback = self.audio_callback
                        if callback:
                            callback(samples.reshape(-1,1),len(samples),None,None)
        except Exception as exc:
            if not self.stop_event.is_set():
                self.error = str(exc)
        finally:
            with self.state_lock:
                self.frame, self.frame_time = None, 0.

    def _stop_if_idle(self):
        if (self.camera_enabled or self.audio_enabled) and self.thread and self.thread.is_alive():
            return
        if self.serial is not None:
            try:
                self._command("STOP")
            except Exception:
                pass
            self.stop_event.set()
            if self.thread:
                self.thread.join(timeout=1)
            self.serial.close()
            self.serial = None

    def set_camera(self, enabled):
        with self.lifecycle_lock:
            if enabled:
                self._ensure_started()
                self.camera_enabled = True
                self._command("CAM_ON")
            else:
                self.camera_enabled = False
                with self.state_lock:
                    self.frame = None
                if self.serial is not None:
                    try:
                        self._command("CAM_OFF")
                    except Exception as exc:
                        self.error = str(exc)
                self._stop_if_idle()

    def set_audio(self, enabled, callback=None):
        with self.lifecycle_lock:
            if enabled:
                self._ensure_started()
                self.audio_callback, self.audio_enabled = callback, True
                self._command("MIC_ON")
            else:
                self.audio_callback, self.audio_enabled = None, False
                if self.serial is not None:
                    try:
                        self._command("MIC_OFF")
                    except Exception as exc:
                        self.error = str(exc)
                self._stop_if_idle()

    def snapshot(self):
        with self.state_lock:
            if not self.camera_enabled or self.frame is None:
                raise ValueError(self.error or "XIAO 摄像头未就绪，请启动并等待画面")
            require_fresh(self.frame_time)
            return self.frame.copy(), self.frame_time

    def status(self):
        return {"port":self.port_name,"connected":bool(self.thread and self.thread.is_alive()),"camera_enabled":self.camera_enabled,"audio_enabled":self.audio_enabled,"error":self.error,"frames_received":self.frames_received,"audio_samples_received":self.audio_samples_received,"bad_packets":self.parser.bad_packets,"device":self.device}
