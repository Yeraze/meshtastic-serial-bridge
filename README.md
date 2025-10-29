# Meshtastic Serial-to-TCP Bridge
[![Docker Image](https://ghcr-badge.egpl.dev/yeraze/meshtastic-serial-bridge/latest_tag?color=%235b4566&ignore=latest,main&label=version&trim=)](https://github.com/Yeraze/meshmonitor/pkgs/container/meshtastic-serial-bridge)
[![Docker Pulls](https://ghcr-badge.egpl.dev/yeraze/meshtastic-serial-bridge/size?color=%235b4566&tag=latest&label=image%20size&trim=)](https://github.com/Yeraze/meshmonitor/pkgs/container/meshtastic-serial-bridge)

Convert a USB-connected Meshtastic device into a network-accessible TCP device.  Designed for use with MeshMonitor but should work with any TCP-compatible Meshtastic application!

## Solution: socat-based Bridge

This project uses **socat** (a mature serial bridging tool) instead of custom code for maximum reliability.

### Features

✅ **Fully Automated** - HUPCL disabled automatically on startup
✅ **Zero Configuration** - Works out of the box
✅ **Production Ready** - Built on industry-standard socat
✅ **Tiny Footprint** - Only ~47MB Alpine image
✅ **Auto-Restart** - Survives reboots with `restart: unless-stopped`
✅ **Works Perfectly** - Full meshtastic CLI compatibility

## Prerequisites

### Device Configuration

Your Meshtastic device must have **serial mode enabled**. Configure using the CLI:

```bash
# Enable serial with correct settings
meshtastic --set serial.enabled true
meshtastic --set serial.echo false
meshtastic --set serial.mode SIMPLE
meshtastic --set serial.baud BAUD_115200

# Verify settings
meshtastic --get serial
```

**Important Settings:**
- `serial.enabled` = `true` (serial interface enabled)
- `serial.echo` = `false` (disable echo to prevent confusion)
- `serial.mode` = `SIMPLE` (default protocol mode)
- `serial.baud` = `BAUD_115200` (must match bridge configuration)

> **Note:** These are the default settings for most devices. If your device was working with the meshtastic CLI directly via USB, these settings are likely already correct.

## Quick Start

```bash
# Build the image
docker build -t meshtastic-serial-bridge -f src/Dockerfile src/

# Start the bridge
docker compose up -d

# Test it
meshtastic --host localhost --info
```

## What Happens on Startup

The container automatically:
1. Checks that `/dev/ttyUSB0` exists
2. **Disables HUPCL** to prevent device reboots
3. Starts socat listening on `0.0.0.0:4403`
4. Bridges TCP ↔ Serial at 115200 baud

## Usage

Once running, use the meshtastic CLI with `--host localhost`:

```bash
# Get device info
meshtastic --host localhost --info

# List mesh nodes
meshtastic --host localhost --nodes

# Send a message
meshtastic --host localhost --sendtext "Hello mesh"

# Any meshtastic command works!
```

## Configuration

Edit `docker-compose.yml` to customize:

```yaml
environment:
  - SERIAL_DEVICE=/dev/ttyUSB0   # Change serial device
  - BAUD_RATE=115200             # Change baud rate
  - TCP_PORT=4403                # Change TCP port
```

## Logs

```bash
# View logs
docker compose logs -f

# Check startup
docker compose logs | head -15
```

Expected output:
```
Meshtastic Serial Bridge starting...
  Device: /dev/ttyUSB0
  Baud: 115200
  TCP Port: 4403
Disabling HUPCL on /dev/ttyUSB0...
✓ HUPCL disabled
Starting socat bridge...
  Listening on: 0.0.0.0:4403
  Connected to: /dev/ttyUSB0 @ 115200baud
```

## Stopping

```bash
docker compose down
```

## Files

```
├── src/
│   ├── Dockerfile          # Alpine + socat + python3
│   └── entrypoint.sh       # Startup script (HUPCL + socat)
├── docker-compose.yml      # Service definition
└── README.md               # This file
```

## Why socat?

Initially, I created a custom Python bridge (`serial_tcp_bridge.py`), but it had issues with:
- Device stopping after ~50 packets
- Blocking I/O in async handlers
- Wake sequence handling
- CLI timeouts

**socat solved all of this** because it's specifically designed for serial bridging and handles all the low-level protocol details correctly.

## Troubleshooting

### Device not found
Ensure `/dev/ttyUSB0` exists and is passed through in docker-compose

### Port in use
```bash
docker compose down
```

### Permission denied
Device must be accessible to the container (check host permissions)

### Device still reboots
Check logs - HUPCL disable may have failed

### Serial settings mismatch
Verify device baud rate matches bridge configuration (default: 115200):
```bash
meshtastic --get serial.baud
```

### Device not responding
Ensure serial is enabled on the device:
```bash
meshtastic --get serial.enabled
```

## Architecture

```
meshtastic CLI → TCP:4403 → socat → /dev/ttyUSB0 → Meshtastic Device
```

Simple, reliable, production-ready!

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=yeraze/meshtastic-serial-bridge&type=date&legend=top-left)](https://www.star-history.com/#yeraze/meshtastic-serial-bridge&type=date&legend=top-left)
## License

MIT

---

🎉 **Ready to use!** Just `docker compose up` and start using your device over the network.
