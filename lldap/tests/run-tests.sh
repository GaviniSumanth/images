#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="lldap-test-${GITHUB_RUN_ID:-local}"
TEST_VOLUME="lldap-tests-${GITHUB_RUN_ID:-local}"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker volume rm "$TEST_VOLUME" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

. "$(dirname "$0")/../../_shared/container-test-common.sh"

echo "Testing candidate image: $TEST_IMAGE"

check_image_user "$TEST_IMAGE" "1000:1000"

docker volume create "$TEST_VOLUME" >/dev/null

docker run -d \
  --name "$CONTAINER_NAME" \
  --mount "type=volume,src=${TEST_VOLUME},dst=/data" \
  --env LLDAP_JWT_SECRET=test-jwt-secret-for-container-healthcheck \
  --env LLDAP_KEY_SEED=test-key-seed-for-container-healthcheck \
  --env LLDAP_LDAP_BASE_DN=dc=example,dc=com \
  --env LLDAP_LDAP_USER_PASS=test-admin-password \
  "$TEST_IMAGE" >/dev/null

echo "Waiting for LLDAP readiness..."

HEALTHY=false

for i in $(seq 1 60); do
  if docker exec "$CONTAINER_NAME" /app/lldap healthcheck --config-file /data/lldap_config.toml >/dev/null 2>&1; then
    HEALTHY=true
    break
  fi

  if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME")" != "true" ]; then
    echo "LLDAP container exited unexpectedly"
    docker logs "$CONTAINER_NAME"
    exit 1
  fi

  sleep 2
done

if [ "$HEALTHY" != "true" ]; then
  echo "LLDAP readiness check timed out"
  docker logs "$CONTAINER_NAME"
  exit 1
fi

echo "LLDAP readiness check passed!"
