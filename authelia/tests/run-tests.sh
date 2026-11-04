#!/usr/bin/env bash
set -euo pipefail

. "$(dirname "$0")/../../_shared/container-test-common.sh"

echo "Testing candidate image: $TEST_IMAGE"

check_image_user "$TEST_IMAGE" "1000:1000"

docker run --rm "$TEST_IMAGE" build-info

echo "Authelia image smoke test passed!"
