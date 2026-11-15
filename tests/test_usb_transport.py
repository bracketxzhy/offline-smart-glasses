import struct
import unittest
import zlib

from glasses.usb_transport import PacketParser, USBTransport


def packet(kind, payload):
    return struct.pack("<4sBBHIIII", b"SGA1",1,kind,24,7,1234,len(payload),zlib.crc32(payload)) + payload


class ProtocolTests(unittest.TestCase):
    def test_fragmented_packets_and_boot_messages_are_handled(self):
        parser = PacketParser()
        data = b"boot message\n" + packet(2,b"\x01\x00\xff\x7f")
        found = []
        for byte in data:
            found.extend(parser.feed(bytes([byte])))
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["payload"],b"\x01\x00\xff\x7f")
        self.assertEqual(found[0]["kind"],2)

    def test_corrupt_packet_is_rejected_and_next_valid_packet_recovered(self):
        parser = PacketParser()
        bad = bytearray(packet(1,b"jpeg"));bad[-1] ^= 1
        good = packet(3,b'{"ok":true}')
        found = parser.feed(bytes(bad)+good)
        self.assertEqual([x["kind"] for x in found],[3])
        self.assertGreater(parser.bad_packets,0)

    def test_oversized_length_cannot_hold_unbounded_buffer(self):
        parser = PacketParser()
        oversized = struct.pack("<4sBBHIIII",b"SGA1",1,1,24,1,1,2**31,0)
        self.assertEqual(len(parser.feed(oversized+packet(2,b"pcm"))),1)
        parser.feed(b"x"*1000000)
        self.assertLess(len(parser.buffer),24)

    def test_disconnected_serial_still_closes_on_stop(self):
        class BrokenSerial:
            closed = False
            def write(self, data): raise OSError("device removed")
            def close(self): self.closed = True
        for method in ["set_audio", "set_camera"]:
            transport = USBTransport({})
            port = BrokenSerial()
            transport.serial = port
            transport.camera_enabled = True
            getattr(transport,method)(False)
            self.assertTrue(port.closed)
            self.assertIsNone(transport.serial)
            self.assertIn("device removed",transport.error)


if __name__ == "__main__":
    unittest.main()
