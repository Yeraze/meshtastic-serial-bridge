# Meshtastic Serial-to-TCP Bridge

Convert a USB-connected Meshtastic device into a network-accessible TCP device.

## Solution: socat-based Bridge

This project uses **socat** (a mature serial bridging tool) instead of custom code for maximum reliability.

### Features

✅ **Fully Automated** - HUPCL disabled automatically on startup  
✅ **Zero Configuration** - Works out of the box  
✅ **Production Ready** - Built on industry-standard socat  
✅ **Tiny Footprint** - Only ~47MB Alpine image  
✅ **Auto-Restart** - Survives reboots with `restart: unless-stopped`  
✅ **Works Perfectly** - Full meshtastic CLI compatibility

## Quick Start

```bash
# Clone or navigate to this directory
cd /home/yeraze/Development/meshtastic-serial-bridge

# Build the image
docker build -t socat-bridge -f src/Dockerfile.socat src/

# Start the bridge
docker compose -f docker-compose-socat.yml up -d

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

Edit `docker-compose-socat.yml` to customize:

```yaml
environment:
  - SERIAL_DEVICE=/dev/ttyUSB0   # Change serial device
  - BAUD_RATE=115200             # Change baud rate
  - TCP_PORT=4403                # Change TCP port
```

## Logs

```bash
# View logs
docker compose -f docker-compose-socat.yml logs -f

# Check startup
docker compose -f docker-compose-socat.yml logs | head -15
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
docker compose -f docker-compose-socat.yml down
```

## Files

```
├── src/
│   ├── Dockerfile.socat         # Alpine + socat + python3
│   └── entrypoint-socat.sh      # Startup script (HUPCL + socat)
├── docker-compose-socat.yml     # Service definition
└── README-SOCAT.md              # Detailed documentation
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
docker compose -f docker-compose-socat.yml down
```

### Permission denied
Device must be accessible to the container (check host permissions)

### Device still reboots
Check logs - HUPCL disable may have failed

## Architecture

```
meshtastic CLI → TCP:4403 → socat → /dev/ttyUSB0 → Meshtastic Device
```

Simple, reliable, production-ready!

## License

MIT

---

🎉 **Ready to use!** Just `docker compose up` and start using your device over the network.
