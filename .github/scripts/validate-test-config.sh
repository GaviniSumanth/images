#!/usr/bin/env bash
set -euo pipefail

TEST_CONTEXT="${1}"

test -f "build/$TEST_CONTEXT/run-tests.sh" || {
  echo "::error::Missing test entrypoint: $TEST_CONTEXT/run-tests.sh"
  exit 1
}

test -f "build/$TEST_CONTEXT/test-ffmpeg-runtime.cjs" || {
  echo "::error::Missing runtime test file: $TEST_CONTEXT/test-ffmpeg-runtime.cjs"
  exit 1
}