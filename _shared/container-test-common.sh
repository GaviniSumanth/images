#!/usr/bin/env bash
set -euo pipefail

check_image_user() {
  local image=$1
  local expected_user=$2
  local image_user

  docker info >/dev/null
  image_user=$(docker image inspect --format '{{.Config.User}}' "$image")
  if [ "$image_user" != "$expected_user" ]; then
    echo "Expected image to run as UID/GID ${expected_user}, got: ${image_user}"
    return 1
  fi
}
