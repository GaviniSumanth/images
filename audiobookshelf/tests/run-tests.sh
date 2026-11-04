#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="audiobookshelf-test-${GITHUB_RUN_ID:-local}"
TEST_VOLUME="audiobookshelf-tests-${GITHUB_RUN_ID:-local}"
PORT="13378"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker volume rm "$TEST_VOLUME" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

. "$(dirname "$0")/../../_shared/container-test-common.sh"

echo "Testing candidate image: $TEST_IMAGE"

check_image_user "$TEST_IMAGE" "1000:1000"

# --------------------------------------------------
# Prepare test files
# --------------------------------------------------

echo "Preparing runtime tests..."

docker volume create "$TEST_VOLUME"

docker run --rm -i \
  -v "$TEST_VOLUME:/tests" \
  alpine:3.22 \
  sh -c 'cat > /tests/test-ffmpeg-runtime.cjs' < test-ffmpeg-runtime.cjs

# --------------------------------------------------
# FFmpeg runtime tests inside candidate
# --------------------------------------------------

echo "Running FFmpeg runtime tests inside candidate..."

docker run --rm \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,uid=1000,gid=1000 \
  --mount "type=volume,src=${TEST_VOLUME},dst=/tests,readonly" \
  --entrypoint node \
  "$TEST_IMAGE" \
  /tests/test-ffmpeg-runtime.cjs

# --------------------------------------------------
# AudioBookShelf health check
# --------------------------------------------------

echo "Starting AudioBookShelf candidate..."

docker run -d \
  --name "$CONTAINER_NAME" \
  -p "${PORT}:8000" \
  "$TEST_IMAGE"

echo "Waiting for AudioBookShelf container health status..."

HEALTHY=false

for i in $(seq 1 60); do
  STATUS=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$CONTAINER_NAME")

  if [ "$STATUS" = "healthy" ]; then
    HEALTHY=true
    break
  fi

  if [ "$STATUS" = "unhealthy" ]; then
    echo "AudioBookShelf container health check failed"
    docker logs "$CONTAINER_NAME"
    exit 1
  fi

  sleep 2
done

if [ "$HEALTHY" != "true" ]; then
  echo "AudioBookShelf container health check timed out"
  docker logs "$CONTAINER_NAME"
  exit 1
fi

echo "AudioBookShelf container health check passed!"

echo "All image tests passed!"