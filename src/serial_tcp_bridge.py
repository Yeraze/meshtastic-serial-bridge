#!/usr/bin/env python3
"""
Meshtastic Serial-to-TCP Bridge

Connects to a Meshtastic device via USB/Serial and exposes a TCP server
that speaks the Meshtastic TCP framing protocol, allowing MeshMonitor
to connect to serial-connected devices.

The serial protocol uses the SAME framing as TCP:
[0x94][0xC3][LENGTH_MSB][LENGTH_LSB][PROTOBUF]

So this bridge acts as a simple bidirectional forwarder between serial and TCP.

Usage:
    python serial_tcp_bridge.py <SERIAL_DEVICE> [--port 4403] [--baud 115200] [--verbose]

Example:
    python serial_tcp_bridge.py /dev/ttyUSB0 --port 4403 --verbose

Requirements:
    pip install pyserial
"""

import asyncio
import serial
import struct
import logging
import argparse
import sys
import os
import threading
import queue
import signal
import random
from typing import List, Optional

# Version
__version__ = "2.0.0"

# TCP/Serial Protocol constants (SAME for both!)
START1 = 0x94
START2 = 0xC3
MAX_PACKET_SIZE = 512
HEADER_SIZE = 4

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    result = []
    while value > 0x7f:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value & 0x7f)
    return bytes(result)


def build_want_config_packet() -> bytes:
    """
    Build a ToRadio packet with want_config_id field.

    This triggers the device to send its full configuration.
    Returns the complete framed packet ready to send.
    """
    # Generate random config ID
    config_id = random.randint(0, 0xFFFFFFFF)

    # Build protobuf message:
    # Field 100 (want_config_id), wire type 0 (varint)
    field_tag = encode_varint((100 << 3) | 0)
    value_bytes = encode_varint(config_id)
    protobuf_payload = field_tag + value_bytes

    # Add framing: [START1][START2][LENGTH_MSB][LENGTH_LSB][PAYLOAD]
    frame = struct.pack('>BBH', START1, START2, len(protobuf_payload)) + protobuf_payload

    logger.debug(f"Built want_config_id packet with ID {config_id:08x} ({len(frame)} bytes)")
    return frame


