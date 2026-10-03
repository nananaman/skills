import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'meta/skill-maintenance/scripts'))
import codex_wire as wire


class WireTest(unittest.TestCase):
    def test_rfc_handshake_validates_upgrade_and_accept(self):
        header=(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                b'Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n')
        wire.accept(io.BytesIO(header),'dGhlIHNhbXBsZSBub25jZQ==')
        with self.assertRaises(ValueError):wire.accept(io.BytesIO(header.replace(b'101',b'403',1)),'dGhlIHNhbXBsZSBub25jZQ==')
        with self.assertRaises(ValueError):wire.accept(io.BytesIO(header),'different-key')

    def test_client_frames_are_masked(self):
        with patch.object(wire.os,'urandom',return_value=b'\x01\x02\x03\x04'):
            self.assertEqual(b'\x81\x82\x01\x02\x03\x04\x7a\x7f',wire.frame(b'{}'))

    def test_server_frames_parse_short_and_extended_lengths(self):
        self.assertEqual((True,1,b'{}'),wire.receive(io.BytesIO(b'\x81\x02{}')))
        self.assertEqual((True,1,b'a'*128),wire.receive(io.BytesIO(b'\x81\x7e\x00\x80'+b'a'*128)))

    def test_invalid_or_oversized_frames_stop_without_payload_read(self):
        for data in (b'\xc1\x02{}',b'\x81\x82mask{}',b'\x09\x00',b'\x81\x7f'+(9*1024*1024).to_bytes(8,'big')):
            with self.subTest(data=data),self.assertRaises(ValueError):wire.receive(io.BytesIO(data))

    def test_truncated_stream_stops(self):
        with self.assertRaises(ValueError):wire.receive(io.BytesIO(b'\x81\x04{}'))


if __name__=='__main__':unittest.main()
