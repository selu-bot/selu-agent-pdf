#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_TAG="${1:-selu-cap-pdf:latest}"
ARCHIVE_NAME="${2:-agent.tar.gz}"

cd "$ROOT_DIR"

echo "Building capability image: $IMAGE_TAG"
docker build -t "$IMAGE_TAG" capabilities/pdf/container

echo "Packaging agent archive: $ARCHIVE_NAME"
tar czf "$ARCHIVE_NAME" \
  --exclude='.git' \
  --exclude='.github' \
  --exclude='.DS_Store' \
  --exclude='capabilities/*/container' \
  --exclude='README.md' \
  agent.yaml \
  agent.md \
  agent.*.md \
  i18n/ \
  capabilities/

echo "Done."
