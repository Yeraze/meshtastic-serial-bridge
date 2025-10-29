#!/bin/bash
# Setup script for socat-based Meshtastic Serial-to-TCP Bridge

set -e

DEVICE="${1:-/dev/ttyUSB0}"

echo "Setting up Meshtastic Serial Bridge using socat..."
echo "Device: $DEVICE"
echo

# Step 1: Disable HUPCL
echo "[1/3] Disabling HUPCL to prevent device reboot..."
python3 -c "
import termios
DEVICE='$DEVICE'
with open(DEVICE) as f:
    attrs = termios.tcgetattr(f)
    attrs[2] = attrs[2] & ~termios.HUPCL
    termios.tcsetattr(f, termios.TCSAFLUSH, attrs)
    print(f'✓ Disabled HUPCL on {DEVICE}')
"

# Step 2: Build Docker image
echo
echo "[2/3] Building socat Docker image..."
docker build -t socat-bridge -f Dockerfile.socat . -q
echo "✓ Docker image built"

# Step 3: Start service
echo
echo "[3/3] Starting serial bridge service..."
docker compose -f docker-compose-socat.yml down 2>/dev/null || true
docker compose -f docker-compose-socat.yml up -d
echo "✓ Service started"

# Wait for service to be ready
echo
echo "Waiting for service to initialize..."
sleep 3

# Test connection
echo
echo "Testing connection..."
if timeout 10 meshtastic --host localhost --info >/dev/null 2>&1; then
    echo "✓ Connection successful!"
    echo
    echo "🎉 Meshtastic Serial Bridge is ready!"
    echo "   TCP Port: 4403"
    echo "   Serial Device: $DEVICE"
    echo
    echo "Usage:"
    echo "  meshtastic --host localhost --info"
    echo "  meshtastic --host localhost --nodes"
    echo
    echo "To stop:"
    echo "  docker compose -f docker-compose-socat.yml down"
else
    echo "⚠ Warning: Connection test failed, but service is running"
    echo "Check logs with: docker compose -f docker-compose-socat.yml logs"
fi
