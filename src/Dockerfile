FROM alpine:latest

# Install socat and python3 (for HUPCL management)
RUN apk add --no-cache socat python3

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Default environment variables
ENV SERIAL_DEVICE=/dev/ttyUSB0
ENV BAUD_RATE=115200
ENV TCP_PORT=4403

ENTRYPOINT ["/entrypoint.sh"]
