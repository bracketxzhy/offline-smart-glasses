import json
import socket
import struct
import threading
import time
import unittest
import zlib

import cv2
import numpy as np

from glasses.wifi_transport import WiFiTransport
from glasses.sensor_input import SensorCamera, SensorInputStream


MAC = '02:00:00:00:00:01'

def packet(kind, data):
    return struct.pack('<4sBBHIIII', b'SGA1', 1, kind, 24, 0, 0, len(data), zlib.crc32(data)) + data

def status(**changes):
    value = dict(protocol='SGA1', version=1, mac=MAC, sample_rate=16000,
                 channels=1, format='s16le', camera_ready=True, microphone_ready=True)
    value.update(changes)
    return packet(3, json.dumps(value).encode())


class Board:
    def __init__(self, handshake=None, close_after=False, malformed_audio=False):
        self.server = socket.socket()
        self.server.bind(('127.0.0.1', 0)); self.server.listen(1)
        self.server.settimeout(.1)
        self.port = self.server.getsockname()[1]
        self.commands = []; self.stop = threading.Event(); self.errors = []
        self.handshake = status() if handshake is None else handshake
        self.close_after, self.malformed_audio = close_after, malformed_audio
        self.thread = threading.Thread(target=self.run, daemon=True); self.thread.start()

    def run(self):
        conn = None
        try:
            while not self.stop.is_set():
                try: conn, _ = self.server.accept(); break
                except socket.timeout: pass
            if conn is None: return
            conn.settimeout(.1)
            # Intentionally split both the header and the payload across sends.
            for start in range(0, len(self.handshake), 7):
                conn.sendall(self.handshake[start:start+7])
            if self.close_after: return
            image = cv2.imencode('.jpg', np.zeros((48, 64, 3), np.uint8))[1].tobytes()
            buf = b''
            while not self.stop.is_set():
                try:
                    chunk = conn.recv(4096)
                    if not chunk: break
                    buf += chunk
                    while b'\n' in buf:
                        line, buf = buf.split(b'\n', 1)
                        self.commands.append(line.decode())
                        if line == b'CAM_ON': conn.sendall(packet(1, image))
                        if line == b'MIC_ON':
                            conn.sendall(packet(2, b'x' if self.malformed_audio else b'\x00\x40\x00\xc0'))
                except socket.timeout: pass
        except (OSError, UnicodeError) as exc:
            if not self.stop.is_set(): self.errors.append(str(exc))
        finally:
            if conn: conn.close()

    def close(self):
        self.stop.set(); self.thread.join(2); self.server.close()


class WiFiTests(unittest.TestCase):
    def create(self, **kwargs):
        board = Board(**kwargs); self.addCleanup(board.close)
        transport = WiFiTransport(dict(host='127.0.0.1', port=board.port,
                                      expected_mac=MAC, audio_gain=1.0))
        self.addCleanup(lambda: (transport.set_audio(False), transport.set_camera(False)))
        return board, transport

    def until(self, predicate):
        deadline = time.monotonic()+3
        while time.monotonic()<deadline:
            if predicate(): return
            time.sleep(.01)
        self.fail('Expected state was not reached')

    def test_fragmented_handshake_camera_and_pcm_have_independent_lifecycle(self):
        board, transport = self.create(); received=[]
        camera=SensorCamera(transport)
        audio=SensorInputStream(transport, lambda data,*_: received.append(data.copy()))
        camera.start(); audio.start()
        self.until(lambda: transport.frames_received and len(received))
        image, stamp=camera.snapshot()
        self.assertEqual(image.shape,(48,64,3))
        np.testing.assert_allclose(received[0].ravel(),[.5,-.5])
        self.assertEqual(transport.audio_samples_received,2)
        camera.stop(); self.assertTrue(audio.active)
        self.assertTrue(transport.status()['connected'])
        audio.close(); self.assertFalse(transport.status()['connected'])
        self.assertFalse(camera.is_running())

    def test_wrong_device_is_rejected_before_media(self):
        board, transport=self.create(handshake=status(mac='00:00:00:00:00:00'))
        with self.assertRaisesRegex(ValueError,'标识'):
            transport.set_camera(True)
        self.assertFalse(transport.status()['connected'])

    def test_wrong_audio_format_is_rejected(self):
        board, transport=self.create(handshake=status(sample_rate=48000))
        with self.assertRaisesRegex(ValueError,'音频'):
            transport.set_camera(True)

    def test_eof_is_explicit_and_close_does_not_raise(self):
        board, transport=self.create(close_after=True)
        try: transport.set_camera(True)
        except (OSError, ValueError): pass
        self.until(lambda: transport.error is not None)
        self.assertFalse(transport.status()['connected'])
        transport.set_audio(False); transport.set_camera(False)
        self.assertIsNone(transport.connection)

    def test_odd_pcm_is_rejected(self):
        board, transport=self.create(malformed_audio=True)
        transport.set_audio(True,lambda *_:None)
        self.until(lambda: transport.error is not None)
        self.assertIn('PCM',transport.error)
        self.assertEqual(transport.audio_samples_received,0)

    def test_stop_releases_a_live_socket_without_waiting_for_network_timeout(self):
        board, transport=self.create(); transport.set_camera(True)
        begin=time.monotonic(); transport.set_camera(False)
        self.assertLess(time.monotonic()-begin,1.5)
        self.assertIsNone(transport.connection)


if __name__=='__main__': unittest.main()
