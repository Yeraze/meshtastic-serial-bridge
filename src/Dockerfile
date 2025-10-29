FROM alpine:latest

# Install socat, python3 (for HUPCL management), and avahi (for mDNS discovery)
RUN apk add --no-cache socat python3 avahi

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Default environment variables
ENV SERIAL_DEVICE=/dev/ttyUSB0
ENV BAUD_RATE=115200
ENV TCP_PORT=4403

ENTRYPOINT ["/entrypoint.sh"]
