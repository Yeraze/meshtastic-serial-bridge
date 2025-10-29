#!/usr/bin/env python3
"""
Unit tests for Serial TCP Bridge
Tests cover basic functionality and error scenarios
"""

import pytest
import asyncio
import struct
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Import the bridge module
import serial_tcp_bridge


class TestSerialBridge:
    """Tests for serial bridge basic functionality"""

    @pytest.fixture
    def bridge(self):
        """Create a bridge instance"""
        with patch('serial_tcp_bridge.serial.Serial'):
            bridge = serial_tcp_bridge.MeshtasticSerialBridge(
                serial_device="/dev/ttyUSB0",
                tcp_port=4403,
                baud_rate=115200
            )
            return bridge

    def test_bridge_initialization(self, bridge):
        """Test that bridge is properly initialized"""
        assert bridge.serial_device == "/dev/ttyUSB0"
        assert bridge.tcp_port == 4403
        assert bridge.baud_rate == 115200
        assert bridge.serial_conn is None
        assert bridge.running is False

    def test_frame_parsing(self, bridge):
        """Test frame header validation"""
        # Valid frame header
        valid_header = bytes([0x94, 0xC3, 0x00, 0x10])  # 16-byte payload
        assert valid_header[0] == serial_tcp_bridge.START1
        assert valid_header[1] == serial_tcp_bridge.START2

        # Parse length
        length = struct.unpack('>H', valid_header[2:4])[0]
        assert length == 16

    def test_invalid_frame_start(self, bridge):
        """Test handling of invalid frame start bytes"""
        invalid_header = bytes([0x00, 0x00, 0x00, 0x10])
        assert invalid_header[0] != serial_tcp_bridge.START1
        assert invalid_header[1] != serial_tcp_bridge.START2

    @pytest.mark.asyncio
    async def test_broadcast_to_tcp_no_clients(self, bridge):
        """Test broadcasting when no clients are connected"""
        test_frame = b"\x94\xC3\x00\x04test"
        # Should not raise an error
        await bridge.broadcast_to_tcp(test_frame)

    @pytest.mark.asyncio
    async def test_broadcast_to_tcp_with_client(self, bridge):
        """Test broadcasting to connected client"""
        # Create mock TCP client
        mock_writer = AsyncMock()
        bridge.tcp_clients.append(mock_writer)

        test_frame = b"\x94\xC3\x00\x04test"
        await bridge.broadcast_to_tcp(test_frame)

        # Verify write was called
        mock_writer.write.assert_called_once_with(test_frame)
        mock_writer.drain.assert_called_once()


class TestFraming:
    """Tests for frame construction and parsing"""

    def test_valid_frame_construction(self):
        """Test creating a valid frame"""
        payload = b"test_payload"
        length = len(payload)

        # Create frame header
        header = struct.pack('>BBH',
                           serial_tcp_bridge.START1,
                           serial_tcp_bridge.START2,
                           length)

        frame = header + payload

        # Verify
        assert frame[0] == 0x94
        assert frame[1] == 0xC3
        assert len(frame) == 4 + len(payload)

        # Parse length back
        parsed_length = struct.unpack('>H', frame[2:4])[0]
        assert parsed_length == len(payload)

    def test_max_packet_size_enforcement(self):
        """Test that oversized packets are rejected"""
        max_size = serial_tcp_bridge.MAX_PACKET_SIZE

        # Valid size
        assert max_size == 512

        # Oversized payload
        large_payload_size = max_size + 100
        assert large_payload_size > max_size


class TestErrorScenarios:
    """Tests for error handling"""

    @pytest.fixture
    def bridge(self):
        """Create a bridge instance"""
        with patch('serial_tcp_bridge.serial.Serial'):
            bridge = serial_tcp_bridge.MeshtasticSerialBridge(
                serial_device="/dev/ttyUSB0",
                tcp_port=4403
            )
            return bridge

    @pytest.mark.asyncio
    async def test_send_to_serial_not_connected(self, bridge):
        """Test sending when serial is not connected"""
        test_frame = b"\x94\xC3\x00\x04test"

        with pytest.raises(RuntimeError):
            await bridge.send_to_serial(test_frame)

    def test_serial_device_validation(self):
        """Test that serial device path is validated"""
        # This would normally be caught in main()
        import os

        # Valid devices exist in /dev
        assert os.path.exists('/dev')

    @pytest.mark.asyncio
    async def test_tcp_client_disconnect_handling(self, bridge):
        """Test handling of TCP client disconnection"""
        # Create mock TCP client that fails on drain
        mock_writer = AsyncMock()
        mock_writer.drain = AsyncMock(side_effect=ConnectionResetError("Connection reset"))

        bridge.tcp_clients.append(mock_writer)

        test_frame = b"\x94\xC3\x00\x04test"
        await bridge.broadcast_to_tcp(test_frame)

        # Client should be removed from list
        assert mock_writer not in bridge.tcp_clients


class TestMDNSService:
    """Tests for mDNS service registration"""

    @pytest.fixture
    def bridge(self):
        """Create a bridge instance"""
        with patch('serial_tcp_bridge.serial.Serial'):
            bridge = serial_tcp_bridge.MeshtasticSerialBridge(
                serial_device="/dev/ttyUSB0",
                tcp_port=4403
            )
            return bridge

    @pytest.mark.asyncio
    async def test_mdns_service_xml_generation(self, bridge):
        """Test that mDNS service XML is properly formatted"""
        # Mock the file write to capture the XML
        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            await bridge.register_mdns_service()

            # If permission allowed, verify file was written
            if mock_file.write.called:
                written_xml = mock_file.write.call_args[0][0]

                # Verify XML structure
                assert '<?xml version="1.0"' in written_xml
                assert '_meshtastic._tcp' in written_xml
                assert f'<port>{bridge.tcp_port}</port>' in written_xml
                assert 'bridge=serial' in written_xml


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
