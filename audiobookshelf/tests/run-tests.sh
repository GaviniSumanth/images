#!/bin/sh
set -eu

CONTAINER_NAME="audiobookshelf-test-${GITHUB_RUN_ID:-local}"
TEST_VOLUME="audiobookshelf-tests-${GITHUB_RUN_ID:-local}"
PORT="13378"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker volume rm "$TEST_VOLUME" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

echo "Testing candidate image: $TEST_IMAGE"

docker info >/dev/null

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
  -p "${PORT}:80" \
  "$TEST_IMAGE"

echo "Waiting for AudioBookShelf health endpoint..."

HEALTHY=false

for i in $(seq 1 60); do
  if docker run --rm \
    --network host \
    curlimages/curl:latest \
    --fail --silent --show-error \
    "http://127.0.0.1:${PORT}/healthcheck" >/dev/null 2>&1; then
    HEALTHY=true
    break
  fi

  if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME")" != "true" ]; then
    echo "AudioBookShelf container exited unexpectedly"
    docker logs "$CONTAINER_NAME"
    exit 1
  fi

  sleep 2
done

if [ "$HEALTHY" != "true" ]; then
  echo "AudioBookShelf health check failed"
  docker logs "$CONTAINER_NAME"
  exit 1
fi

echo "AudioBookShelf health check passed!"

echo "All image tests passed!"