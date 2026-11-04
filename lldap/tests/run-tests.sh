#!/usr/bin/env bash
set -euo pipefail

. "$(dirname "$0")/../../_shared/container-test-common.sh"

CONTAINER_NAME="lldap-test-${GITHUB_RUN_ID:-local}"
CONFIG_FILE="/data/lldap_config.toml"
LLDAP_JWT_SECRET=$(openssl rand -hex 32)
LLDAP_KEY_SEED=$(openssl rand -hex 32)
LLDAP_LDAP_USER_PASS=$(openssl rand -hex 16)

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

echo "Testing candidate image: $TEST_IMAGE"
check_image_user "$TEST_IMAGE" "1000:1000"

echo "Starting LLDAP candidate..."
docker run --detach \
  --name "$CONTAINER_NAME" \
  --env "LLDAP_JWT_SECRET=$LLDAP_JWT_SECRET" \
  --env "LLDAP_KEY_SEED=$LLDAP_KEY_SEED" \
  --env LLDAP_LDAP_BASE_DN=dc=example,dc=com \
  --env "LLDAP_LDAP_USER_PASS=$LLDAP_LDAP_USER_PASS" \
  "$TEST_IMAGE" >/dev/null

echo "Waiting for LLDAP readiness..."
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER_NAME" /app/lldap healthcheck \
    --config-file "$CONFIG_FILE" >/dev/null 2>&1; then
    echo "LLDAP readiness check passed!"
    exit 0
  fi

  if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME")" != "true" ]; then
    echo "LLDAP container exited unexpectedly" >&2
    docker logs "$CONTAINER_NAME"
    exit 1
  fi

  sleep 2
done

echo "LLDAP readiness check timed out" >&2
docker logs "$CONTAINER_NAME"
exit 1
