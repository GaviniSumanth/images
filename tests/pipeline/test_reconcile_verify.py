import copy
import json
import urllib.error

import pytest

from reconcile_verify import (
    ReconcileError,
    alias_exists,
    parse_matrix,
    reconcile,
)

pytestmark = pytest.mark.unit

BUILD = [{"image": "a", "tag": "v1"}]
VERIFY = [{"image": "b", "tag": "v2"}, {"image": "c", "tag": "v3"}]


class FakeResponse:
    def __init__(self, body=b"{}", status=200):
        self.body = body
        self.status = status

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_for(*results):
    requests = []

    def opener(request, timeout):
        requests.append(request)
        result = results[len(requests) - 1]
        if isinstance(result, BaseException):
            raise result
        return result

    opener.requests = requests
    return opener


def test_present_alias_stays_in_verify():
    result = reconcile(
        copy.deepcopy(BUILD), VERIFY, "owner", "actor", "token", exists=lambda *_: True
    )
    assert result == {"build": BUILD, "verify": VERIFY}


def test_missing_alias_moves_to_build():
    result = reconcile(
        [],
        VERIFY,
        "owner",
        "actor",
        "token",
        exists=lambda repository, tag, *_: tag != "v2",
    )
    assert [entry["image"] for entry in result["build"]] == ["b"]
    assert [entry["image"] for entry in result["verify"]] == ["c"]


def test_missing_alias_already_in_build_is_not_duplicated():
    result = reconcile(
        copy.deepcopy(BUILD),
        [{"image": "a", "tag": "v1"}],
        "owner",
        "actor",
        "token",
        exists=lambda *_: False,
    )
    assert result["build"] == BUILD
    assert result["verify"] == []


def test_invalid_verify_entry_fails():
    with pytest.raises(ReconcileError, match="Invalid verify matrix entry"):
        reconcile([], [{"image": "b"}], "owner", "actor", "token", exists=lambda *_: True)


def test_invalid_owner_fails():
    with pytest.raises(ReconcileError, match="Invalid owner"):
        reconcile([], [], "Bad Owner", "actor", "token", exists=lambda *_: True)


def test_parse_matrix_rejects_invalid_json():
    with pytest.raises(ReconcileError, match="not valid JSON"):
        parse_matrix("not json", "BUILD_MATRIX")


def test_parse_matrix_rejects_non_list():
    with pytest.raises(ReconcileError, match="must be a JSON array"):
        parse_matrix('{"image": "a"}', "BUILD_MATRIX")


def test_parse_matrix_skips_non_object_entries():
    assert parse_matrix('[{"image": "a"}, 1, "x"]', "BUILD_MATRIX") == [{"image": "a"}]


def test_alias_exists_requests_token_then_manifest():
    opener = opener_for(
        FakeResponse(json.dumps({"token": "abc"}).encode()),
        FakeResponse(b"{}", 200),
    )

    assert alias_exists("owner/image", "v1.2.3", "actor", "secret", opener=opener)

    token_request, manifest_request = opener.requests
    assert token_request.full_url.startswith("https://ghcr.io/token?")
    assert "service=ghcr.io" in token_request.full_url
    assert "scope=repository%3Aowner%2Fimage%3Apull" in token_request.full_url
    assert manifest_request.full_url == (
        "https://ghcr.io/v2/owner/image/manifests/v1.2.3"
    )
    assert manifest_request.get_header("Authorization") == "Bearer abc"
    assert "application/vnd.oci.image.index.v1+json" in manifest_request.get_header(
        "Accept"
    )


def test_alias_exists_returns_false_for_missing_manifest():
    opener = opener_for(
        FakeResponse(json.dumps({"token": "abc"}).encode()),
        urllib.error.HTTPError(
            "https://ghcr.io/v2/owner/image/manifests/v1",
            404,
            "Not Found",
            None,
            None,
        ),
    )

    assert alias_exists("owner/image", "v1", "actor", "secret", opener=opener) is False


def test_alias_exists_fails_closed_for_auth_error():
    opener = opener_for(
        FakeResponse(json.dumps({"token": "abc"}).encode()),
        urllib.error.HTTPError(
            "https://ghcr.io/v2/owner/image/manifests/v1",
            403,
            "Forbidden",
            None,
            None,
        ),
    )

    with pytest.raises(ReconcileError, match="HTTP 403"):
        alias_exists("owner/image", "v1", "actor", "secret", opener=opener)


def test_alias_exists_fails_closed_when_token_is_denied():
    opener = opener_for(
        urllib.error.HTTPError(
            "https://ghcr.io/token", 403, "Forbidden", None, None
        )
    )

    with pytest.raises(ReconcileError, match="registry token"):
        alias_exists("owner/image", "v1", "actor", "secret", opener=opener)


def test_cli_passes_through_when_verify_is_empty(run_script, github_output):
    result = run_script(
        "reconcile_verify.py",
        env={
            "BUILD_MATRIX": '[{"image":"a","tag":"v1"}]',
            "VERIFY_MATRIX": "[]",
        },
    )

    assert result.returncode == 0, result.stderr
    assert github_output.read_text() == (
        'build_matrix=[{"image":"a","tag":"v1"}]\n'
        "verify_matrix=[]\n"
    )


def test_cli_fails_on_invalid_matrix(run_script):
    result = run_script(
        "reconcile_verify.py",
        env={"BUILD_MATRIX": "not json", "VERIFY_MATRIX": "[]"},
    )

    assert result.returncode == 1
    assert "::error::" in result.stdout
