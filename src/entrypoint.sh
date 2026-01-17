#!/bin/sh
# Entrypoint script for socat serial bridge
# Handles HUPCL disabling and starts socat with reconnect support

DEVICE="${SERIAL_DEVICE:-/dev/ttyUSB0}"
BAUD="${BAUD_RATE:-115200}"
TCP_PORT="${TCP_PORT:-4403}"
RECONNECT_DELAY="${RECONNECT_DELAY:-5}"
VERSION=$(cat /VERSION 2>/dev/null || echo "unknown")

echo "Meshtastic Serial Bridge v${VERSION}"
echo "  Device: $DEVICE"
echo "  Baud: $BAUD"
echo "  TCP Port: $TCP_PORT"
echo "  Reconnect Delay: ${RECONNECT_DELAY}s"

# Function to wait for device to be available
wait_for_device() {
    if [ ! -e "$DEVICE" ]; then
        echo "Waiting for device $DEVICE..."
        while [ ! -e "$DEVICE" ]; do
            sleep "$RECONNECT_DELAY"
        done
        echo "Device $DEVICE found"
    fi
}

# Function to disable HUPCL to prevent device reboot on disconnect
disable_hupcl() {
    echo "Disabling HUPCL on $DEVICE..."
    python3 -c "
import termios
import sys

try:
    with open('$DEVICE') as f:
        attrs = termios.tcgetattr(f)
        attrs[2] = attrs[2] & ~termios.HUPCL
        termios.tcsetattr(f, termios.TCSAFLUSH, attrs)
    print('HUPCL disabled')
except Exception as e:
    print(f'Warning: Could not disable HUPCL: {e}', file=sys.stderr)
    print('Device may reboot on disconnect', file=sys.stderr)
"
    # Small delay to let device settle
    sleep 0.5
}

# Wait for device on initial startup
wait_for_device
disable_hupcl

# Register mDNS service via Avahi (if available)
AVAHI_DIR="/etc/avahi/services"
if [ -d "$AVAHI_DIR" ] && [ -w "$AVAHI_DIR" ]; then
    echo "Registering mDNS service..."

    # Create sanitized service name
    SANITIZED_DEVICE=$(echo "$DEVICE" | sed 's/[\/\.]/_/g')
    SERVICE_NAME="${SERVICE_NAME:-Meshtastic Serial Bridge ($SANITIZED_DEVICE)}"
    SERVICE_FILE="$AVAHI_DIR/meshtastic-serial-bridge-${SANITIZED_DEVICE}.service"

    # Create Avahi service XML
    cat > "$SERVICE_FILE" << EOF
<?xml version="1.0" standalone="no"?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name>${SERVICE_NAME}</name>
  <service>
    <type>_meshtastic._tcp</type>
    <port>${TCP_PORT}</port>
    <txt-record>bridge=serial</txt-record>
    <txt-record>port=${TCP_PORT}</txt-record>
    <txt-record>serial_device=${DEVICE}</txt-record>
    <txt-record>baud_rate=${BAUD}</txt-record>
  </service>
</service-group>
EOF

    echo "✓ mDNS service registered: ${SERVICE_NAME}"
    echo "  Service type: _meshtastic._tcp.local."
    echo "  Port: $TCP_PORT"
    echo "  Test with: avahi-browse -rt _meshtastic._tcp"

    # Set up cleanup trap to remove service file on exit
    trap "rm -f '$SERVICE_FILE' 2>/dev/null" EXIT INT TERM
else
    echo "⚠ Avahi service directory not available - mDNS discovery disabled"
    echo "  To enable: mount host's /etc/avahi/services directory"
    echo "  Add to docker-compose.yml:"
    echo "    volumes:"
    echo "      - /etc/avahi/services:/etc/avahi/services"
fi

# Main loop - restart socat on disconnect with configurable delay
while true; do
    echo "Starting socat bridge..."
    echo "  Listening on: 0.0.0.0:$TCP_PORT"
    echo "  Connected to: $DEVICE @ ${BAUD}baud"
    echo

    socat \
        TCP-LISTEN:$TCP_PORT,fork,reuseaddr \
        FILE:$DEVICE,b$BAUD,raw,echo=0

    echo "Bridge disconnected, waiting ${RECONNECT_DELAY}s before retry..."
    sleep "$RECONNECT_DELAY"

    # Wait for device to reappear (in case it was unplugged)
    wait_for_device
    disable_hupcl
done