class MeshtasticSerialBridge:
    """
    Bridges Meshtastic Serial to TCP for MeshMonitor compatibility.

    Since both serial and TCP use the same framing protocol, this is
    a simple bidirectional forwarder.
    """

    def __init__(self, serial_device: str, tcp_port: int = 4403, baud_rate: int = 115200):
        self.serial_device = serial_device
        self.tcp_port = tcp_port
        self.baud_rate = baud_rate
        self.serial_conn: Optional[serial.Serial] = None

        self.tcp_clients: List[asyncio.StreamWriter] = []
        self.running = False
        self.serial_read_task: Optional[asyncio.Task] = None
        self.tcp_server = None

        # Config cache - stores initial config dump from device
        self.config_cache: List[bytes] = []
        self.config_complete = False
        self.config_requested = False  # Track if we've already requested config
        self.config_start_time = None  # When we started caching config
        self.CONFIG_CACHE_DURATION = 10  # Cache for 10 seconds

        # Avahi service file path
        self.avahi_service_file = None

        # Thread-safe queue for passing frames from serial thread to async event loop
        self.frame_queue: queue.Queue = queue.Queue(maxsize=200)  # Buffer up to 200 frames
        self.serial_thread: Optional[threading.Thread] = None

    async def start(self):
        """Start the Serial-TCP bridge."""
        logger.info(f"Starting Serial-TCP Bridge v{__version__}")
        logger.info(f"Serial Device: {self.serial_device}")
        logger.info(f"Baud Rate: {self.baud_rate}")
        logger.info(f"TCP Port: {self.tcp_port}")

        self.running = True

        # Connect to serial device
        await self.connect_serial()

        # Register mDNS service for autodiscovery
        await self.register_mdns_service()

        # Start TCP server
        await self.start_tcp_server()

    async def connect_serial(self):
        """Connect to Meshtastic device via serial port."""
        logger.info(f"Connecting to serial device: {self.serial_device}")

        try:
            # CRITICAL: Disable HUPCL to prevent device reboot on serial open
            # This matches what the official meshtastic library does
            import sys
            if sys.platform != "win32":
                import termios
                with open(self.serial_device, encoding="utf8") as f:
                    attrs = termios.tcgetattr(f)
                    attrs[2] = attrs[2] & ~termios.HUPCL
                    termios.tcsetattr(f, termios.TCSAFLUSH, attrs)
                logger.debug("✅ Disabled HUPCL (prevents device reboot)")
                await asyncio.sleep(0.1)

            # Open serial port with settings matching official meshtastic library
            self.serial_conn = serial.Serial(
                port=self.serial_device,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                exclusive=True,  # Exclusive access
                timeout=0.5,  # Match official library
                write_timeout=0  # Match official library (non-blocking writes)
            )
            self.serial_conn.flush()
            await asyncio.sleep(0.1)

            logger.info(f"✅ Connected to serial device: {self.serial_device}")

            # Start serial reading thread (for maximum speed)
            self.serial_thread = threading.Thread(
                target=self._serial_reader_thread,
                daemon=True,
                name="SerialReader"
            )
            self.serial_thread.start()
            logger.debug(f"✅ Started serial reading thread")

            # Start queue consumer task (processes frames from thread)
            self.serial_read_task = asyncio.create_task(self._process_frame_queue())
            logger.debug(f"✅ Started frame queue processor")

        except serial.SerialException as e:
            logger.error(f"❌ Failed to connect to serial device: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error connecting to serial: {e}")
            raise

    async def register_mdns_service(self):
        """Register mDNS service via Avahi service file for autodiscovery.

        Writes a service file to /etc/avahi/services/ which the host's Avahi
        daemon will automatically detect and publish on the network.

        Requires: -v /etc/avahi/services:/etc/avahi/services
        """
        try:
            # Create a sanitized service name from serial device
            sanitized_device = self.serial_device.replace('/', '_').replace('.', '_')
            service_name = f"Meshtastic Serial Bridge ({sanitized_device})"

            # Create Avahi service XML
            service_xml = f'''<?xml version="1.0" standalone="no"?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name>{service_name}</name>
  <service>
    <type>_meshtastic._tcp</type>
    <port>{self.tcp_port}</port>
    <txt-record>bridge=serial</txt-record>
    <txt-record>port={self.tcp_port}</txt-record>
    <txt-record>serial_device={self.serial_device}</txt-record>
    <txt-record>baud_rate={self.baud_rate}</txt-record>
    <txt-record>version={__version__}</txt-record>
  </service>
</service-group>
'''

            service_file_path = f"/etc/avahi/services/meshtastic-serial-bridge-{sanitized_device}.service"

            try:
                # Write service file for host's Avahi daemon
                with open(service_file_path, 'w') as f:
                    f.write(service_xml)
                self.avahi_service_file = service_file_path

                logger.info(f"✅ mDNS service registered: {service_name}")
                logger.info(f"   Service type: _meshtastic._tcp.local.")
                logger.info(f"   Port: {self.tcp_port}")
                logger.info(f"   Host Avahi will publish this service automatically")
                logger.info(f"   Test with: avahi-browse -rt _meshtastic._tcp")

            except PermissionError:
                logger.warning(f"Cannot write to {service_file_path}")
                logger.warning(f"mDNS autodiscovery will not work (TCP bridge still functional)")
                logger.info(f"Mount /etc/avahi/services with: -v /etc/avahi/services:/etc/avahi/services")

        except Exception as e:
            logger.warning(f"Failed to register mDNS service (bridge will still work): {e}")
            logger.debug(f"mDNS registration error details:", exc_info=True)

    def _serial_reader_thread(self):
        """
        Dedicated thread for reading from serial port (for maximum speed).
        Runs synchronously in a thread, reading as fast as possible and
        pushing frames to a queue for async processing.
        """
        logger.debug("Serial reader thread started")

        while self.running:
            try:
                frame = self._read_one_frame_blocking()

                if frame:
                    # Put frame in queue for async processing
                    # Use non-blocking put with small timeout to avoid deadlock on shutdown
                    try:
                        self.frame_queue.put(frame, timeout=0.1)
                    except queue.Full:
                        logger.warning("Frame queue full! Dropping packet to prevent blocking serial read")

            except Exception as e:
                if self.running:
                    logger.error(f"Error in serial reader thread: {e}")
                    import time
                    time.sleep(1.0)
                else:
                    break

        logger.debug("Serial reader thread ended")

    async def _process_frame_queue(self):
        """
        Async task that processes frames from the queue and broadcasts to TCP clients.
        This runs in the event loop while the serial thread reads at maximum speed.
        """
        logger.debug("Frame queue processor started")

        while self.running:
            try:
                # Check queue in non-blocking mode
                try:
                    frame = self.frame_queue.get_nowait()
                    logger.debug(f"📥 Serial packet received: {len(frame)} bytes")
                    # Broadcast to TCP clients (fire and forget)
                    asyncio.create_task(self.broadcast_to_tcp(frame))
                except queue.Empty:
                    # Queue empty, sleep briefly to avoid busy waiting
                    await asyncio.sleep(0.001)  # 1ms sleep

            except Exception as e:
                if self.running:
                    logger.error(f"Error processing frame queue: {e}")
                    await asyncio.sleep(1.0)
                else:
                    break

        logger.debug("Frame queue processor ended")

    def _read_one_frame_blocking(self) -> Optional[bytes]:
        """
        Read one complete framed packet from serial (blocking).
        Returns the complete frame including header.
        """
        if not self.serial_conn or not self.serial_conn.is_open:
            return None

        try:
            # Read header (4 bytes)
            header = self.serial_conn.read(HEADER_SIZE)

            if len(header) != HEADER_SIZE:
                return None

            # Validate frame start
            if header[0] != START1 or header[1] != START2:
                logger.debug(f"Skipping non-frame data: {header[0]:02x} {header[1]:02x}")
                return None

            # Parse length (big-endian 16-bit)
            length = struct.unpack('>H', header[2:4])[0]

            if length > MAX_PACKET_SIZE:
                logger.warning(f"Frame too large: {length} > {MAX_PACKET_SIZE}")
                return None

            # Read payload
            payload = self.serial_conn.read(length)

            if len(payload) != length:
                logger.warning(f"Incomplete frame: expected {length}, got {len(payload)}")
                return None

            # Return complete frame (header + payload)
            return header + payload

        except serial.SerialException as e:
            if self.running:
                logger.error(f"Serial error: {e}")
            return None
        except Exception as e:
            if self.running:
                logger.error(f"Unexpected error reading frame: {e}")
            return None

    async def broadcast_to_tcp(self, frame: bytes):
        """Broadcast frame to all connected TCP clients."""
        # Cache config packets for first 10 seconds
        if not self.config_complete:
            import time

            # Start timer on first packet
            if self.config_start_time is None:
                self.config_start_time = time.time()
                self.config_requested = True
                logger.info("📦 Started caching config packets")

            # Cache all packets for 10 seconds
            elapsed = time.time() - self.config_start_time
            if elapsed < self.CONFIG_CACHE_DURATION:
                self.config_cache.append(frame)
                logger.debug(f"📦 Cached config packet ({len(self.config_cache)} total, {elapsed:.1f}s elapsed)")
            else:
                # Time's up - mark complete
                logger.info(f"📦 Config cache complete after {elapsed:.1f}s ({len(self.config_cache)} packets)")
                self.config_complete = True

        if not self.tcp_clients:
            logger.debug("No TCP clients connected, dropping packet")
            return

        logger.debug(f"📤 Broadcasting to {len(self.tcp_clients)} TCP client(s)")
        # Show first 20 bytes for debugging
        preview = frame[:20].hex() if len(frame) <= 20 else frame[:20].hex() + "..."
        logger.info(f"Serial->TCP: {len(frame)} bytes: {preview}")

        disconnected = []
        for writer in self.tcp_clients:
            try:
                writer.write(frame)
                await writer.drain()
            except Exception as e:
                logger.warning(f"Failed to send to TCP client: {e}")
                disconnected.append(writer)

        # Remove disconnected clients
        for writer in disconnected:
            self.tcp_clients.remove(writer)
            logger.info(f"TCP client disconnected ({len(self.tcp_clients)} remaining)")

    async def start_tcp_server(self):
        """Start TCP server to accept connections from MeshMonitor."""
        self.tcp_server = await asyncio.start_server(
            self.handle_tcp_client,
            '0.0.0.0',  # Listen on all interfaces
            self.tcp_port
        )

        addr = self.tcp_server.sockets[0].getsockname()
        logger.info(f"✅ TCP server listening on {addr[0]}:{addr[1]}")
        logger.info(f"MeshMonitor can now connect to <bridge-ip>:{self.tcp_port}")

        self.running = True

        async with self.tcp_server:
            await self.tcp_server.serve_forever()

    async def handle_tcp_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a new TCP client connection."""
        addr = writer.get_extra_info('peername')
        logger.info(f"🔌 TCP client connected from {addr}")

        self.tcp_clients.append(writer)

        # Don't send want_config ourselves - let the client do it naturally!
        # We'll just cache whatever config the device sends in response to the client's request
        # This avoids duplicate requests that might confuse the device or interfere with timing

        # Replay cached config to new client if available
        if self.config_complete and self.config_cache:
            logger.info(f"📤 Replaying {len(self.config_cache)} cached config packets to new client")
            for cached_frame in self.config_cache:
                try:
                    writer.write(cached_frame)
                    await writer.drain()
                except Exception as e:
                    logger.warning(f"Failed to replay config to client: {e}")
                    break

        try:
            wake_buffer = bytearray()
            while self.running:
                # Read byte-by-byte to find frame start (like official library does)
                # Look for START1 (0x94)
                while True:
                    b = await reader.readexactly(1)
                    if b[0] == START1:
                        # Flush any buffered wake bytes before processing frame
                        if wake_buffer and self.serial_conn and self.serial_conn.is_open:
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, self.serial_conn.write, bytes(wake_buffer))
                            await loop.run_in_executor(None, self.serial_conn.flush)
                            wake_buffer.clear()
                        break
                    # Buffer wake-up bytes (0xC3) and other non-frame data
                    # These are needed to wake the device!
                    wake_buffer.append(b[0])
                    # Flush buffer every 32 bytes or when it gets large
                    if len(wake_buffer) >= 32 and self.serial_conn and self.serial_conn.is_open:
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, self.serial_conn.write, bytes(wake_buffer))
                        await loop.run_in_executor(None, self.serial_conn.flush)
                        wake_buffer.clear()

                # Look for START2 (0xC3)
                b = await reader.readexactly(1)
                if b[0] != START2:
                    logger.debug(f"Expected START2, got {b[0]:02x}")
                    continue

                # Read length (big-endian 16-bit)
                length_bytes = await reader.readexactly(2)
                length = struct.unpack('>H', length_bytes)[0]

                # Validate length
                if length > MAX_PACKET_SIZE:
                    logger.warning(f"Invalid packet length: {length} (max {MAX_PACKET_SIZE})")
                    continue

                logger.debug(f"📥 TCP frame received: {length} bytes")

                # Read payload
                payload = await reader.readexactly(length)

                # Combine into complete frame
                frame = bytes([START1, START2]) + length_bytes + payload

                # Log hex dump for debugging
                preview = frame[:20].hex() if len(frame) <= 20 else frame[:20].hex() + "..."
                logger.info(f"TCP->Serial: {len(frame)} bytes: {preview}")

                # Send to serial (forward complete frame)
                await self.send_to_serial(frame)

        except asyncio.IncompleteReadError:
            logger.info(f"TCP client {addr} disconnected")
        except ConnectionResetError:
            logger.info(f"TCP client {addr} connection reset by peer")
        except Exception as e:
            logger.error(f"Error handling TCP client: {e}")
        finally:
            if writer in self.tcp_clients:
                self.tcp_clients.remove(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionResetError, ConnectionError, OSError):
                # Connection already closed by peer - this is fine
                pass
            logger.info(f"TCP client {addr} closed ({len(self.tcp_clients)} remaining)")

    async def send_to_serial(self, frame: bytes):
        """Send complete frame to serial device."""
        if not self.serial_conn or not self.serial_conn.is_open:
            logger.warning("⚠️  Cannot send to serial - not connected")
            raise RuntimeError("Serial port not connected")

        try:
            logger.debug(f"📤 Sending {len(frame)} bytes to serial")

            # Run blocking serial write in executor
            await asyncio.get_event_loop().run_in_executor(
                None, self.serial_conn.write, frame
            )

            # CRITICAL: Flush to ensure data is actually sent to device
            await asyncio.get_event_loop().run_in_executor(
                None, self.serial_conn.flush
            )

            logger.debug(f"✅ Sent {len(frame)} bytes to serial")

        except serial.SerialException as e:
            logger.error(f"Failed to send to serial: {e}")
            raise

    async def stop(self):
        """Stop the bridge."""
        logger.info("Stopping Serial-TCP bridge...")
        self.running = False

        # Close TCP server
        if self.tcp_server:
            logger.info("Closing TCP server...")
            self.tcp_server.close()
            await self.tcp_server.wait_closed()
            logger.info("✅ TCP server closed")

        # Remove Avahi service file
        if hasattr(self, 'avahi_service_file') and self.avahi_service_file:
            try:
                logger.info("Removing mDNS service file...")
                if os.path.exists(self.avahi_service_file):
                    os.remove(self.avahi_service_file)
                logger.info("✅ mDNS service file removed")
            except Exception as e:
                logger.warning(f"Failed to remove mDNS service file: {e}")

        # Cancel serial reading task
        if self.serial_read_task:
            self.serial_read_task.cancel()
            try:
                await self.serial_read_task
            except asyncio.CancelledError:
                pass

        # Close serial port
        if self.serial_conn and self.serial_conn.is_open:
            try:
                logger.info("Closing serial port...")
                self.serial_conn.close()
                logger.info("✅ Serial port closed")
            except Exception as e:
                logger.warning(f"Failed to close serial port: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Meshtastic Serial-to-TCP Bridge for MeshMonitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Connect to USB device
  %(prog)s /dev/ttyUSB0

  # Use custom TCP port
  %(prog)s /dev/ttyUSB0 --port 14403

  # Use custom baud rate (default is 115200)
  %(prog)s /dev/ttyUSB0 --baud 38400

  # Verbose logging
  %(prog)s /dev/ttyUSB0 --verbose
        """
    )

    parser.add_argument(
        'serial_device',
        nargs='?',
        help='Serial device path (e.g., /dev/ttyUSB0, COM3)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=4403,
        help='TCP port to listen on (default: 4403)'
    )
    parser.add_argument(
        '--baud',
        type=int,
        default=115200,
        help='Serial baud rate (default: 115200, Meshtastic default is 38400 or 115200)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate serial device - check argument first, then environment variable
    serial_device = args.serial_device or os.environ.get('SERIAL_DEVICE')

    if not serial_device:
        parser.error("Serial device is required. Provide as argument or set SERIAL_DEVICE environment variable")

    # Check if serial device exists
    if not os.path.exists(serial_device):
        logger.error(f"Serial device does not exist: {serial_device}")
        logger.info(f"Available serial devices:")
        import glob
        for dev in glob.glob('/dev/tty*'):
            logger.info(f"  {dev}")
        sys.exit(1)

    # Create and run bridge
    bridge = MeshtasticSerialBridge(serial_device, args.port, args.baud)

    async def run_bridge():
        """Run bridge with proper shutdown handling."""
        loop = asyncio.get_running_loop()

        # Signal handler for graceful shutdown
        def handle_signal():
            logger.info("\n🛑 Received shutdown signal...")
            # Close the TCP server to trigger shutdown
            if bridge.tcp_server:
                bridge.tcp_server.close()

        # Register signal handlers with the event loop
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_signal)

        try:
            await bridge.start()
        except KeyboardInterrupt:
            logger.info("\n🛑 Interrupted by user")
        except Exception as e:
            logger.error(f"❌ Bridge failed: {e}")
            sys.exit(1)
        finally:
            # Remove signal handlers
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.remove_signal_handler(sig)
                except Exception:
                    pass  # Ignore errors during cleanup
            await bridge.stop()

    try:
        asyncio.run(run_bridge())
    except KeyboardInterrupt:
        # Already handled in run_bridge
        pass
    except Exception as e:
        logger.error(f"❌ Bridge failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
