#!/usr/bin/env bash
set -euo pipefail

TESTFILE="${1}"
TEST_CONTEXT="${2}"

test -f "build/$TESTFILE" || {
  echo "::error::Missing test Containerfile: $TESTFILE"
  exit 1
}

test -f "build/$TEST_CONTEXT/run-tests.sh" || {
  echo "::error::Missing test entrypoint: $TEST_CONTEXT/run-tests.sh"
  exit 1
}