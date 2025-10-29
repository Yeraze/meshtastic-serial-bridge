# Quick Start Guide

Get your Serial bridge running in 5 minutes!

## Step 1: Find Your Serial Device

```bash
# Check what USB devices are connected
ls -l /dev/tty* | grep USB

# Example output:
# crw-rw---- 1 root dialout 188, 0 Oct 28 15:30 /dev/ttyUSB0
```

Common device names:
- Linux: `/dev/ttyUSB0`, `/dev/ttyACM0`
- macOS: `/dev/cu.usbserial-*`
- Windows: `COM3`, `COM4`

**Copy your device path** (e.g., `/dev/ttyUSB0`)!

## Step 2: Check Permissions (Linux only)

```bash
# Add yourself to the dialout group
sudo usermod -a -G dialout $USER

# Log out and back in for this to take effect
# Or just use Docker with --device flag
```

## Step 3: Test Without Docker (Optional)

```bash
# Install pyserial
pip install pyserial

# Test the bridge directly
python src/serial_tcp_bridge.py /dev/ttyUSB0 --verbose
```

You should see:
```
✅ Connected to serial device: /dev/ttyUSB0
✅ TCP server listening on 0.0.0.0:4403
```

Press Ctrl+C to stop.

## Step 4: Build the Container

```bash
cd src
docker build -t meshmonitor-serial-bridge -f Dockerfile.serial .
```

Expected output:
```
Successfully built <image-id>
Successfully tagged meshmonitor-serial-bridge:latest
```

## Step 5: Start the Bridge

Replace `/dev/ttyUSB0` with your device path:

```bash
docker run -d --name serial-bridge \
  --network host \
  --restart unless-stopped \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  -v /etc/avahi/services:/etc/avahi/services \
  meshmonitor-serial-bridge /dev/ttyUSB0 --verbose
```

### Or use Docker Compose:

```bash
# Create .env file with your device
echo "SERIAL_DEVICE=/dev/ttyUSB0" > .env

# Start the service
docker compose -f docker-compose.serial.yml up -d
```

## Step 6: Verify It's Running

```bash
# Check container status
docker ps | grep serial-bridge

# View logs
docker logs -f serial-bridge
```

You should see:
```
✅ Connected to serial device: /dev/ttyUSB0
✅ TCP server listening on 0.0.0.0:4403
```

## Step 7: Test the Connection

```bash
# From the same machine or another machine on the network
telnet <bridge-ip> 4403
```

If it connects, you're ready! Press Ctrl+] then type `quit` to exit telnet.

## Step 8: Configure MeshMonitor

### If MeshMonitor is on the Same Machine:
```bash
MESHTASTIC_NODE_IP=localhost
MESHTASTIC_NODE_PORT=4403
```

### If MeshMonitor is on a Different Machine:
```bash
MESHTASTIC_NODE_IP=<bridge-machine-ip>
MESHTASTIC_NODE_PORT=4403
```

### Or use mDNS autodiscovery:
```bash
# Test mDNS discovery
avahi-browse -rt _meshtastic._tcp

# You should see:
#   Meshtastic Serial Bridge (_dev_ttyUSB0)
```

## Troubleshooting

### Container won't start?
```bash
# Check logs
docker logs serial-bridge

# Common issues:
# - Serial device not found: Check device path with ls -l /dev/tty*
# - Permission denied: Add --device flag or use dialout group
# - Device in use: Another process may be using the serial port
```

### Can't connect from MeshMonitor?
```bash
# Check bridge is listening
docker exec serial-bridge netstat -tln | grep 4403

# Should show: tcp 0 0 0.0.0.0:4403 0.0.0.0:* LISTEN

# Check firewall
sudo ufw status
sudo ufw allow 4403/tcp  # If using ufw
```

### Device keeps disconnecting?

```bash
# Try different baud rate (default is 115200)
docker stop serial-bridge
docker rm serial-bridge

docker run -d --name serial-bridge \
  --network host \
  --restart unless-stopped \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  meshmonitor-serial-bridge /dev/ttyUSB0 --baud 38400 --verbose

# Watch logs
docker logs -f serial-bridge
```

### How do I know what baud rate to use?

Meshtastic devices typically use:
- **115200** (modern default, try this first)
- **38400** (older default, try if 115200 fails)

Look in the logs - if you see garbled data or no data, try the other baud rate.

## Stopping the Bridge

```bash
docker stop serial-bridge
docker rm serial-bridge
```

## Testing Data Flow

Once connected, you should see log messages like:

```
📥 Serial packet received: 45 bytes
📤 Broadcasting to 1 TCP client(s)
📥 TCP frame received: 32 bytes
📤 Sending 36 bytes to serial
```

This shows data flowing bidirectionally between serial and TCP!

## Next Steps

- See `README.md` for detailed documentation
- See `docs/` for troubleshooting guides
- Check MeshMonitor connects and sees your node

## Need Help?

Check the full documentation or visit:
- MeshMonitor: https://github.com/Yeraze/meshmonitor
- Meshtastic: https://meshtastic.org
