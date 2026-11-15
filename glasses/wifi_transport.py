"""Explicit SGA1 TCP input from the XIAO access point; no source fallback."""
import json
import socket
import threading
import time

from .core import require_fresh
from .usb_transport import PacketParser


class WiFiTransport:
    def __init__(self, config):
        self.config = config
        self.lifecycle_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.connection = None
        self.camera_enabled = self.audio_enabled = False
        self.audio_callback = None
        self.frame, self.frame_time = None, 0.
        self.device = None
        self.error = None
        self.parser = PacketParser()
        self.frames_received = self.audio_samples_received = 0

    def _command(self, text):
        with self.write_lock:
            if self.connection is None:
                raise OSError('XIAO 无线连接已断开')
            self.connection.sendall((text+'\n').encode('ascii'))

    def _accept(self, packet):
        import cv2
        import numpy as np
        if packet['kind'] == 3:
            device = json.loads(packet['payload'])
            if (device.get('protocol') != 'SGA1' or device.get('version') != 1 or
                    device.get('mac', '').lower() != self.config['expected_mac'].lower()):
                raise ValueError('XIAO 无线固件或板卡标识与配置不符')
            if (device.get('sample_rate') != 16000 or device.get('channels') != 1 or
                    device.get('format') != 's16le'):
                raise ValueError('XIAO 无线音频必须为 16kHz 单声道 s16le')
            self.device = device
        elif self.device is not None and packet['kind'] == 1 and self.camera_enabled:
            frame = cv2.imdecode(np.frombuffer(packet['payload'], dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError('XIAO 无线 JPEG 无法解码')
            with self.state_lock:
                self.frame, self.frame_time = frame, time.monotonic()
                self.frames_received += 1
        elif self.device is not None and packet['kind'] == 2 and self.audio_enabled:
            payload = packet['payload']
            if len(payload) % 2:
                raise ValueError('XIAO 无线 PCM 样本长度错误')
            values = np.frombuffer(payload, dtype='<i2').astype(np.float32)/32768.
            values = np.clip(values*self.config['audio_gain'], -1., 1.)
            self.audio_samples_received += len(values)
            callback = self.audio_callback
            if callback:
                callback(values.reshape(-1, 1), len(values), None, None)

    def _ensure_started(self):
        if self.thread and self.thread.is_alive() and self.error is None:
            return
        self._close()
        self.error, self.device = None, None
        self.parser = PacketParser()
        self.stop_event.clear()
        try:
            conn = socket.create_connection((self.config['host'], int(self.config['port'])), timeout=4)
            conn.settimeout(.25)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.connection = conn
            self._command('START')
            deadline = time.monotonic()+6
            while self.device is None:
                if time.monotonic() > deadline:
                    raise ValueError('未收到 XIAO 无线 SGA1 握手')
                try: chunk = conn.recv(65536)
                except socket.timeout: continue
                if not chunk: raise OSError('XIAO 无线连接在握手时断开')
                for packet in self.parser.feed(chunk): self._accept(packet)
            self.thread = threading.Thread(target=self._read, args=(conn,), daemon=True, name='xiao-wifi')
            self.thread.start()
        except Exception as exc:
            self.error = str(exc)
            self._close()
            raise

    def _read(self, conn):
        last_received = time.monotonic()
        try:
            while not self.stop_event.is_set():
                try: chunk = conn.recv(65536)
                except socket.timeout:
                    if time.monotonic()-last_received > 8:
                        raise OSError('XIAO 无线数据/状态超时')
                    continue
                if not chunk: raise OSError('XIAO 无线连接已断开')
                last_received = time.monotonic()
                for packet in self.parser.feed(chunk): self._accept(packet)
        except Exception as exc:
            if not self.stop_event.is_set(): self.error = str(exc)
        finally:
            with self.state_lock:
                self.frame, self.frame_time = None, 0.
            conn.close()
            if self.connection is conn: self.connection = None

    def _close(self):
        self.stop_event.set()
        conn, self.connection = self.connection, None
        if conn is not None:
            try: conn.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            conn.close()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)
        with self.state_lock:
            self.frame, self.frame_time = None, 0.

    def _stop_if_idle(self):
        if ((self.camera_enabled or self.audio_enabled) and self.thread and
                self.thread.is_alive() and self.error is None):
            return
        if self.connection is not None:
            try: self._command('STOP')
            except OSError: pass
        self._close()

    def set_camera(self, enabled):
        with self.lifecycle_lock:
            if enabled:
                self._ensure_started()
                self.camera_enabled = True
                self._command('CAM_ON')
            else:
                self.camera_enabled = False
                with self.state_lock: self.frame = None
                if self.connection is not None:
                    try: self._command('CAM_OFF')
                    except OSError as exc: self.error = str(exc)
                self._stop_if_idle()

    def set_audio(self, enabled, callback=None):
        with self.lifecycle_lock:
            if enabled:
                self._ensure_started()
                self.audio_callback, self.audio_enabled = callback, True
                self._command('MIC_ON')
            else:
                self.audio_callback, self.audio_enabled = None, False
                if self.connection is not None:
                    try: self._command('MIC_OFF')
                    except OSError as exc: self.error = str(exc)
                self._stop_if_idle()

    def snapshot(self):
        with self.state_lock:
            if not self.camera_enabled or self.frame is None:
                raise ValueError(self.error or 'XIAO 无线摄像头未就绪，请启动并等待画面')
            require_fresh(self.frame_time)
            return self.frame.copy(), self.frame_time

    def status(self):
        return dict(host=self.config['host'], port=self.config['port'],
                    connected=bool(self.connection is not None and self.thread and self.thread.is_alive() and self.error is None),
                    camera_enabled=self.camera_enabled, audio_enabled=self.audio_enabled,
                    error=self.error, frames_received=self.frames_received,
                    audio_samples_received=self.audio_samples_received,
                    bad_packets=self.parser.bad_packets, device=self.device)
