#!/usr/bin/env bash
set -e

CONTAINER_NAME="finally"
IMAGE_NAME="finally"

echo "Building FinAlly..."
docker build -t "$IMAGE_NAME" .

echo "Stopping any existing container..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Starting FinAlly..."
docker run -d \
  --name "$CONTAINER_NAME" \
  -p 8000:8000 \
  -v finally-data:/app/db \
  --env-file .env \
  "$IMAGE_NAME"

echo ""
echo "FinAlly is running at http://localhost:8000"

# Open browser (macOS)
if command -v open &>/dev/null; then
  sleep 2
  open http://localhost:8000
fi
