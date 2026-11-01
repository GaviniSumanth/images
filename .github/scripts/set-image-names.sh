#!/usr/bin/env bash
set -euo pipefail

OWNER="${1}"
IMAGE="${2}"

echo "name=ghcr.io/${OWNER}/${IMAGE}" >> "$GITHUB_OUTPUT"
echo "candidate=candidate-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" >> "$GITHUB_OUTPUT"