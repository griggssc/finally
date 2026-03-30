#!/usr/bin/env bash
set -e

CONTAINER_NAME="finally"

echo "Stopping FinAlly..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null && echo "Stopped." || echo "Container was not running."
echo "Data volume preserved."
