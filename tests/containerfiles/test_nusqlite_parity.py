from pathlib import Path

import pytest

from prebuild import (
    KNOWN_OUR_SHA256,
    KNOWN_OUR_URL,
    KNOWN_UPSTREAM_URL,
    parse_nusqlite,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
OURS = REPO_ROOT / "audiobookshelf" / "Containerfile"

OFFICIAL_FIXTURE = r'''
RUN case "$TARGETPLATFORM" in \
  "linux/amd64") \
  curl -L -o /tmp/library.zip "https://github.com/mikiher/nunicode-sqlite/releases/download/v1.2/libnusqlite3-linux-musl-x64.zip" ;; \
  "linux/arm64") \
  curl -L -o /tmp/library.zip "https://github.com/mikiher/nunicode-sqlite/releases/download/v1.2/libnusqlite3-linux-musl-arm64.zip" ;; \
  *) echo "Unsupported platform: $TARGETPLATFORM" && exit 1 ;; \
  esac
'''

OURS_FIXTURE = r'''
RUN set -eux; \
    case "${TARGETPLATFORM}" in \
        "linux/amd64") \
            LIBRARY_URL="https://github.com/mikiher/nunicode-binaries/releases/download/v1.2/libnusqlite3-linux-musl-x64.zip"; \
            LIBRARY_SHA256="6fdd092b6ba471d9bd1d5c3b01da4ca2bd84f41b03c91ccc0db6d75f1d97e52d" \
            ;; \
        "linux/arm64") \
            LIBRARY_URL="https://github.com/mikiher/nunicode-binaries/releases/download/v1.2/libnusqlite3-linux-musl-arm64.zip"; \
            LIBRARY_SHA256="91e2fc92e473f07c59df9b430e6ff120e1b56cd9a6317e61ea123259669788a7" \
            ;; \
    esac
'''


def test_official_fixture_parser():
    assert parse_nusqlite(OFFICIAL_FIXTURE) == (KNOWN_UPSTREAM_URL, None)


def test_our_fixture_parser():
    assert parse_nusqlite(OURS_FIXTURE) == (KNOWN_OUR_URL, KNOWN_OUR_SHA256)


def test_real_containerfile_uses_the_known_amd64_pin():
    assert parse_nusqlite(OURS.read_text(encoding="utf-8")) == (
        KNOWN_OUR_URL,
        KNOWN_OUR_SHA256,
    )


def test_parser_rejects_missing_platform():
    with pytest.raises(AssertionError, match="No NuSQLite case block"):
        parse_nusqlite("FROM scratch\n", platform="linux/amd64")
