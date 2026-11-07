import json
import os
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest

from container_test_common import (
    check_image_contract,
    container_name,
    docker_client,
    managed_container,
    published_port,
    wait_for_container,
)
from image_contract import EXPECTED_PORTS


IMAGE = os.environ.get("TEST_IMAGE")
ERROR_CASES = [
    (400, "Bad Request"),
    (401, "Unauthorized"),
    (403, "Forbidden"),
    (404, "Not Found"),
    (429, "Too Many Requests"),
    (500, "Internal Server Error"),
    (502, "Bad Gateway"),
    (503, "Service Unavailable"),
    (504, "Gateway Timeout"),
]
RESPONSE_FORMATS = {
    "html": "text/html",
    "json": "application/json",
    "xml": "application/xml",
    "txt": "text/plain",
}

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(IMAGE is None, reason="TEST_IMAGE is not set"),
]


def test_image_contract():
    check_image_contract(IMAGE, EXPECTED_PORTS["error-pages"])


@pytest.fixture(scope="module")
def error_pages_url():
    name = container_name("error-pages")
    container = docker_client().containers.run(
        IMAGE,
        detach=True,
        name=name,
        ports={"8080/tcp": ("127.0.0.1", None)},
        environment={"SEND_SAME_HTTP_CODE": "true"},
    )
    with managed_container(container):
        base_url = f"http://127.0.0.1:{published_port(container, 8080)}"

        def is_healthy(_container):
            try:
                status, _, _ = fetch_response(f"{base_url}/healthz")
                return status == 200
            except (TimeoutError, URLError):
                return False

        wait_for_container(container, is_healthy)
        yield base_url


def fetch_response(url, headers=None):
    request = Request(url, headers=headers or {})
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as error:
        response = error

    with response:
        return (
            response.status,
            response.headers.get_content_type(),
            response.read(),
        )


def assert_error_page_body(response_format, body, code, message):
    if response_format == "json":
        page = json.loads(body)
        assert page["error"] is True
        assert page["code"] == code
        assert page["message"] == message
    elif response_format == "xml":
        page = ET.fromstring(body)
        assert page.findtext("code") == str(code)
        assert page.findtext("message") == message
    else:
        text = body.decode("utf-8")
        assert str(code) in text
        assert message in text


def test_container_serves_health_endpoint(error_pages_url):
    status, _, _ = fetch_response(f"{error_pages_url}/healthz")
    assert status == 200


@pytest.mark.parametrize(
    ("code", "message"),
    ERROR_CASES,
    ids=[f"http-{code}" for code, _ in ERROR_CASES],
)
@pytest.mark.parametrize(
    ("response_format", "content_type"),
    RESPONSE_FORMATS.items(),
)
def test_error_page_response(
    error_pages_url, code, message, response_format, content_type
):
    status, actual_content_type, body = fetch_response(
        f"{error_pages_url}/{code}.{response_format}"
    )

    assert status == code
    assert actual_content_type == content_type
    assert_error_page_body(response_format, body, code, message)


@pytest.mark.parametrize(("code", "message"), ERROR_CASES)
def test_json_error_page_content_negotiation(error_pages_url, code, message):
    status, content_type, body = fetch_response(
        f"{error_pages_url}/{code}",
        headers={"Accept": "application/json"},
    )

    assert status == code
    assert content_type == "application/json"
    assert_error_page_body("json", body, code, message)
