#!/bin/sh
# Entrypoint script for socat serial bridge
# Handles HUPCL disabling and starts socat

set -e

DEVICE="${SERIAL_DEVICE:-/dev/ttyUSB0}"
BAUD="${BAUD_RATE:-115200}"
TCP_PORT="${TCP_PORT:-4403}"

echo "Meshtastic Serial Bridge starting..."
echo "  Device: $DEVICE"
echo "  Baud: $BAUD"
echo "  TCP Port: $TCP_PORT"

# Check if device exists
if [ ! -e "$DEVICE" ]; then
    echo "ERROR: Serial device $DEVICE not found!"
    exit 1
fi

# Disable HUPCL to prevent device reboot on disconnect
echo "Disabling HUPCL on $DEVICE..."
python3 -c "
import termios
import sys

try:
    with open('$DEVICE') as f:
        attrs = termios.tcgetattr(f)
        attrs[2] = attrs[2] & ~termios.HUPCL
        termios.tcsetattr(f, termios.TCSAFLUSH, attrs)
    print('✓ HUPCL disabled')
except Exception as e:
    print(f'Warning: Could not disable HUPCL: {e}', file=sys.stderr)
    print('Device may reboot on disconnect', file=sys.stderr)
"

# Small delay to let device settle
sleep 0.5

# Start socat
echo "Starting socat bridge..."
echo "  Listening on: 0.0.0.0:$TCP_PORT"
echo "  Connected to: $DEVICE @ ${BAUD}baud"
echo

exec socat \
    TCP-LISTEN:$TCP_PORT,fork,reuseaddr \
    FILE:$DEVICE,b$BAUD,raw,echo=0
