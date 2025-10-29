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

# Start socat
echo "Starting socat bridge..."
echo "  Listening on: 0.0.0.0:$TCP_PORT"
echo "  Connected to: $DEVICE @ ${BAUD}baud"
echo

exec socat \
    TCP-LISTEN:$TCP_PORT,fork,reuseaddr \
    FILE:$DEVICE,b$BAUD,raw,echo=0
